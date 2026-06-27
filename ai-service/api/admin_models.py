"""POST /v1/admin/models/* — 模型发现与连通性测试（供 Java 后端调用）。

Java 通过 @RequireGlobalAdmin 做权限校验，Python 只负责实际调用提供商 API。
"""

import time

from fastapi import APIRouter
from pydantic import BaseModel

from common import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/admin/models")


class DiscoverRequest(BaseModel):
    provider_type: str       # "openai_compatible" | "ollama"
    base_url: str
    api_key: str
    model_type_filter: str | None = None  # "chat" | "embedding"


class TestRequest(BaseModel):
    provider_type: str
    base_url: str
    api_key: str
    model_name: str | None = None


@router.post("/discover")
async def discover_models(req: DiscoverRequest):
    """模型发现：调提供商端点获取可用模型列表。"""
    try:
        if req.provider_type == "openai_compatible":
            return await _discover_openai(req)
        elif req.provider_type == "ollama":
            return await _discover_ollama(req)
        else:
            return {"error": f"不支持的 provider 类型: {req.provider_type}", "models": []}
    except Exception as e:
        logger.warning(f"模型发现失败: {e}")
        return {"error": str(e), "models": []}


@router.post("/test")
async def test_connection(req: TestRequest):
    """连通性测试：轻量调用提供商 API 验证连接。"""
    start = time.time()
    try:
        if req.provider_type in ("openai_compatible",):
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=req.api_key,
                base_url=req.base_url,
                timeout=10,
            )
            # 最小开销测试：用 models.list() ，比 chat 调用更轻量
            await client.models.list()
        elif req.provider_type == "ollama":
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{req.base_url}/api/tags")
                resp.raise_for_status()
        else:
            return {"success": False, "error": f"不支持的 provider 类型: {req.provider_type}"}

        elapsed = (time.time() - start) * 1000
        return {"success": True, "latency_ms": round(elapsed, 1)}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _discover_openai(req: DiscoverRequest) -> dict:
    """从 OpenAI 兼容 API 发现模型。"""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=req.api_key, base_url=req.base_url, timeout=15)
    models = await client.models.list()

    result = []
    for m in models.data:
        # 过滤掉非模型条目（如 dall-e, whisper, tts, moderation 等）
        model_id = m.id
        result.append({
            "id": model_id,
            "owned_by": getattr(m, "owned_by", ""),
        })

    return {"models": result, "total": len(result)}


async def _discover_ollama(req: DiscoverRequest) -> dict:
    """从 Ollama 发现本地模型。"""
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{req.base_url.rstrip('/')}/api/tags")
        resp.raise_for_status()
        data = resp.json()

    result = []
    for m in data.get("models", []):
        result.append({
            "id": m.get("name", ""),
            "owned_by": "ollama",
        })

    return {"models": result, "total": len(result)}
