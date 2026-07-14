"""模型工厂 — LLM / Embedding / Reranker / OCR 实例创建。

包含两层工厂：
  - Pydantic 驱动（models.yaml → ProviderConfig / ModelConfig）
  - HTTP 降级（兼容旧版 Java API dict 格式）
"""

import json
import os

from common import get_logger
from llm.base import BaseLLM, BaseEmbedding
from llm.openai_compatible import OpenAICompatibleLLM, OpenAICompatibleEmbedding

logger = get_logger(__name__)


# ================================================================
# Pydantic 驱动工厂（models.yaml）
# ================================================================

def create_llm_instance(provider, model) -> BaseLLM:
    """从 Pydantic ProviderConfig + ModelConfig 创建 LLM 实例。"""
    from models.config import LLMConfig

    api_key = _resolve_api_key(provider)

    timeout = getattr(model, 'timeout', None)
    connect_t = timeout.connect if timeout else 10.0
    read_t = timeout.read if timeout else 60.0
    total_t = timeout.total if timeout else 120.0

    params = dict(getattr(model, 'params', {}) or {})
    params.setdefault("temperature", 0.3)
    params.setdefault("max_tokens", model.max_tokens or 2048)
    params["timeout"] = {"connect": connect_t, "read": read_t, "total": total_t}

    config = LLMConfig(
        model=model.model_name,
        api_key=api_key,
        base_url=provider.base_url,
        default_params=params,
    )
    return OpenAICompatibleLLM(config)


def create_embedding_instance(provider, model) -> BaseEmbedding:
    """从 Pydantic ProviderConfig + ModelConfig 创建 Embedding 实例。"""
    from models.config import EmbeddingConfig

    api_key = _resolve_api_key(provider)
    config = EmbeddingConfig(
        model=model.model_name,
        api_key=api_key,
        base_url=provider.base_url,
        dimension=model.dimension or 1024,
    )
    return OpenAICompatibleEmbedding(config)


def create_cross_encoder(model):
    """从 Pydantic ModelConfig 加载本地 Cross-Encoder 模型。"""
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        logger.warning("sentence-transformers 未安装，Cross-Encoder 不可用")
        return None

    params = getattr(model, 'params', {}) or {}
    device = params.get('device', None)

    try:
        if device:
            ce = CrossEncoder(model.model_name, device=device)
        else:
            ce = CrossEncoder(model.model_name)
        logger.info(f"Cross-Encoder 加载成功: {model.model_name} (device={device or 'auto'})")
        return ce
    except Exception as e:
        logger.warning(f"Cross-Encoder 加载失败 ({e})")
        return None


def create_api_reranker(provider, model):
    """从 Pydantic ProviderConfig + ModelConfig 创建云端 Rerank API 实例。"""
    from retrieval.reranker import APIReranker

    api_key = _resolve_api_key(provider)
    api_path = getattr(model, 'api_path', '') or ''
    base_url = provider.base_url
    if '/compatible-mode' in base_url:
        base_url = base_url.split('/compatible-mode')[0]

    timeout = getattr(model, 'timeout', None)
    total_t = timeout.total if timeout and timeout.total else 30.0

    api_reranker = APIReranker(
        api_key=api_key,
        api_path=api_path,
        model_name=model.model_name,
        base_url=base_url,
        timeout=total_t,
    )
    if api_reranker.is_available:
        logger.info(f"云端 Rerank API 已配置: {model.model_name} ({api_path})")
        return api_reranker
    else:
        logger.warning(f"云端 Rerank API 缺 api_key 或 api_path: {model.model_name}")
        return None


def create_api_ocr_instance(provider, model):
    """从 Pydantic ProviderConfig + ModelConfig 创建云端 OCR API 实例。"""
    from parsing.pdf.ocr import APIOCR

    api_path = getattr(model, 'api_path', '') or ''
    base_url = provider.base_url
    if '/compatible-mode' in base_url:
        base_url = base_url.split('/compatible-mode')[0]

    ocr = APIOCR(
        api_key=provider.api_key,
        base_url=base_url,
        api_path=api_path,
        model_name=model.model_name,
    )
    if ocr.load():
        logger.info(f"云端 OCR API 已配置: {model.model_name} ({api_path})")
    else:
        logger.warning(f"云端 OCR API 缺 api_key 或 api_path: {model.model_name}")
    return ocr


# ================================================================
# HTTP 降级工厂（兼容旧的 Java API dict 格式）
# ================================================================

def create_llm_from_dict(provider: dict, model: dict) -> BaseLLM:
    """根据 provider dict 创建 LLM（HTTP 降级路径）。"""
    ptype = provider.get("type", "")
    api_key = _resolve_key_from_dict(provider)
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


def create_embedding_from_dict(provider: dict, model: dict) -> BaseEmbedding:
    """根据 provider dict 创建 Embedding（HTTP 降级路径）。"""
    ptype = provider.get("type", "")
    api_key = _resolve_key_from_dict(provider)
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


# ================================================================
# API Key 解析
# ================================================================

def _resolve_api_key(provider) -> str:
    """从 Pydantic ProviderConfig 解析 API Key。"""
    api_key = provider.api_key or ""
    if api_key.startswith("${") and api_key.endswith("}"):
        var_name = api_key[2:-1]
        return os.environ.get(var_name, "")
    return api_key


def _resolve_key_from_dict(provider: dict) -> str:
    """解析 API Key（HTTP 降级 dict 格式）。

    优先级：.secret 文件 > 环境变量 > provider dict api_key。
    """
    env_var = provider.get("api_key_env") or ""
    if not env_var and "api_key" in provider:
        return provider["api_key"]

    var_name = env_var.replace("${", "").replace("}", "")
    if not var_name:
        return ""

    # .secret 文件
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

    return os.environ.get(var_name, "")
