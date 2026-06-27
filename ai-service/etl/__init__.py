# ETL 模块：文档解析、OCR、脱敏、分块、入库
# 实现 IngestMessageHandler 接口，作为 MQ 的 Consumer

from .pipeline import ETLPipeline

__all__ = ["ETLPipeline"]
