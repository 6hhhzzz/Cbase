"""三层去重 + 相邻合并 — 检索后、Reranker 前的去重管道。

从 orchestrator.py 提取，纯数据转换函数，仅依赖 ScoredChunk 数据类。
"""

from common import get_logger
from .models import ScoredChunk

logger = get_logger(__name__)


def merge_dedup(chunks: list[ScoredChunk]) -> list[ScoredChunk]:
    """合并去重 — 相同 chunk_id 只保留第一次命中。

    保持原始顺序（先出现的子查询结果优先）。
    """
    seen: set[str] = set()
    unique: list[ScoredChunk] = []
    for c in chunks:
        if c.chunk_id not in seen:
            seen.add(c.chunk_id)
            unique.append(c)
    return unique


def dedup_chunks(chunks: list[ScoredChunk]) -> list[ScoredChunk]:
    """Chunk 内容去重 — 前 300 字符相同的只保留最高分。

    解决分块重叠导致不同 chunk_id 但内容相同的重复召回。
    """
    best: dict[str, ScoredChunk] = {}
    for c in chunks:
        key = (c.content or "")[:300].strip()
        if key not in best or c.score > best[key].score:
            best[key] = c
    result = sorted(best.values(), key=lambda x: x.score, reverse=True)
    removed = len(chunks) - len(result)
    if removed:
        logger.debug(f"Chunk 去重: {len(chunks)} → {len(result)} (移除 {removed} 条)")
    return result


def dedup_docs(chunks: list[ScoredChunk], max_per_doc: int = 3) -> list[ScoredChunk]:
    """文档去重 — 同一文档最多保留 top-N 条 chunk。

    按 doc_id（metadata 中）或 source_file 分组，每组按分数降序取前 N。
    """
    groups: dict[str, list[ScoredChunk]] = {}
    for c in chunks:
        doc_key = (c.metadata or {}).get("doc_id") or c.source_file or "_unknown"
        if doc_key not in groups:
            groups[doc_key] = []
        groups[doc_key].append(c)

    result = []
    for doc_chunks in groups.values():
        doc_chunks.sort(key=lambda x: x.score, reverse=True)
        result.extend(doc_chunks[:max_per_doc])
    result.sort(key=lambda x: x.score, reverse=True)
    removed = len(chunks) - len(result)
    if removed:
        logger.debug(f"文档去重: {len(chunks)} → {len(result)} (移除 {removed} 条, {len(groups)} 文档)")
    return result


def merge_adjacent(chunks: list[ScoredChunk]) -> list[ScoredChunk]:
    """相邻 Chunk 合并 — 同文档、chunk_index 连续的合并 content，取平均分。

    仅当 metadata 中有 doc_id 和 chunk_index 时生效。
    """
    if not chunks:
        return chunks

    # 检查是否有 chunk_index 可用
    has_index = any(
        "chunk_index" in (c.metadata or {}) for c in chunks[:3]
    )
    if not has_index:
        return chunks

    # 按 (doc_id, chunk_index) 排序
    def _sort_key(c):
        m = c.metadata or {}
        return (m.get("doc_id", ""), m.get("chunk_index", 0))

    sorted_chunks = sorted(chunks, key=_sort_key)
    merged = []
    i = 0
    while i < len(sorted_chunks):
        c = sorted_chunks[i]
        m = c.metadata or {}
        doc_id = m.get("doc_id", "")
        ci = m.get("chunk_index", -1)

        # 向后查找同文档相邻 chunk
        j = i + 1
        while j < len(sorted_chunks):
            nm = sorted_chunks[j].metadata or {}
            if (nm.get("doc_id", "") == doc_id
                    and nm.get("chunk_index", -1) == ci + (j - i)):
                j += 1
            else:
                break

        if j > i + 1:
            # 合并 i..j-1
            merged_content = "\n".join(
                sorted_chunks[k].content for k in range(i, j)
            )
            avg_score = sum(sorted_chunks[k].score for k in range(i, j)) / (j - i)
            merged_chunk = ScoredChunk(
                chunk_id=c.chunk_id,
                content=merged_content,
                score=avg_score,
                source_file=c.source_file,
                metadata=c.metadata,
            )
            merged.append(merged_chunk)
        else:
            merged.append(c)
        i = j

    merged.sort(key=lambda x: x.score, reverse=True)
    removed = len(chunks) - len(merged)
    if removed:
        logger.debug(f"相邻合并: {len(chunks)} → {len(merged)} (合并 {removed} 条)")
    return merged
