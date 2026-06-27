"""CitationInserter — 引用插入 + 位置单调约束。

借鉴 RAGFlow 的 insert_citations 思路：
    1. 将 LLM 生成的答案拆为句子
    2. 每句 embedding 与检索 chunks 计算相似度
    3. 超过阈值(0.6)的标注引用
    4. 位置单调约束：引用序号只增不减

架构师建议：
    加入位置约束，防止 LLM 为了凑引用交叉乱标。
"""

import re

from common import get_logger
from llm import BaseEmbedding
from .models import ScoredChunk

logger = get_logger(__name__)

# 相似度阈值
_CITATION_THRESHOLD = 0.6

# 句子分割正则（中英文）
_SENTENCE_PATTERN = re.compile(r"[^。！？.!?\n]+[。！？.!?\n]?")


class CitationInserter:
    """引用插入器。

    对 LLM 答案进行后处理，为每个句子标注文献来源。
    """

    def __init__(self, embedding: BaseEmbedding):
        self._embedding = embedding

    async def insert(
        self,
        answer: str,
        chunks: list[ScoredChunk],
        threshold: float = _CITATION_THRESHOLD,
    ) -> tuple[str, list[dict]]:
        """为答案插入引用标记。

        Args:
            answer: LLM 生成的答案文本
            chunks: 检索到的文档 chunks
            threshold: 引用相似度阈值

        Returns:
            (带引用标记的答案, 引用列表 [{chunk_id, sentence_idx, score}])
        """
        if not chunks or not answer.strip():
            return answer, []

        # Step 1: 分句
        sentences = _split_sentences(answer)
        if len(sentences) <= 1:
            return answer, []

        # Step 2: 每句 embed
        sentence_data = []  # (text, vec) pairs
        for sent in sentences:
            try:
                vec = await self._embedding.embed_query(sent)
                sentence_data.append((sent, vec))
            except Exception:
                sentence_data.append((sent, None))

        # Step 3: 相似度匹配 + 位置单调约束（基于文档原始位置）
        citations = []
        cited_chunks: set[str] = set()

        # 为每个 chunk 计算文档原始位置序号（按 page_range 排序）
        # 无 page_range 的排在最后
        doc_order_map = _build_doc_order(chunks)
        last_doc_order = -1

        for sent_idx, (sent_text, sent_vec) in enumerate(sentence_data):
            if sent_vec is None:
                continue

            best_chunk = None
            best_score = 0.0

            for chunk in chunks:
                if chunk.chunk_id in cited_chunks:
                    continue
                score = self._similarity(sent_vec, sent_text, chunk)
                if score is None or score < threshold:
                    continue
                # 位置单调约束：优先选择文档位置在上一引用之后的 chunk
                # 若都在之前，放宽约束取最相似者
                chunk_doc_order = doc_order_map.get(chunk.chunk_id, 9999)
                respects_order = chunk_doc_order >= last_doc_order

                if score > best_score:
                    if best_chunk is None or respects_order:
                        best_chunk = chunk
                        best_score = score
                elif score == best_score and respects_order:
                    best_chunk = chunk

            if best_chunk:
                citations.append({
                    "chunk_id": best_chunk.chunk_id,
                    "sentence_idx": sent_idx,
                    "score": round(best_score, 3),
                    "source_file": best_chunk.source_file,
                })
                cited_chunks.add(best_chunk.chunk_id)
                last_doc_order = doc_order_map.get(best_chunk.chunk_id, 9999)

        # Step 4: 在句子末尾插入引用标记
        result_sentences = []
        cite_map = {c["sentence_idx"]: i + 1 for i, c in enumerate(citations)}

        for i, sent in enumerate(sentences):
            if i in cite_map:
                sent = f"{sent.rstrip()} [{cite_map[i]}]"
            result_sentences.append(sent)

        return "".join(result_sentences), citations

    def _similarity(
        self, sent_vec: list[float], sent_text: str, chunk: ScoredChunk
    ) -> float | None:
        """计算句子与 chunk 的相似度。

        优先使用 chunk 预计算的 _embedding 做余弦相似度；
        若无 _embedding（如 sparse 检索结果），降级为文本重叠度。
        """
        chunk_emb = chunk.metadata.get("_embedding")
        if chunk_emb is not None and len(sent_vec) == len(chunk_emb):
            return _cosine(sent_vec, chunk_emb)
        # 降级：文本重叠度（Jaccard-like）
        return _text_overlap(sent_text, chunk)


def _split_sentences(text: str) -> list[str]:
    """中英文分句。"""
    sentences = _SENTENCE_PATTERN.findall(text)
    if not sentences:
        return [text]
    # 合并过短的句子
    result = []
    i = 0
    while i < len(sentences):
        sent = sentences[i]
        # 与后续短句合并
        j = i + 1
        while j < len(sentences) and len(sent) < 10:
            sent += sentences[j]
            j += 1
        result.append(sent.strip())
        i = j
    return result if result else [text]


def _cosine(vec_a: list[float], vec_b: list[float]) -> float:
    """余弦相似度。"""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _text_overlap(sent_text: str, chunk) -> float:
    """文本重叠度降级匹配 — 当 chunk 无 _embedding 时使用。

    用句子文本与 chunk 内容的字符级 Jaccard 系数近似语义相关性。
    分词：中文按 bigram 切分，英文按空格分词。
    """
    content = chunk.content or ""
    if not content.strip() or not sent_text.strip():
        return 0.0

    # 使用字符 bigram 作为特征集（兼容中英文混合）
    def _bigrams(text: str) -> set[str]:
        chars = text.replace(" ", "").replace("\n", "")
        if len(chars) < 2:
            return {chars} if chars else set()
        return {chars[i:i + 2] for i in range(len(chars) - 1)}

    sent_bigrams = _bigrams(sent_text)
    chunk_bigrams = _bigrams(content)

    if not sent_bigrams or not chunk_bigrams:
        return 0.0

    intersection = sent_bigrams & chunk_bigrams
    union = sent_bigrams | chunk_bigrams
    if not union:
        return 0.0

    return len(intersection) / len(union)


def _build_doc_order(chunks: list) -> dict[str, int]:
    """按文档原始位置为每个 chunk 分配顺序号。

    排序依据: page_range.start → page_range.end → chunk_id（稳定排序）。
    无 page_range 的排最后。
    """
    def _key(c):
        pr = c.page_range
        if pr:
            return (0, pr[0], pr[1])
        return (1, 0, 0)

    sorted_chunks = sorted(chunks, key=_key)
    return {c.chunk_id: i for i, c in enumerate(sorted_chunks)}

