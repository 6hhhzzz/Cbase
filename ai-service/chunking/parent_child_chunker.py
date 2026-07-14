"""ParentChildChunker — 两级分块器（Parent+Child）。

策略:
    1. 按 \n\n 自然段落边界分组为 Parent（~500 tokens 上限）
    2. 每个 Parent 内按标点切分为 Child（~150 tokens）
    3. 表格/图片 block 各自独立为一个 Parent（自身为唯一 Child）
    4. Child content 注入 parent 的标题前缀
    5. Child metadata 携带 parent_id / parent_content / parent_title

核心思路:
    - 检索用 Child（精细语义匹配，~150 tokens）
    - 回答用 Parent（完整语义单元，~500 tokens，含完整列表/段落）
    - 所有解析器（DOCX/PDF/MD/HTML）共享统一逻辑
"""

from common import get_logger
from common.utils import estimate_tokens, generate_chunk_id
from parsing.models import ParsedDocument, TextBlock, TableBlock, ImageBlock

from .base import BaseChunker
from .models import Chunk, ChunkRelation

logger = get_logger(__name__)

# 父 chunk 切分的边界符
PARENT_SEPARATORS = ["\n\n"]

# 子 chunk 切分的标点
CHILD_SEPARATORS = ["\n", "。", "！", "？", ".", "!", "?", "；", ";"]

# 需要保留的 layout_type
_KEEP_LAYOUTS = {"title", "text", "equation"}

# 子 chunk 分隔符
CHILD_JOIN_SEP = "\n"


