"""Reranker — DashScope API（优先）→ Cross-Encoder（本地）→ LLM 降级。

策略链:
  1. APIReranker — 调 DashScope gte-rerank 云端 API（快、便宜）
  2. CrossEncoder — 本地 BGE-Reranker（GPU 加速）
  3. LLMReranker — LLM 降级打分
  4. 直接截断 — 按原始 RRF 分数
"""

import httpx

from common import get_logger
from llm.rerank_llm import LLMReranker
from .models import ScoredChunk

logger = get_logger(__name__)


class APIReranker:
    """云端 Rerank API 调用（DashScope gte-rerank 等）。

    用法::

        reranker = APIReranker(
            api_key="sk-xxx",
            api_path="/api/v1/services/rerank/text-rerank/text-rerank",
            model_name="gte-rerank",
            base_url="https://your-rerank-api.example.com",
        )
        top_k = await reranker.rerank(query, documents_dicts, top_n=5)
    """

    def __init__(self, api_key: str, base_url: str, api_path: str = "",
                 model_name: str = "gte-rerank", timeout: float = 30.0):
        self._api_key = api_key
        self._model_name = model_name
        self._url = f"{base_url.rstrip('/')}{api_path}" if (base_url and api_path) else ""
        self._available = bool(self._api_key and self._url)
        self._timeout = timeout

    @property
    def is_available(self) -> bool:
        return self._available

    async def rerank(
        self,
        query: str,
        documents: list[dict],
        top_n: int = 5,
    ) -> list[dict]:
        """调云端 Rerank API 重排序。

        Args:
            query: 查询文本
            documents: [{"id": ..., "content": ...}, ...]
            top_n: 返回数量

        Returns:
            带 score 字段的文档列表，按分数降序
        """
        if not self._available or not documents:
            return documents

        docs_text = [d["content"] for d in documents]
        payload = {
            "model": self._model_name,
            "input": {
                "query": query,
                "documents": docs_text,
            },
            "parameters": {"top_n": min(top_n, len(documents))},
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    self._url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code != 200:
                    logger.warning(f"Rerank API 返回 {resp.status_code}: {resp.text[:200]}")
                    raise RuntimeError(f"Rerank API error: {resp.status_code}")

                data = resp.json()
                results = data.get("output", {}).get("results", [])

                # 合并分数回 documents
                score_map = {
                    r.get("index", 999): r.get("relevance_score", 0.5)
                    for r in results if "index" in r
                }
                for i, doc in enumerate(documents):
                    doc["score"] = score_map.get(i, 0.5)  # 默认中等分（API 返回 0~1 制）

                documents.sort(key=lambda x: x.get("score", 0), reverse=True)
                logger.debug(f"Rerank API 完成: {len(results)} 条结果, model={self._model_name}")
                return documents

        except Exception as e:
            logger.warning(f"Rerank API 调用失败 ({self._model_name}): {e}")
            raise

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
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = CrossEncoder(_DEFAULT_CE_MODEL, device=device)
        logger.info(f"Cross-Encoder 加载成功: {_DEFAULT_CE_MODEL} (device={device})")
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

    def __init__(self, llm=None, cross_encoder=None, api_reranker=None):
        """
        Args:
            llm: BaseLLM 实例（用于 LLM 降级 rerank）
            cross_encoder: 交叉编码器模型
            api_reranker: APIReranker 实例（DashScope gte-rerank 等云端 API）
        """
        self._api_reranker = api_reranker
        self._cross_encoder = cross_encoder
        self._last_strategy = "unknown"  # trace 用
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

        # 策略 1: 云端 Rerank API（DashScope gte-rerank）
        if self._api_reranker and self._api_reranker.is_available:
            try:
                result = await self._rerank_with_api(query, candidates, top_n)
                self._last_strategy = "api"
                return result
            except Exception as e:
                logger.warning(f"API rerank 失败，降级: {e}")

        # 策略 2: 本地交叉编码器
        if self._cross_encoder:
            try:
                result = await self._rerank_with_cross_encoder(query, candidates, top_n)
                self._last_strategy = "cross_encoder"
                return result
            except Exception as e:
                logger.warning(f"Cross-encoder rerank 失败，降级: {e}")

        # 策略 3: LLM 降级
        if self._llm_reranker:
            try:
                result = await self._rerank_with_llm(query, candidates, top_n)
                self._last_strategy = "llm"
                return result
            except Exception as e:
                logger.warning(f"LLM rerank 失败，降级截断: {e}")

        # 策略 4: 兜底直接截断
        self._last_strategy = "truncation"
        return sorted(candidates, key=lambda x: x.score, reverse=True)[:top_n]

    async def _rerank_with_api(
        self, query: str, candidates: list[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        """使用云端 Rerank API 重排序。"""
        docs = [{"id": c.chunk_id, "content": c.content} for c in candidates]
        reranked = await self._api_reranker.rerank(query, docs, top_n=top_n)
        score_map = {d["id"]: d.get("score", 0.5) for d in reranked}
        for c in candidates:
            c.score = score_map.get(c.chunk_id, c.score)
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
        """使用 LLM 降级重排序。

        LLM prompt 输出 0~100 分数，归一化到 0~1 以与 Cross-Encoder 统一。
        """
        docs = [{"id": c.chunk_id, "content": c.content} for c in candidates]
        reranked = await self._llm_reranker.rerank(query, docs)

        # 合并回 ScoredChunk，归一化到 0~1
        score_map = {d["id"]: d.get("score", 50) for d in reranked}
        for c in candidates:
            raw_score = score_map.get(c.chunk_id, c.score)
            c.score = raw_score / 100.0  # 归一化: 0~100 → 0~1

        return sorted(candidates, key=lambda x: x.score, reverse=True)[:top_n]
