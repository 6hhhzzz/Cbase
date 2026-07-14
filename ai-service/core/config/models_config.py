"""模型配置 v2 — 从 models.yaml 加载（Pydantic 模型 + YAML 加载器）。

替代旧的 ModelPool HTTP 拉取方式。
配置集中在一个 YAML 文件中，通过前端 API 编辑。
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

# 配置文件路径
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "models.yaml"

# 支持的 provider 类型
PROVIDER_TYPES = {"openai_compatible", "ollama", "local"}

# 支持的 model 类型
MODEL_TYPES = {"chat", "embedding", "reranker", "ocr"}


# ── Pydantic 模型 ──

class ProviderConfig(BaseModel):
    """供应商配置。"""
    type: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    description: str = ""

    @field_validator("type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in PROVIDER_TYPES:
            raise ValueError(f"不支持的 provider type: {v}，有效值: {PROVIDER_TYPES}")
        return v


class TimeoutConfig(BaseModel):
    """HTTP 超时配置。"""
    connect: float = 10.0
    read: float = 60.0
    total: float = 120.0


class ModelConfig(BaseModel):
    """模型实例配置。"""
    provider: str                            # provider key
    model_name: str                          # 实际模型名
    model_type: str = "chat"                 # chat | embedding | reranker | splade
    max_tokens: int = 8192
    dimension: int = 0                       # embedding 用
    api_path: str = ""                       # 覆盖默认 API 路径（不同 model_type 端点不同时使用）
    params: dict[str, Any] = Field(default_factory=dict)  # 模型参数（device, temperature 等）
    timeout: TimeoutConfig = Field(default_factory=TimeoutConfig)

    @field_validator("model_type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in MODEL_TYPES:
            raise ValueError(f"不支持的 model_type: {v}，有效值: {MODEL_TYPES}")
        return v


class AssignmentConfig(BaseModel):
    """环节映射配置。"""
    model: str                               # model key
    fallback: str | None = None              # 降级目标 purpose key
    description: str = ""


class ModelsConfig(BaseModel):
    """顶层配置 — models.yaml 的完整结构。"""
    version: int = 2
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    models: dict[str, ModelConfig] = Field(default_factory=dict)
    assignments: dict[str, AssignmentConfig] = Field(default_factory=dict)


# ── 加载器 ──

def _load_dotenv() -> None:
    """加载 .env 文件到 os.environ（仅设置未存在的变量）。"""
    dotenv_path = Path(__file__).parent.parent.parent / ".env"
    if not dotenv_path.exists():
        return
    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass  # .env 加载失败不影响启动


def _resolve_env_vars(value: Any) -> Any:
    """递归替换字符串中的 ${ENV_VAR} 为环境变量值。"""
    if isinstance(value, str):
        pattern = re.compile(r'\$\{(\w+)\}')
        def _replacer(m: re.Match) -> str:
            return str(os.environ.get(m.group(1), m.group(0)))
        return pattern.sub(_replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


def load_models_config(path: Path | None = None) -> ModelsConfig:
    """加载 models.yaml 配置文件。

    流程: 读 YAML → 替换环境变量 → Pydantic 校验 → 返回 ModelsConfig

    Args:
        path: 配置文件路径。None 时使用默认路径。

    Returns:
        ModelsConfig 实例

    Raises:
        FileNotFoundError: 配置文件不存在
        ValueError: YAML 格式或校验错误
    """
    config_path = path or DEFAULT_CONFIG_PATH

    if not config_path.exists():
        raise FileNotFoundError(f"模型配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError(f"配置文件为空: {config_path}")

    # 加载 .env 到 os.environ（兼容开发环境）
    _load_dotenv()

    # 替换环境变量
    resolved = _resolve_env_vars(raw)

    # Pydantic 校验
    config = ModelsConfig(**resolved)

    # 交叉引用校验
    _validate_references(config)

    return config


def _validate_references(config: ModelsConfig) -> None:
    """校验 model/provider 引用有效性 + fallback 无环。"""
    # 1. assignments 中的 model 必须在 models 中定义
    for purpose, a in config.assignments.items():
        if a.model not in config.models:
            raise ValueError(
                f"环节 '{purpose}' 引用的模型 '{a.model}' 未在 models 中定义"
            )

    # 2. models 中的 provider 必须在 providers 中定义
    for model_key, m in config.models.items():
        if m.provider not in config.providers:
            raise ValueError(
                f"模型 '{model_key}' 引用的供应商 '{m.provider}' 未在 providers 中定义"
            )

    # 3. fallback 引用必须指向有效的 assignments key
    for purpose, a in config.assignments.items():
        if a.fallback and a.fallback not in config.assignments:
            raise ValueError(
                f"环节 '{purpose}' 的 fallback '{a.fallback}' 不是有效的环节"
            )
        # 检测自引用
        if a.fallback == purpose:
            raise ValueError(
                f"环节 '{purpose}' 的 fallback 不能指向自身"
            )

    # 4. 降级链无环检测
    _validate_fallback_no_cycle(config)


def _validate_fallback_no_cycle(config: ModelsConfig) -> None:
    """检测 fallback 链中是否存在有效循环（len > 2 的环）。

    允许 A→B→A（双向降级），禁止 A→B→C→A（三向及以上循环）。
    """
    def get_chain(purpose: str) -> list[str] | None:
        chain: list[str] = [purpose]
        seen = {purpose}
        current = purpose
        while True:
            a = config.assignments.get(current)
            if not a or not a.fallback:
                return None  # 链终止，无循环
            nxt = a.fallback
            if nxt in seen:
                # 检查是否是双向引用（A→B→A）
                if len(chain) >= 2 and nxt == chain[-2]:
                    return None  # 双向降级，允许
                chain.append(nxt)
                return chain  # 真正的循环
            chain.append(nxt)
            seen.add(nxt)
            current = nxt

    for purpose in config.assignments:
        cycle = get_chain(purpose)
        if cycle:
            raise ValueError(
                f"降级链中存在循环依赖: {' → '.join(cycle)}"
                f"（双向降级如 A→B→A 允许，但三向及以上不允许）"
            )


def save_models_config(config: ModelsConfig, path: Path | None = None) -> None:
    """保存配置到 models.yaml（原子写入）。

    流程: 写临时文件 → YAML dump → 原子 rename

    Args:
        config: ModelsConfig 实例
        path: 配置文件路径
    """
    config_path = path or DEFAULT_CONFIG_PATH
    tmp_path = config_path.with_suffix(".yaml.tmp")

    # 转为 dict（Pydantic model_dump），排序保持可读性
    raw = config.model_dump(exclude_defaults=False)

    # 去掉空字符串/0 值使其更干净
    raw = _clean_empty(raw)

    yaml_str = yaml.dump(raw, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # 原子写入
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(yaml_str)

    os.replace(tmp_path, config_path)


def _clean_empty(obj: Any) -> Any:
    """递归清理空值（空字符串、空 dict、0 值）。"""
    if isinstance(obj, dict):
        return {k: _clean_empty(v) for k, v in obj.items()
                if v != "" and v != {} and v != [] and v is not None}
    elif isinstance(obj, list):
        return [_clean_empty(v) for v in obj]
    return obj


def resolve_fallback_chain(config: ModelsConfig) -> dict[str, list[str]]:
    """解析降级链：为每个 purpose 生成完整的降级路径。

    Returns:
        {purpose: [purpose, fallback1, fallback2, ...]}
        如 {"reranker": ["reranker", "rerank_llm", "slm", "chat"]}
    """
    chains: dict[str, list[str]] = {}

    for purpose in config.assignments:
        chain = [purpose]
        current = purpose
        seen = {purpose}
        while True:
            a = config.assignments.get(current)
            if not a or not a.fallback or a.fallback in seen:
                break
            chain.append(a.fallback)
            seen.add(a.fallback)
            current = a.fallback
        chains[purpose] = chain

    return chains