class ParentChildChunker(BaseChunker):
    """两级分块器。

    产出只有 Child chunk（Parent 信息存储在 Child 的 metadata 中）。
    """

    def __init__(
        self,
        parent_max_tokens: int = 500,
        child_target_tokens: int = 150,
        child_min_tokens: int = 40,
    ):
        """
        Args:
            parent_max_tokens: Parent chunk 最大 token 数
            child_target_tokens: Child chunk 目标 token 数
            child_min_tokens: Child chunk 最小 token 数（低于此的合并到相邻）
        """
        self._parent_max = parent_max_tokens
        self._child_target = child_target_tokens
        self._child_min = child_min_tokens

    async def chunk(self, doc: ParsedDocument) -> tuple[list[Chunk], list[ChunkRelation]]:
        """执行两级分块。

        Returns:
            (chunks: list[Chunk], relations: list[ChunkRelation])
            chunks 只包含 Child chunk。
        """
        # ── 阶段 0：收集所有 blocks，分组 ──
        parents: list[dict] = self._build_parents(doc)

        # ── 阶段 1：每个 Parent 内切 Child ──
        all_children: list[tuple[dict, int, Chunk]] = []  # (parent, child_idx_in_parent, Chunk)
        child_idx = 0

        for pi, parent in enumerate(parents):
            children = self._split_children(parent, pi)
            for ci, child_chunk in enumerate(children):
                all_children.append((parent, ci, child_chunk))
                child_idx += 1

        # ── 阶段 2：设置 content_with_weight ──
        chunks = [c for _, _, c in all_children]
        self._set_content_with_weight(chunks)

        # ── 阶段 3：构建关系 ──
        relations = self._build_relations(chunks)

        logger.info(
            f"ParentChildChunker: {len(doc.blocks)} blocks → "
            f"{len(parents)} parents → {len(chunks)} children"
        )
        return chunks, relations

    # ═══════════════════════════════════════════════════════════
    # 阶段 0：构建 Parent 列表
    # ═══════════════════════════════════════════════════════════

    def _build_parents(self, doc: ParsedDocument) -> list[dict]:
        """将 blocks 分组为 Parent。

        每个 Parent 是一个 dict:
            {
                "heading": str,           # 当前 section 标题
                "text_blocks": [...],     # 包含的 TextBlock
                "total_tokens": int,
                "parent_type": "text" | "table" | "image",
            }
        """
        parents: list[dict] = []
        current_heading = ""
        text_buffer: list[TextBlock] = []
        buffer_tokens = 0

        def _flush_text_parent():
            nonlocal text_buffer, buffer_tokens
            if not text_buffer:
                return
            combined = "\n\n".join(b.text for b in text_buffer)
            parents.append({
                "heading": current_heading,
                "content": combined,
                "total_tokens": estimate_tokens(combined),
                "parent_type": "text",
                "start_page": text_buffer[0].page_num,
                "end_page": text_buffer[-1].page_num,
            })
            text_buffer = []
            buffer_tokens = 0

        for block in doc.blocks:
            if isinstance(block, TextBlock):
                if block.layout_type == "title":
                    # title block → 更新当前 heading + 作为边界
                    _flush_text_parent()
                    current_heading = block.text[:100]
                    # title 自己也作为一个独立的 text parent（短 parent）
                    title_tokens = estimate_tokens(block.text)
                    parents.append({
                        "heading": current_heading,
                        "content": block.text,
                        "total_tokens": title_tokens,
                        "parent_type": "text",
                        "start_page": block.page_num,
                        "end_page": block.page_num,
                    })
                    continue

                if block.layout_type not in _KEEP_LAYOUTS:
                    # header/footer/reference → 作为边界
                    _flush_text_parent()
                    continue

                # text block → 累积
                block_tokens = estimate_tokens(block.text)

                if buffer_tokens + block_tokens > self._parent_max and text_buffer:
                    # 超出 parent 上限 → 切出一个新 parent
                    _flush_text_parent()

                text_buffer.append(block)
                buffer_tokens += block_tokens

            elif isinstance(block, TableBlock):
                # 表格 → 先 flush text parent，表格自身作为独立 parent
                _flush_text_parent()
                content = f"{block.description}\n{block.html}" if block.description else block.html
                parents.append({
                    "heading": current_heading,
                    "content": content,
                    "total_tokens": estimate_tokens(content),
                    "parent_type": "table",
                    "start_page": block.page_num,
                    "end_page": block.page_num,
                    "caption": block.caption,
                })

            elif isinstance(block, ImageBlock):
                _flush_text_parent()
                parts = []
                if block.description:
                    parts.append(block.description)
                if block.caption:
                    parts.append(f"[图片说明: {block.caption}]")
                content = "\n".join(parts) if parts else "[图片]"
                parents.append({
                    "heading": current_heading,
                    "content": content,
                    "total_tokens": estimate_tokens(content),
                    "parent_type": "image",
                    "start_page": block.page_num,
                    "end_page": block.page_num,
                })

            else:
                # 未知类型 → 当作边界
                _flush_text_parent()

        # 最后 flush
        _flush_text_parent()

        return parents

    # ═══════════════════════════════════════════════════════════
    # 阶段 1：Parent → Children
    # ═══════════════════════════════════════════════════════════

    def _split_children(self, parent: dict, parent_idx: int) -> list[Chunk]:
        """将一个 Parent 切分为多个 Child chunk。"""
        parent_type = parent["parent_type"]
        parent_content = parent["content"]
        parent_heading = parent["heading"]

        # 生成确定性 parent_id
        parent_id = generate_chunk_id(
            f"parent_{parent_idx}", parent["start_page"]
        )

        if parent_type in ("table", "image"):
            # 表格/图片：自身为唯一 Child
            chunk = Chunk(
                id=generate_chunk_id(f"child_{parent_idx}_0", 0),
                content=parent_content,
                chunk_type=parent_type,
                title=parent.get("caption"),
                page_range=(parent["start_page"], parent["end_page"]),
                tokens=parent["total_tokens"],
                metadata={
                    "parent_id": parent_id,
                    "parent_content": parent_content,
                    "parent_title": parent_heading,
                    "parent_type": parent_type,
                    "layout_type": parent_type,
                },
            )
            return [chunk]

        # 文本 Parent → 按标点切分
        raw_splits = self._split_by_separators(parent_content)
        merged = self._merge_short_children(raw_splits)

        children = []
        for ci, child_text in enumerate(merged):
            # 构建带前缀的 child content
            if parent_heading and parent_heading not in child_text:
                prefixed = f"{parent_heading} | {child_text}"
            else:
                prefixed = child_text

            child_id = generate_chunk_id(f"child_{parent_idx}_{ci}", ci)
            chunk = Chunk(
                id=child_id,
                content=prefixed,
                chunk_type="text",
                title=parent_heading or None,
                page_range=(parent["start_page"], parent["end_page"]),
                tokens=estimate_tokens(prefixed),
                metadata={
                    "parent_id": parent_id,
                    "parent_content": parent_content,
                    "parent_title": parent_heading,
                    "parent_type": "text",
                    "child_index_in_parent": ci,
                    "parent_total_children": len(merged),
                },
            )
            children.append(chunk)

        return children

    def _split_by_separators(self, text: str) -> list[str]:
        """按标点优先级递归切分文本为 child 片段。

        递归尝试: \n → 。→ ！→ ？→ . → ! → ? → ；→ ;
        """
        if not text.strip():
            return [text]

        tokens = estimate_tokens(text)
        if tokens <= self._child_target:
            return [text]

        for sep in CHILD_SEPARATORS:
            parts = text.split(sep)
            if len(parts) <= 1:
                continue
            # 重新组装：每个 part 加上分隔符（保留标点）
            result = []
            for i, part in enumerate(parts):
                if i < len(parts) - 1:
                    result.append(part + sep)
                elif part.strip():
                    result.append(part)
            # 检查是否切出了多个有效的片段
            non_empty = [r for r in result if r.strip()]
            if len(non_empty) > 1:
                # 递归处理每个片段（可能仍然太大）
                final = []
                for r in result:
                    if not r.strip():
                        continue
                    if estimate_tokens(r) > self._child_target:
                        # 尝试更细粒度的分隔符
                        sub = self._split_by_separators(r)
                        final.extend(sub)
                    else:
                        final.append(r)
                return final

        # 所有分隔符都失败 → 强制按 child_target 切分
        return self._force_split(text)

    def _force_split(self, text: str) -> list[str]:
        """强制按 child_target tokens 切分（用于无标点长文本）。"""
        parts = []
        current = ""
        for char in text:
            current += char
            if estimate_tokens(current) >= self._child_target:
                parts.append(current)
                current = ""
        if current.strip():
            parts.append(current)
        return parts if parts else [text]

    def _merge_short_children(self, splits: list[str]) -> list[str]:
        """合并过短的 child chunk（低于 child_min_tokens）。"""
        if not splits:
            return []

        merged = []
        current = splits[0]

        for split in splits[1:]:
            combined = current + CHILD_JOIN_SEP + split
            if estimate_tokens(combined) <= self._child_target:
                current = combined
            else:
                if estimate_tokens(current) >= self._child_min:
                    merged.append(current)
                    current = split
                else:
                    # 太小 → 强制合并
                    current = combined

        if current.strip():
            # 最后一段：如果太小，合并到前面
            if estimate_tokens(current) < self._child_min and merged:
                merged[-1] = merged[-1] + CHILD_JOIN_SEP + current
            else:
                merged.append(current)

        return merged

    # ═══════════════════════════════════════════════════════════
    # 阶段 2 & 3: content_with_weight + relations
    # ═══════════════════════════════════════════════════════════

    def _set_content_with_weight(self, chunks: list[Chunk]) -> None:
        """设置 content_with_weight（BM25 增强）。"""
        for i, chunk in enumerate(chunks):
            parts = [chunk.content]
            # 前重叠
            if i > 0 and chunks[i - 1].chunk_type == "text":
                prev = chunks[i - 1].content
                overlap_chars = min(int(len(prev) * 0.15), 200)
                if overlap_chars > 0:
                    parts.append(prev[-overlap_chars:])
            # 后重叠
            if i < len(chunks) - 1 and chunks[i + 1].chunk_type == "text":
                nxt = chunks[i + 1].content
                overlap_chars = min(int(len(nxt) * 0.15), 200)
                if overlap_chars > 0:
                    parts.append(nxt[:overlap_chars])
            chunk.content_with_weight = "\n".join(parts)
            chunk.tokens = estimate_tokens(chunk.content_with_weight)

    def _build_relations(self, chunks: list[Chunk]) -> list[ChunkRelation]:
        """构建相邻关系（同 parent 内 child 间 prev/next + 所有 child → parent_id）。"""
        relations = []
        for i in range(len(chunks)):
            cur = chunks[i]
            prev_id = chunks[i - 1].id if i > 0 else None
            next_id = chunks[i + 1].id if i < len(chunks) - 1 else None
            parent_id = cur.metadata.get("parent_id")

            # 判断前后是否是同一个 parent
            if i > 0 and chunks[i - 1].metadata.get("parent_id") != parent_id:
                prev_id = None
            if i < len(chunks) - 1 and chunks[i + 1].metadata.get("parent_id") != parent_id:
                next_id = None

            rel = ChunkRelation(
                parent_id=parent_id,
                prev_id=prev_id,
                next_id=next_id,
            )
            relations.append(rel)
        return relations
