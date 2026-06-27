"""文件解析步骤。"""

from common import get_logger
from models.document import IngestCallbackMessage, IngestStatus
from etl.parsers.registry import ParserRegistry
from .base import PipelineStep

logger = get_logger(__name__)


class ParseStep(PipelineStep):
    """根据文件类型选择解析器并解析文件。"""

    def __init__(self, parser_registry: ParserRegistry):
        self._parser_registry = parser_registry

    async def execute(self, ctx: dict) -> dict:
        msg = ctx["msg"]
        temp_path = ctx["temp_path"]

        parser = self._parser_registry.get(msg.file_type)
        if parser is None:
            ctx["_early_exit"] = IngestCallbackMessage(
                doc_id=msg.doc_id,
                status=IngestStatus.FAILED,
                error_message=f"不支持的文件类型: {msg.file_type}",
            )
            return ctx

        parse_result = await parser.parse(temp_path)
        ctx["parse_result"] = parse_result

        # OCR 存根：如果 raw_text 为空，尝试 OCR
        if not parse_result.raw_text:
            logger.info(f"raw_text 为空，OCR 存根（未实现）: doc_id={msg.doc_id}")
            # TODO: 集成 PaddleOCR

        if not parse_result.raw_text:
            ctx["_early_exit"] = IngestCallbackMessage(
                doc_id=msg.doc_id,
                status=IngestStatus.FAILED,
                error_message="无法提取文本内容",
            )

        return ctx
