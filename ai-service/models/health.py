"""健康检查数据模型。对应 openapi.yaml 中 HealthResponse Schema。"""

from pydantic import BaseModel, Field


class ComponentStatus(BaseModel):
    """单个组件的健康状态。"""

    status: str = Field(..., pattern=r"^(healthy|degraded|unhealthy)$")


class HealthResponse(BaseModel):
    """健康检查整体响应。"""

    status: str
    components: dict[str, str]
