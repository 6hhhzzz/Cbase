"""ETL 管道入口 — v4 解耦版。

将处理链路拆分为独立的 PipelineStep，通过 context dict 传递状态。
每个 Step 只负责一个职责，可以独立测试和替换。

步骤链:
    DownloadStep → ParseStepV5 → SanitizeStep → ChunkStepV5 → LlmMetadataEnrichStep → EmbedStep → IndexStep
"""

import os

from common import get_logger
from models.document import (
    DocumentIngestMessage,
    IngestCallbackMessage,
    IngestStatus,
)
from mq.handler import IngestMessageHandler

from .steps.base import PipelineStep

logger = get_logger(__name__)


class ETLPipeline(IngestMessageHandler):
    """ETL 管道入口，按顺序执行 Step 链。"""

    def __init__(self, steps: list[PipelineStep]):
        self._steps = steps

    async def handle(self, msg: DocumentIngestMessage) -> IngestCallbackMessage:
        """执行 Step 链处理单条入库消息。

        每个 Step 通过 context dict 传递状态。如果某步设置了 ``_early_exit``，
        管道提前终止，返回该步骤产生的回调消息。
        """
        logger.info(f"ETL 开始: doc_id={msg.doc_id}, type={msg.file_type}")

        ctx: dict = {"msg": msg}

        try:
            for step in self._steps:
                ctx = await step.execute(ctx)
                if "_early_exit" in ctx:
                    return ctx["_early_exit"]

            inserted = ctx.get("inserted_count", 0)
            logger.info(f"ETL 完成: doc_id={msg.doc_id}, chunks={inserted}")
            return IngestCallbackMessage(
                doc_id=msg.doc_id,
                status=IngestStatus.COMPLETED,
                chunks_created=inserted,
            )

        except Exception as e:
            logger.error(f"ETL 失败: doc_id={msg.doc_id}, error={e}")
            return IngestCallbackMessage(
                doc_id=msg.doc_id,
                status=IngestStatus.FAILED,
                error_message=str(e),
            )

        finally:
            temp_path = ctx.get("temp_path")
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                    logger.debug(f"临时文件已删除: {temp_path}")
                except OSError as e:
                    logger.warning(f"临时文件删除失败: {temp_path}, error={e}")
