"""ModelPool — 动态模型池，替代 ModelFactory。

启动时从 Java 后端拉取全量配置，构建 LLM/Embedding/Reranker 实例池。
支持热重载：每 30 秒检查 config_version 变化，自动重建实例。

用法::

    pool = ModelPool(java_base_url="http://localhost:8080")
    await pool.initialize()

    chat_llm = pool.get_llm("chat")       # 对话生成
    rewrite_llm = pool.get_llm("rewrite") # Query 改写
    intent_llm = pool.get_llm("intent")   # 意图分类
    embedding = pool.get_embedding()       # 向量嵌入
    reranker = pool.get_reranker()         # 重排序

    # 后台热重载
    await pool.start_watch()
"""

import asyncio
import json
import os

import httpx

from common import get_logger
from llm.base import BaseLLM, BaseEmbedding
from llm.openai_compatible import OpenAICompatibleLLM, OpenAICompatibleEmbedding

logger = get_logger(__name__)

_PURPOSE_ORDER = ["chat", "rewrite", "intent", "rerank_llm"]  # 降级顺序


class ModelPool:
    """动态模型池。

    从 Java 后端 GET /api/admin/models/active 获取配置，
    按 purpose 管理 LLM/Embedding/Reranker 实例。
    """

    def __init__(self, java_base_url: str):
        self._java_url = java_base_url.rstrip("/")
        self._instances: dict[str, BaseLLM] = {}
        self._embedding: BaseEmbedding | None = None
        self._reranker = None  # Reranker instance
        self._config_version: int = 0
        self._lock = asyncio.Lock()

    # ============================================================
    # 初始化
    # ============================================================

    async def initialize(self) -> None:
        """启动时从 Java 拉取配置并构建模型池。"""
        try:
            configs = await self._fetch_active_configs()
            self._build_pool(configs)
            logger.info(
                f"ModelPool 初始化完成: {len(self._instances)} LLMs, "
                f"embedding={self._embedding is not None}"
            )
        except Exception as e:
            logger.error(f"ModelPool 初始化失败: {e}")
            raise

    async def _fetch_active_configs(self) -> dict:
        """GET /api/admin/models/active。"""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self._java_url}/api/admin/models/active")
            resp.raise_for_status()
            data = resp.json()
            # ApiResponse 解包
            return data.get("data", data)

    def _build_pool(self, configs: dict) -> None:
        """根据配置构建所有模型实例。"""
        # 清空旧实例
        self._instances.clear()
        self._embedding = None
        self._reranker = None

        assignments = configs.get("assignments", [])
        for assignment in assignments:
            purpose = assignment.get("purpose", "")
            model = assignment.get("model")
            provider = assignment.get("provider")

            if not model or not provider:
                continue

            model_type = model.get("model_type", "")
            logger.info(f"ModelPool: {purpose} → {provider['name']}:{model['model_name']} ({model_type})")

            if model_type == "chat":
                self._instances[purpose] = _create_llm(provider, model)
            elif model_type == "embedding":
                self._embedding = _create_embedding(provider, model)
            elif model_type == "reranker":
                self._reranker = _create_reranker_from_config(provider, model)

        # 如果未配置 reranker，使用默认 Cross-Encoder + LLM 降级
        if self._reranker is None and "rerank_llm" in self._instances:
            from retrieval.reranker import create_reranker
            self._reranker = create_reranker(llm=self._instances["rerank_llm"])

    # ============================================================
    # 获取模型实例
    # ============================================================

    def get_llm(self, purpose: str) -> BaseLLM:
        """按用途获取 LLM。降级链: purpose → chat → 抛异常。"""
        if purpose in self._instances:
            return self._instances[purpose]

        # 降级：找列表中最接近的
        for fallback in _PURPOSE_ORDER:
            if fallback in self._instances and fallback != purpose:
                logger.warning(f"未配置 {purpose} LLM，降级使用 {fallback}")
                return self._instances[fallback]

        raise ValueError(f"未配置任何 LLM，purpose={purpose}")

    def get_embedding(self) -> BaseEmbedding:
        """获取 Embedding 模型。"""
        if self._embedding is None:
            raise ValueError("Embedding 模型未配置")
        return self._embedding

    def get_reranker(self):
        """获取 Reranker（可能为 None）。"""
        return self._reranker

    @property
    def embedding_dimension(self) -> int:
        """当前 embedding 模型的维度。"""
        if self._embedding is not None:
            return self._embedding.get_dimension()
        return 1024

    # ============================================================
    # 热重载
    # ============================================================

    async def start_watch(self, interval: int = 30) -> None:
        """后台任务：定时检查配置版本号，变更时自动热重载。"""
        asyncio.create_task(self._watch_loop(interval))
        logger.info(f"ModelPool 热重载监控已启动 (interval={interval}s)")

    async def _watch_loop(self, interval: int) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                new_version = await self._fetch_config_version()
                if new_version > self._config_version:
                    logger.info(
                        f"检测到配置变更 (v{self._config_version} → v{new_version})，热重载中..."
                    )
                    configs = await self._fetch_active_configs()
                    async with self._lock:
                        self._config_version = new_version
                        self._build_pool(configs)
                    logger.info("ModelPool 热重载完成")
            except Exception as e:
                logger.warning(f"ModelPool 热重载检查失败: {e}")

    async def _fetch_config_version(self) -> int:
        """GET /api/admin/models/version。"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{self._java_url}/api/admin/models/version")
            data = resp.json().get("data", resp.json())
            return int(data.get("version", 0))


# ================================================================
# 工厂函数
# ================================================================

def _create_llm(provider: dict, model: dict) -> BaseLLM:
    """根据 provider 类型创建 LLM 实例。"""
    ptype = provider.get("type", "")
    api_key = _resolve_key(provider)
    base_url = provider.get("base_url", "")
    model_name = model.get("model_name", "")

    if ptype in ("openai_compatible",):
        from models.config import LLMConfig
        config = LLMConfig(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            default_params={"temperature": 0.3, "max_tokens": model.get("max_tokens", 2048)},
        )
        return OpenAICompatibleLLM(config)
    raise ValueError(f"不支持的 provider 类型: {ptype}")


def _create_embedding(provider: dict, model: dict) -> BaseEmbedding:
    """根据 provider 类型创建 Embedding 实例。"""
    ptype = provider.get("type", "")
    api_key = _resolve_key(provider)
    base_url = provider.get("base_url", "")
    model_name = model.get("model_name", "")

    if ptype in ("openai_compatible",):
        from models.config import EmbeddingConfig
        config = EmbeddingConfig(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            dimension=model.get("dimension", 1024),
        )
        return OpenAICompatibleEmbedding(config)
    raise ValueError(f"不支持的 embedding provider: {ptype}")


def _create_reranker_from_config(provider: dict, model: dict):
    """根据 provider 类型创建 Reranker 实例。"""
    from retrieval.reranker import Reranker
    llm = _create_llm(provider, model)
    return Reranker(llm=llm)


def _resolve_key(provider: dict) -> str:
    """解析 API Key：环境变量 / .secret 文件。

    优先级：
        1. .secret/providers/{name}.json 文件中的 api_key
        2. os.environ[API_KEY_ENV]
    """
    env_var = provider.get("api_key_env") or ""
    if not env_var and "api_key" in provider:
        return provider["api_key"]  # /active 端点的直接传 key

    var_name = env_var.replace("${", "").replace("}", "")
    if not var_name:
        return ""

    # 1. 尝试本地配置文件
    secret_path = os.path.join(
        os.path.dirname(__file__), "..", "..", ".secret",
        "providers", f"{provider.get('name', 'unknown')}.json"
    )
    try:
        with open(os.path.normpath(secret_path)) as f:
            secret_data = json.load(f)
            if secret_data.get("api_key"):
                return secret_data["api_key"]
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # 2. 环境变量
    return os.environ.get(var_name, "")
