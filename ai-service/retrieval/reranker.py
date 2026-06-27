"""Reranker — 交叉编码器重排序 + LLM 降级。

优先使用 BGE-Reranker 等交叉编码器（精度高），
无 GPU 时降级使用 LLM-based Reranker。
"""

from common import get_logger
from llm.rerank_llm import LLMReranker
from .models import ScoredChunk

logger = get_logger(__name__)

# 默认 Cross-Encoder 模型（开发阶段硬编码，后续由配置中心接管）
_DEFAULT_CE_MODEL = "BAAI/bge-reranker-v2-m3"


def create_reranker(llm=None) -> "Reranker":
    """创建 Reranker 实例，自动尝试加载默认 Cross-Encoder。

    加载顺序：
        1. 尝试加载 sentence-transformers CrossEncoder（BGE-Reranker-v2-m3）
        2. 失败则降级为纯 LLM Reranker
        3. LLM 也不可用时，仅做截断

    后续可通过配置中心覆盖 cross_encoder 参数。
    """
    cross_encoder = _load_default_cross_encoder()
    return Reranker(llm=llm, cross_encoder=cross_encoder)


def _load_default_cross_encoder():
    """加载默认 Cross-Encoder 模型。开发阶段硬编码模型名。"""
    try:
        from sentence_transformers import CrossEncoder
        model = CrossEncoder(_DEFAULT_CE_MODEL)
        logger.info(f"Cross-Encoder 加载成功: {_DEFAULT_CE_MODEL}")
        return model
    except ImportError:
        logger.warning(
            "sentence-transformers 未安装，Cross-Encoder 不可用，"
            "降级使用 LLM Reranker。安装: pip install sentence-transformers"
        )
    except Exception as e:
        logger.warning(f"Cross-Encoder 加载失败 ({e})，降级使用 LLM Reranker")
    return None


class Reranker:
    """重排序器。

    策略：
        1. 优先 BGE-Reranker-v2-m3 等交叉编码器
        2. 降级 LLM-based Reranker
        3. 兜底：直接截断返回

    用法::

        reranker = Reranker(llm=llm, cross_encoder=model)
        top_k = await reranker.rerank(query, candidates, top_n=5)
    """

    def __init__(self, llm=None, cross_encoder=None):
        """
        Args:
            llm: BaseLLM 实例（用于 LLM 降级 rerank）
            cross_encoder: 交叉编码器模型，需实现 predict([[query, text]]) 接口
        """
        self._cross_encoder = cross_encoder
        self._llm_reranker = LLMReranker(llm) if llm else None

    async def rerank(
        self,
        query: str,
        candidates: list[ScoredChunk],
        top_n: int = 5,
    ) -> list[ScoredChunk]:
        """重排序候选文档。

        Args:
            query: 用户查询
            candidates: 候选文档列表
            top_n: 最终返回数量

        Returns:
            重排后的 Top-N 结果
        """
        if not candidates:
            return []

        if len(candidates) <= top_n:
            return candidates

        # 策略 1: 交叉编码器
        if self._cross_encoder:
            try:
                return await self._rerank_with_cross_encoder(query, candidates, top_n)
            except Exception as e:
                logger.warning(f"Cross-encoder rerank 失败，降级: {e}")

        # 策略 2: LLM 降级
        if self._llm_reranker:
            try:
                return await self._rerank_with_llm(query, candidates, top_n)
            except Exception as e:
                logger.warning(f"LLM rerank 失败，降级截断: {e}")

        # 策略 3: 兜底直接截断
        return sorted(candidates, key=lambda x: x.score, reverse=True)[:top_n]

    async def _rerank_with_cross_encoder(
        self, query: str, candidates: list[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        """使用交叉编码器重排序。"""
        pairs = [[query, c.content] for c in candidates]
        scores = self._cross_encoder.predict(pairs)

        for c, score in zip(candidates, scores):
            if isinstance(score, (list, tuple)):
                c.score = float(score[0])
            else:
                c.score = float(score)

        return sorted(candidates, key=lambda x: x.score, reverse=True)[:top_n]

    async def _rerank_with_llm(
        self, query: str, candidates: list[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        """使用 LLM 降级重排序。"""
        docs = [{"id": c.chunk_id, "content": c.content} for c in candidates]
        reranked = await self._llm_reranker.rerank(query, docs)

        # 合并回 ScoredChunk
        score_map = {d["id"]: d.get("score", 50) for d in reranked}
        for c in candidates:
            c.score = score_map.get(c.chunk_id, c.score)

        return sorted(candidates, key=lambda x: x.score, reverse=True)[:top_n]
