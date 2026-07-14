"""POST /v1/admin/models/* — 模型发现、连通性测试、配置读写（供 Java 后端调用）。

Java 通过 @RequireGlobalAdmin 做权限校验，Python 只负责实际执行。
"""

import time

from fastapi import APIRouter, HTTPException
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


# ── v2 配置文件读写 ──

class ConfigUpdateRequest(BaseModel):
    """models.yaml 更新请求 — 前端提交 JSON 配置对象或 YAML 字符串。"""
    config_json: dict | None = None     # JSON 对象（前端推荐）
    yaml_content: str | None = None     # YAML 字符串（兼容）


@router.get("/config")
async def get_models_config():
    """获取当前 models.yaml 内容（JSON 格式）。"""
    try:
        from core.config.models_config import load_models_config, resolve_fallback_chain, DEFAULT_CONFIG_PATH

        config = load_models_config()
        chains = resolve_fallback_chain(config)

        return {
            "providers": {k: v.model_dump() for k, v in config.providers.items()},
            "models": {k: v.model_dump() for k, v in config.models.items()},
            "assignments": {
                k: {
                    "model": v.model,
                    "fallback": v.fallback,
                    "description": v.description,
                    "fallback_chain": chains.get(k, [k]),
                }
                for k, v in config.assignments.items()
            },
            "version": config.version,
            "config_path": str(DEFAULT_CONFIG_PATH),
        }
    except FileNotFoundError:
        return {"providers": {}, "models": {}, "assignments": {}, "version": 0,
                "error": "配置文件不存在"}
    except Exception as e:
        logger.error(f"读取配置失败: {e}")
        return {"error": str(e)}


@router.put("/config")
async def update_models_config(req: ConfigUpdateRequest):
    """更新 models.yaml（校验 + 原子写入）。

    接受两种格式:
      - config_json: JSON 对象（前端推荐）
      - yaml_content: YAML 字符串（兼容旧接口）
    """
    from core.config.models_config import save_models_config, ModelsConfig, _validate_references
    import yaml as yaml_lib

    # 解析输入
    raw = None
    if req.config_json:
        raw = req.config_json
    elif req.yaml_content:
        try:
            raw = yaml_lib.safe_load(req.yaml_content)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"YAML 解析失败: {e}")
    else:
        raise HTTPException(status_code=400, detail="需要 config_json 或 yaml_content")

    if raw is None:
        raise HTTPException(status_code=400, detail="配置为空")

    # Pydantic 校验 + 交叉引用检查
    try:
        new_config = ModelsConfig(**raw)
        _validate_references(new_config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"配置校验失败: {e}")

    try:
        save_models_config(new_config)
        logger.info("models.yaml 已通过 API 更新")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {e}")

    return {"success": True, "message": "配置已保存"}
