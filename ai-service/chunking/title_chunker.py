"""TitleChunker — 标题感知分块，适合结构化文档。

借鉴 RAGFlow 的 hierarchy_chunker 思路：
    1. 从 ParsedDocument 提取标题块构建章节树
    2. 同一标题下的内容合并为一个 chunk
    3. 过长章节递归切分
    4. chunk.title 填入所属章节标题
    5. 标题 chunk 与正文 chunk 建立父子关系
"""

from dataclasses import dataclass, field
from typing import Union

from common import get_logger
from common.utils import estimate_tokens, generate_chunk_id
from parsing.models import ParsedDocument, TextBlock, TableBlock, ImageBlock

from .base import BaseChunker
from .models import Chunk, ChunkRelation

BlockType = Union[TextBlock, TableBlock, ImageBlock]

logger = get_logger(__name__)

_DEFAULT_MAX_TOKENS = 800  # 标题组最大 token 数


class TitleChunker(BaseChunker):
    """标题感知分块器。

    适合有明确标题层级的文档（手册、规范、API 文档等）。
    对缺乏标题的文档会降级为 TokenChunker 行为。
    """

    def __init__(self, max_tokens: int = _DEFAULT_MAX_TOKENS):
        self._max_tokens = max_tokens

    async def chunk(self, doc: ParsedDocument) -> tuple[list[Chunk], list[ChunkRelation]]:
        """按标题层级分块。"""
        # Step 1: 构建章节树
        sections = _build_sections(doc)
        if not sections:
            # 无标题 → 降级为简单按 block 分块
            logger.info("文档无标题层级，降级为简单分块")
            return await _fallback_chunk(doc, self._max_tokens)

        # Step 2: 每个 section 生成 chunk(s) — 共享 chunk index
        chunks: list[Chunk] = []
        chunk_idx = [0]  # mutable counter shared across all sections
        for section in sections:
            _section_to_chunks(section, doc, self._max_tokens, chunks, chunk_idx)

        # Step 3: 构建关系
        relations = _build_title_relations(chunks)

        logger.info(f"TitleChunker: {len(doc.blocks)} blocks → {len(sections)} sections → {len(chunks)} chunks")
        return chunks, relations


# ---- 内部辅助 ----

@dataclass
class _Section:
    """内部章节节点。"""
    title: str
    level: int
    page_num: int
    content_blocks: list[BlockType] = field(default_factory=list)
    children: list["_Section"] = field(default_factory=list)


def _build_sections(doc: ParsedDocument) -> list[_Section]:
    """从 ParsedDocument 构建章节树。"""
    sections: list[_Section] = []
    stack: list[_Section] = []  # 按层级栈

    for block in doc.blocks:
        if isinstance(block, TextBlock) and block.layout_type == "title":
            section = _Section(
                title=block.text,
                level=block.level or 1,  # 无 level 时默认 1，由 LlmMetadataEnrichStep 后续修正
                page_num=block.page_num,
            )

            # 弹出比当前层级更深的标题
            while stack and stack[-1].level >= block.level:
                popped = stack.pop()
                if stack:
                    stack[-1].children.append(popped)
                else:
                    sections.append(popped)

            stack.append(section)
        elif stack:
            # 内容归入当前最深层标题
            stack[-1].content_blocks.append(block)
        elif isinstance(block, (TextBlock, TableBlock, ImageBlock)):
            # 文档开头无标题的内容 → 视为独立 section
            if sections and not sections[-1].title:
                sections[-1].content_blocks.append(block)
            else:
                untitled = _Section(title="", level=0, page_num=0)
                untitled.content_blocks.append(block)
                sections.append(untitled)

    # 弹出剩余栈
    while stack:
        popped = stack.pop()
        if stack:
            stack[-1].children.append(popped)
        else:
            sections.append(popped)

    return sections


def _section_to_chunks(
    section: _Section, doc: ParsedDocument, max_tokens: int,
    chunks: list[Chunk], chunk_idx: list[int],
) -> None:
    """将章节转换为 chunks（原地添加到 chunks 列表）。"""
    doc_name = doc.metadata.file_name

    # 标题 chunk
    if section.title:
        title_id = generate_chunk_id(doc_name, chunk_idx[0])
        chunks.append(Chunk(
            id=title_id,
            content=section.title,
            content_with_weight=section.title,
            chunk_type="title",
            title=section.title,
            page_range=(section.page_num, section.page_num),
            tokens=estimate_tokens(section.title),
            metadata={"level": section.level},
        ))
        chunk_idx[0] += 1

    # 正文：合并内容 blocks
    current_text = ""
    for block in section.content_blocks:
        if isinstance(block, TextBlock):
            text = block.text
        elif isinstance(block, TableBlock):
            text = f"{block.description}\n{block.html}"
        elif isinstance(block, ImageBlock):
            text = block.description or ""
        else:
            continue

        combined_tokens = estimate_tokens(current_text + "\n\n" + text)
        if combined_tokens <= max_tokens:
            current_text += "\n\n" + text if current_text else text
        else:
            if current_text.strip():
                chunks.append(_make_content_chunk(
                    current_text, chunk_idx[0], doc_name, section
                ))
                chunk_idx[0] += 1
            current_text = text

    if current_text.strip():
        chunks.append(_make_content_chunk(
            current_text, chunk_idx[0], doc_name, section
        ))
        chunk_idx[0] += 1

    # 子章节递归 — 共享同一个 chunk_idx
    for child in section.children:
        _section_to_chunks(child, doc, max_tokens, chunks, chunk_idx)


def _make_content_chunk(
    text: str, idx: int, doc_name: str, section: _Section
) -> Chunk:
    """创建正文 Chunk。"""
    return Chunk(
        id=generate_chunk_id(doc_name, idx),
        content=text,
        content_with_weight=text,
        chunk_type="text",
        title=section.title or None,
        page_range=(section.page_num, section.page_num),
        tokens=estimate_tokens(text),
        metadata={"level": section.level},
    )


def _build_title_relations(chunks: list[Chunk]) -> list[ChunkRelation]:
    """构建标题→正文父子关系。"""
    relations = []
    current_parent_id = None

    for chunk in chunks:
        if chunk.chunk_type == "title":
            current_parent_id = chunk.id
            relations.append(ChunkRelation(parent_id=None))
        else:
            relations.append(ChunkRelation(parent_id=current_parent_id))

    # 填充兄弟关系
    for i in range(len(chunks)):
        if i > 0:
            relations[i].prev_id = chunks[i - 1].id
        if i < len(chunks) - 1:
            relations[i].next_id = chunks[i + 1].id

    return relations


async def _fallback_chunk(
    doc: ParsedDocument, max_tokens: int
) -> tuple[list[Chunk], list[ChunkRelation]]:
    """无标题时的降级分块。"""
    from .token_chunker import TokenChunker
    fallback = TokenChunker(chunk_token_size=max_tokens)
    return await fallback.chunk(doc)
