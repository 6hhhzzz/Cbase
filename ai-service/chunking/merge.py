"""Naive Merge — RAGFlow 移植。

将过短的相邻 chunk 合并，直到每个 chunk 接近目标 token 数。
与 TokenChunker._merge_short 的区别：后者只合并单个文本块内的 split 结果，
本模块作用于最终 chunk 列表，跨 block 合并。

用法:
    from chunking.merge import merge_chunks
    chunks, relations = merge_chunks(chunks, relations, target_tokens=512)
"""

from common import get_logger
from common.utils import estimate_tokens, generate_chunk_id

from .models import Chunk, ChunkRelation

logger = get_logger(__name__)


def merge_chunks(
    chunks: list[Chunk],
    relations: list[ChunkRelation],
    target_tokens: int = 512,
    min_tokens: int = 50,
    separator: str = "\n\n",
) -> tuple[list[Chunk], list[ChunkRelation]]:
    """合并过短的相邻文本 chunk。

    贪婪算法：从头扫描，将 token 数低于 min_tokens 的 chunk
    合并到相邻 chunk，直到每个 chunk 接近 target_tokens。

    表格和图片 chunk 保留不合并。

    Args:
        chunks: 原始 chunk 列表
        relations: 原始关系列表
        target_tokens: 目标 chunk token 数
        min_tokens: 最小 token 阈值，低于此值的 chunk 会被合并
        separator: 合并时的文本分隔符

    Returns:
        (merged_chunks, merged_relations)
    """
    if len(chunks) <= 1:
        return chunks, relations

    # 第一遍：合并短文本 chunk
    merged: list[Chunk] = []
    skip_indices: set[int] = set()

    i = 0
    while i < len(chunks):
        if i in skip_indices:
            i += 1
            continue

        chunk = chunks[i]

        # 非文本 chunk 不参与合并
        if chunk.chunk_type != "text":
            merged.append(chunk)
            i += 1
            continue

        current_tokens = chunk.tokens or estimate_tokens(chunk.content)
        current_text = chunk.content

        # 如果当前 chunk 已达到目标，直接保留
        if current_tokens >= target_tokens:
            merged.append(chunk)
            i += 1
            continue

        # 向前合并后续短 chunk
        j = i + 1
        while j < len(chunks) and current_tokens < target_tokens:
            next_chunk = chunks[j]

            # 跳过非文本 chunk（它们不参与合并，但也不阻断合并）
            if next_chunk.chunk_type != "text":
                j += 1
                continue

            combined = current_text + separator + next_chunk.content
            combined_tokens = estimate_tokens(combined)

            if combined_tokens <= target_tokens:
                # 合并
                current_text = combined
                current_tokens = combined_tokens
                skip_indices.add(j)
                j += 1
            else:
                # 如果当前 chunk 太小且下一个太大，仍然强制合并
                if current_tokens < min_tokens:
                    current_text = combined
                    current_tokens = combined_tokens
                    skip_indices.add(j)
                # 否则停止合并
                break

        # 创建合并后的 chunk（保留第一个 chunk 的元数据）
        merged_chunk = Chunk(
            id=chunk.id,
            content=current_text,
            content_with_weight=current_text,  # enrich 阶段会重新计算
            title=chunk.title,
            chunk_type="text",
            page_range=_merge_page_ranges(chunk, chunks, i, j - 1 if j > i + 1 else i),
            tokens=current_tokens,
            metadata={**chunk.metadata},
        )
        merged.append(merged_chunk)
        i = j if j > i + 1 else i + 1

    # 第二遍：重建 ID 和关系
    for idx, chunk in enumerate(merged):
        doc_id = chunk.metadata.get("file_name", chunk.metadata.get("doc_id", "unknown"))
        chunk.id = generate_chunk_id(str(doc_id), idx)
        chunk.tokens = estimate_tokens(chunk.content)

    new_relations = _rebuild_relations(merged)

    if len(merged) < len(chunks):
        logger.info(
            f"merge_chunks: {len(chunks)} → {len(merged)} chunks "
            f"(target={target_tokens} tokens)"
        )

    return merged, new_relations


def _merge_page_ranges(
    first_chunk: Chunk,
    chunks: list[Chunk],
    start_idx: int,
    end_idx: int,
) -> tuple[int, int] | None:
    """合并多个 chunk 的 page_range。"""
    ranges = []
    for idx in range(start_idx, min(end_idx + 1, len(chunks))):
        pr = chunks[idx].page_range
        if pr:
            ranges.append(pr)
    if not ranges:
        return first_chunk.page_range
    return (ranges[0][0], ranges[-1][1])


def _rebuild_relations(chunks: list[Chunk]) -> list[ChunkRelation]:
    """合并后重建相邻关系。"""
    relations = []
    for i in range(len(chunks)):
        rel = ChunkRelation(
            prev_id=chunks[i - 1].id if i > 0 else None,
            next_id=chunks[i + 1].id if i < len(chunks) - 1 else None,
        )
        relations.append(rel)
    return relations
