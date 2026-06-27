"""配置模型。对应 proposal 4.7 的 YAML 配置结构和 docker-compose 基础设施参数。

环境变量映射（pydantic-settings 自动处理，嵌套用 __ 分隔）：
  LLM__API_KEY       → settings.llm.api_key
  PGVECTOR__HOST     → settings.pgvector.host
  RABBITMQ__HOST     → settings.rabbitmq.host
"""

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class LLMConfig(BaseModel):
    """LLM 配置。对应 proposal 4.7 中 llm.yaml 的 llm 段。"""

    type: str = "openai_compatible"
    api_key: str
    base_url: str
    model: str
    default_params: dict = Field(default_factory=lambda: {
        "temperature": 0.3,
        "max_tokens": 2048,
    })


class EmbeddingConfig(BaseModel):
    """Embedding 配置。对应 proposal 4.7 中 llm.yaml 的 embedding 段。"""

    type: str = "openai_compatible"
    api_key: str
    base_url: str
    model: str
    dimension: int = 1024


class PGVectorConfig(BaseModel):
    """PostgreSQL + pgvector 连接配置。对应 docker-compose 中的 postgres 服务。"""

    host: str = "localhost"
    port: int = 5432
    user: str = "kes"
    password: str = "kes123"
    database: str = "kes"
    dimension: int = 1024
    min_pool_size: int = 2
    max_pool_size: int = 10


class RabbitMQConfig(BaseModel):
    """RabbitMQ 连接配置。对应 docker-compose 中的 rabbitmq 服务。"""

    host: str = "localhost"
    port: int = 5672
    user: str = "kes"
    password: str = "kes123"
    exchange: str = "kes.document"
    ingest_routing_key: str = "document.ingest"
    callback_routing_key: str = "document.ingest.callback"


class RedisConfig(BaseModel):
    """Redis 连接配置。对应 docker-compose 中的 redis 服务。"""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    ttl_seconds: int = 604800  # 7 天


class MinioConfig(BaseModel):
    """MinIO 对象存储配置。对应 docker-compose 中的 kes-minio 服务。"""

    endpoint: str = "localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "kes-documents"
    secure: bool = False


class SummaryConfig(BaseModel):
    """摘要引擎配置。"""
    soft_limit: int = 1500
    compress_target: int = 800
    trigger_rounds: int = 10
    max_failures: int = 3


class Settings(BaseSettings):
    """全局配置，从环境变量 / YAML 加载。

    环境变量映射（pydantic-settings 自动处理，嵌套用 __ 分隔）：
      LLM__API_KEY       → settings.llm.api_key
      PGVECTOR__HOST     → settings.pgvector.host
      RABBITMQ__HOST     → settings.rabbitmq.host
    """

    llm: LLMConfig
    embedding: EmbeddingConfig
    pgvector: PGVectorConfig = PGVectorConfig()
    rabbitmq: RabbitMQConfig = RabbitMQConfig()
    redis: RedisConfig = RedisConfig()
    minio: MinioConfig = MinioConfig()
    summary: SummaryConfig = SummaryConfig()

    model_config = {"env_nested_delimiter": "__"}
