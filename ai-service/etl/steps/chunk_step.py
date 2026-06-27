"""文本分块 + 元数据注入步骤。"""

from common import get_logger
from models.document import IngestCallbackMessage, IngestStatus
from etl.chunkers.text_chunker import TextChunker
from .base import PipelineStep

logger = get_logger(__name__)


class ChunkStep(PipelineStep):
    """将解析后的文本拆分为重叠块并注入权限/业务元数据。"""

    def __init__(self, chunker: TextChunker):
        self._chunker = chunker

    async def execute(self, ctx: dict) -> dict:
        msg = ctx["msg"]
        parse_result = ctx["parse_result"]

        # Excel 双通道判定
        if msg.file_type == "xlsx" and self._is_structured_excel(msg):
            logger.info(f"Excel 结构化通道: doc_id={msg.doc_id} (暂未实现)")
            ctx["_early_exit"] = IngestCallbackMessage(
                doc_id=msg.doc_id,
                status=IngestStatus.COMPLETED,
                chunks_created=0,
                error_message="结构化通道暂未实现",
            )
            return ctx

        chunks = await self._chunker.chunk(parse_result, msg.metadata, doc_id=msg.doc_id)
        if not chunks:
            ctx["_early_exit"] = IngestCallbackMessage(
                doc_id=msg.doc_id,
                status=IngestStatus.FAILED,
                error_message="分块结果为空",
            )
            return ctx

        # 注入权限元数据 + 业务时效
        for chunk in chunks:
            chunk.metadata["kb_id"] = msg.metadata.kb_id
            chunk.metadata["source_file"] = msg.file_path
            chunk.metadata["effective_date"] = msg.metadata.effective_date
            chunk.metadata["expiry_date"] = msg.metadata.expiry_date
            chunk.metadata["version"] = msg.metadata.version

        ctx["chunks"] = chunks
        return ctx

    @staticmethod
    def _is_structured_excel(msg) -> bool:
        """判断 Excel 是否走结构化通道（proposal 7.2）。"""
        return msg.metadata.uploader_role in {
            "finance_manager", "sales_manager", "admin", "superadmin"
        }
