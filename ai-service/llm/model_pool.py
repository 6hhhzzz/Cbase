"""ModelPool — 动态模型池（v2 配置文件驱动）。

启动时从 config/models.yaml 加载全部配置，构建 LLM/Embedding/Reranker 实例池。
支持热重载：每 30 秒检查文件 mtime，变化时自动重建实例。
HTTP 从 Java 拉取配置保留为降级路径。

用法::

    pool = ModelPool()
    await pool.initialize()

    chat_llm = pool.get_llm("chat")       # 对话生成
    slm = pool.get_slm()                   # SLM（轻量小模型）
    embedding = pool.get_embedding()       # 向量嵌入
    reranker = pool.get_reranker()         # 重排序

    # 后台热重载
    await pool.start_watch()
"""

import asyncio
from pathlib import Path
from typing import Any

from common import get_logger
from llm.base import BaseLLM, BaseEmbedding
from llm.model_factory import (
    create_llm_instance, create_embedding_instance,
    create_cross_encoder, create_api_reranker, create_api_ocr_instance,
    create_llm_from_dict, create_embedding_from_dict,
)
from llm.config_watcher import ConfigWatcher

logger = get_logger(__name__)

# 配置文件路径
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "models.yaml"


class ModelPool:
    """动态模型池（v2 配置文件驱动）。

    从 config/models.yaml 加载配置，按 purpose 管理模型实例。
    HTTP 拉取保留为降级路径。
    """

    def __init__(self, java_base_url: str = ""):
        self._java_url = java_base_url.rstrip("/") if java_base_url else ""
        self._instances: dict[str, BaseLLM] = {}
        self._embedding: BaseEmbedding | None = None
        self._reranker = None  # Reranker instance
        self._ocr = None
        self._ocr = None       # OCR engine (APIOCR)
        self._fallback_chains: dict[str, list[str]] = {}
        self._config_mtime: float = 0
        self._lock = asyncio.Lock()

    # ============================================================
    # 初始化
    # ============================================================

    async def initialize(self) -> None:
        """加载配置并构建模型池。优先本地文件，降级 HTTP。"""
        try:
            config = self._load_from_file()
            self._build_pool(config)
            logger.info(
                f"ModelPool 初始化完成 (本地文件): {len(self._instances)} LLMs, "
                f"embedding={self._embedding is not None}"
            )
        except FileNotFoundError:
            logger.info("models.yaml 不存在，尝试从 Java 后端拉取配置")
            if self._java_url:
                await self._initialize_from_http()
            else:
                raise
        except Exception as e:
            logger.warning(f"从 models.yaml 加载失败 ({e})，尝试降级")
            if self._java_url:
                await self._initialize_from_http()
            else:
                raise

    async def _initialize_from_http(self) -> None:
        """HTTP 降级：从 Java 后端拉取配置。"""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self._java_url}/api/admin/models/active")
                resp.raise_for_status()
                data = resp.json()
                configs = data.get("data", data)
                self._build_pool_from_http(configs)
                logger.info(f"ModelPool 初始化完成 (HTTP): {len(self._instances)} LLMs")
        except Exception as e:
            logger.error(f"ModelPool HTTP 初始化也失败: {e}")
            raise

    # ============================================================
    # 配置加载
    # ============================================================

    @staticmethod
    def _load_from_file():
        """从 models.yaml 加载配置（Pydantic 校验）。"""
        from core.config.models_config import load_models_config, resolve_fallback_chain
        config = load_models_config()
        return config, resolve_fallback_chain(config)

    def _build_pool(self, loaded: tuple) -> None:
        """根据 ModelsConfig + fallback_chains 构建实例。"""
        config, fallback_chains = loaded
        self._instances.clear()
        self._embedding = None
        self._reranker = None
        self._fallback_chains = fallback_chains

        # 收集 Reranker 降级链各组件（避免后续 assignment 覆盖前面的）
        _api_reranker = None       # APIReranker 实例（DashScope gte-rerank）
        _cross_encoder = None      # CrossEncoder 模型（本地 BGE-Reranker）

        for purpose, assignment in config.assignments.items():
            model_key = assignment.model
            model = config.models.get(model_key)
            if not model:
                logger.warning(f"环节 '{purpose}' 引用的模型 '{model_key}' 未定义，跳过")
                continue

            provider = config.providers.get(model.provider)
            if not provider:
                logger.warning(f"模型 '{model_key}' 的供应商 '{model.provider}' 未定义，跳过")
                continue

            logger.info(f"ModelPool: {purpose} → {provider.type}:{model.model_name} ({model.model_type})")

            model_type = model.model_type
            provider_type = provider.type

            if model_type in ("chat",):
                # chat/SLM: 必须通过 API 调用
                if provider_type == "local":
                    logger.error(
                        f"环节 '{purpose}': chat 模型不支持 local provider。"
                        f"如需本地 LLM，请使用 ollama 类型。"
                    )
                    continue
                self._instances[purpose] = self._create_llm_instance(provider, model)

            elif model_type == "embedding":
                # embedding: 必须通过 API 调用
                if provider_type == "local":
                    logger.error("embedding 模型不支持 local provider")
                    continue
                self._embedding = self._create_embedding_instance(provider, model)

            elif model_type == "reranker":
                if provider_type == "local":
                    _cross_encoder = self._create_cross_encoder(model)
                elif provider_type == "openai_compatible":
                    _api_reranker = self._create_api_reranker(provider, model)
                else:
                    logger.warning(f"不支持 Reranker provider 类型: {provider_type}，将降级")

            elif model_type == "ocr":
                if provider_type == "openai_compatible":
                    try:
                        self._ocr = self._create_api_ocr_instance(provider, model)
                    except Exception as e:
                        logger.warning(f"OCR 初始化失败 ({e})，OCR 功能不可用")
                        self._ocr = None
                else:
                    logger.warning(f"OCR 仅支持 openai_compatible provider，当前: {provider_type}")
                    self._ocr = None

        # 构建完整 Reranker 降级链 (API → Cross-Encoder → LLM)
        if _api_reranker or _cross_encoder:
            from retrieval.reranker import Reranker
            rerank_llm = self._instances.get("rerank_llm") or self._instances.get("slm")
            self._reranker = Reranker(
                llm=rerank_llm,
                cross_encoder=_cross_encoder,
                api_reranker=_api_reranker,
            )
            strategies = []
            if _api_reranker: strategies.append("API")
            if _cross_encoder: strategies.append("Cross-Encoder")
            if rerank_llm: strategies.append("LLM")
            logger.info(f"Reranker 降级链已构建: {' → '.join(strategies)}")
        else:
            # 未配置任何 reranker → 降级纯 LLM Reranker
            rerank_llm = self._instances.get("rerank_llm") or self._instances.get("slm")
            if rerank_llm:
                from retrieval.reranker import create_reranker
                self._reranker = create_reranker(llm=rerank_llm)
                logger.info("Reranker 降级: 使用 LLM Reranker")

    def _build_pool_from_http(self, configs: dict) -> None:
        """HTTP 降级：兼容旧的 Java API 响应格式。"""
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
            logger.info(f"ModelPool(HTTP): {purpose} → {provider['name']}:{model['model_name']} ({model_type})")

            if model_type == "chat":
                self._instances[purpose] = create_llm_from_dict(provider, model)
            elif model_type == "embedding":
                self._embedding = create_embedding_from_dict(provider, model)

        # 降级链回退到硬编码列表
        self._fallback_chains = {}
        if self._reranker is None and "rerank_llm" in self._instances:
            from retrieval.reranker import create_reranker
            self._reranker = create_reranker(llm=self._instances["rerank_llm"])

    # ============================================================
    # 工厂方法（委托给 model_factory 模块）
    # ============================================================

    def _create_llm_instance(self, provider, model) -> BaseLLM:
        return create_llm_instance(provider, model)

    def _create_embedding_instance(self, provider, model) -> BaseEmbedding:
        return create_embedding_instance(provider, model)

    def _create_cross_encoder(self, model):
        return create_cross_encoder(model)

    def _create_api_reranker(self, provider, model):
        return create_api_reranker(provider, model)

    def _create_api_ocr_instance(self, provider, model):
        return create_api_ocr_instance(provider, model)

    def get_ocr(self):
        """获取 OCR 引擎（云端 API 优先）。"""
        return self._ocr

    # ============================================================
    # 获取模型实例
    # ============================================================

    def get_llm(self, purpose: str) -> BaseLLM:
        """按环节获取 LLM。降级链从配置文件 fallback 字段解析。"""
        if purpose in self._instances:
            return self._instances[purpose]

        # 从配置的降级链找
        chain = self._fallback_chains.get(purpose, [])
        for fallback in chain[1:]:  # 跳过 purpose 自身
            if fallback in self._instances:
                logger.warning(f"未配置 {purpose} LLM，降级使用 {fallback}")
                return self._instances[fallback]

        # 最后尝试 chat
        if "chat" in self._instances:
            logger.warning(f"未配置 {purpose} LLM，降级使用 chat")
            return self._instances["chat"]

        raise ValueError(f"未配置任何可用 LLM，purpose={purpose}")

    def get_slm(self) -> BaseLLM:
        """获取 SLM。先查 slm，没配则降级到 chat。"""
        return self.get_llm("slm")

    def get_embedding(self) -> BaseEmbedding:
        if self._embedding is None:
            raise ValueError("Embedding 模型未配置")
        return self._embedding

    def get_reranker(self):
        return self._reranker

    @property
    def embedding_dimension(self) -> int:
        if self._embedding is not None:
            return self._embedding.get_dimension()
        return 1024

    # ============================================================
    # 热重载（委托给 ConfigWatcher）
    # ============================================================

    async def start_watch(self, interval: int = 30) -> None:
        """后台热重载：每 N 秒检查 models.yaml 的 mtime。"""
        async def _reload():
            config = self._load_from_file()
            self._build_pool(config)

        self._watcher = ConfigWatcher(DEFAULT_CONFIG_PATH, _reload)
        asyncio.create_task(self._watcher.watch_loop(interval))
        logger.info(f"ModelPool 热重载已启动 (文件监控, interval={interval}s)")

    # ============================================================
    # 调试
    # ============================================================

    def get_pool_info(self) -> dict[str, Any]:
        """返回当前池状态（调试用）。"""
        return {
            "instances": {p: llm.get_model_name() for p, llm in self._instances.items()},
            "embedding": self._embedding.get_model_name() if self._embedding else None,
            "reranker": "Cross-Encoder" if self._reranker and getattr(self._reranker, '_cross_encoder', None) else ("LLM" if self._reranker else None),
            "fallback_chains": self._fallback_chains,
        }


# ================================================================
# HTTP 降级工厂函数已迁移至 llm/model_factory.py
# (create_llm_from_dict, create_embedding_from_dict, _resolve_api_key, _resolve_key_from_dict)
# ================================================================
