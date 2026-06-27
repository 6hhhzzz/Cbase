"""配置加载模块。从 YAML 文件和环境变量加载配置，返回强类型 Settings 对象。

环境变量优先级 > YAML 文件 > Pydantic Field default 值
"""

import os
from functools import lru_cache
from pathlib import Path

import yaml

from models.config import EmbeddingConfig, LLMConfig, Settings


def _substitute_env_vars(value: str) -> str:
    """替换字符串中的 ${ENV_VAR} 为环境变量值。

    如果引用的环境变量未设置，抛出 KeyError，启动时立即失败而非静默传空值。
    """
    if not isinstance(value, str):
        return value
    import re

    def _replace(match):
        var_name = match.group(1)
        val = os.environ.get(var_name)
        if val is None:
            raise KeyError(
                f"环境变量 {var_name} 未设置（YAML 中引用了 ${{{var_name}}}）"
            )
        return val

    return re.sub(r"\$\{(\w+)\}", _replace, value)


def _resolve_env_in_dict(data: dict) -> dict:
    """递归处理字典中的所有值，替换 ${ENV_VAR} 占位符。"""
    resolved = {}
    for key, value in data.items():
        if isinstance(value, str):
            resolved[key] = _substitute_env_vars(value)
        elif isinstance(value, dict):
            resolved[key] = _resolve_env_in_dict(value)
        else:
            resolved[key] = value
    return resolved


def _apply_env_overrides(settings: Settings) -> None:
    """检查 LLM__*、EMBEDDING__* 等环境变量并覆盖 Settings 中对应字段。

    例如:
        LLM__API_KEY=sk-xxx       → settings.llm.api_key = "sk-xxx"
        PGVECTOR__HOST=10.0.0.1  → settings.pgvector.host = "10.0.0.1"
    """
    # 子配置名 → 对应 Settings 上的属性名
    section_map = {
        "LLM": "llm",
        "EMBEDDING": "embedding",
        "PGVECTOR": "pgvector",
        "RABBITMQ": "rabbitmq",
        "REDIS": "redis",
        "MINIO": "minio",
    }

    for key, val in os.environ.items():
        if "__" not in key:
            continue
        prefix, field = key.split("__", 1)
        attr_name = section_map.get(prefix.upper())
        if attr_name is None:
            continue
        section = getattr(settings, attr_name)
        if hasattr(section, field.lower()):
            # 类型转换：Pydantic 字段可能有 int/bool 类型
            field_info = section.model_fields.get(field.lower())
            if field_info and field_info.annotation is not None:
                annotation = field_info.annotation
                if annotation is int:
                    val = int(val)
                elif annotation is bool:
                    val = val.lower() in ("true", "1", "yes")
            setattr(section, field.lower(), val)


def load_settings(config_path: str = "config/llm.yaml") -> Settings:
    """加载全局配置。

    Args:
        config_path: YAML 配置文件路径，相对于项目根目录

    Returns:
        Settings: 强类型配置对象

    Raises:
        FileNotFoundError: 配置文件不存在
        ValueError: 配置校验失败
    """
    # 查找配置文件
    path = Path(config_path)
    if not path.is_absolute():
        # 从 ai-service 根目录开始查找
        search_paths = [
            path,
            Path.cwd() / path,
            Path(__file__).parent.parent.parent / path,  # core/config -> ai-service/
        ]
        for p in search_paths:
            if p.exists():
                path = p
                break
        else:
            raise FileNotFoundError(
                f"配置文件未找到: {config_path}，已搜索路径: {search_paths}"
            )

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # 替换 YAML 中的 ${ENV_VAR} 占位符
    resolved = _resolve_env_in_dict(raw)

    # 让 pydantic-settings 自动从环境变量覆盖 YAML 值
    # 支持 LLM__API_KEY、MILVUS__HOST 等嵌套变量名
    settings = Settings(
        llm=LLMConfig(**resolved.get("llm", {})),
        embedding=EmbeddingConfig(**resolved.get("embedding", {})),
    )

    # 环境变量覆盖：LLM__API_KEY 等 pydantic-settings 风格变量
    # Settings 直接传参后 BaseSettings 不会自动覆盖，这里手动合并
    _apply_env_overrides(settings)

    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回已加载的 Settings 单例。首次调用时自动从 YAML 加载。"""
    return load_settings()
