"""文件解析步骤 v5 — 使用 parsing/ 模块。

与旧 ParseStep 的区别：
    - 使用 parsing.ParseOrchestrator（MIME 路由，返回 ParsedDocument）
    - 支持 PPTX 格式
    - 产出 ParsedDocument（含 TextBlock/TableBlock/ImageBlock）
    - 同时产出旧 ParseResult，保持 SanitizeStep 兼容
"""

from common import get_logger
from models.document import ParseResult, IngestCallbackMessage, IngestStatus
from parsing.orchestrator import ParseOrchestrator
from .base import PipelineStep

logger = get_logger(__name__)


class ParseStepV5(PipelineStep):
    """v5 解析步骤 — 使用新的 parsing/ 模块。

    产出：
        ctx["parsed_doc"]   — ParsedDocument（结构化 blocks，供 ChunkStepV5 使用）
        ctx["parse_result"] — ParseResult（旧格式，供 SanitizeStep 兼容）
    """

    def __init__(self, orchestrator: ParseOrchestrator):
        self._orchestrator = orchestrator

    async def execute(self, ctx: dict) -> dict:
        msg = ctx["msg"]
        temp_path = ctx["temp_path"]

        # 使用新 ParseOrchestrator 解析
        try:
            parsed_doc = await self._orchestrator.parse(temp_path, file_type=msg.file_type)
        except ValueError as e:
            ctx["_early_exit"] = IngestCallbackMessage(
                doc_id=msg.doc_id,
                status=IngestStatus.FAILED,
                error_message=str(e),
            )
            return ctx

        if not parsed_doc.blocks:
            ctx["_early_exit"] = IngestCallbackMessage(
                doc_id=msg.doc_id,
                status=IngestStatus.FAILED,
                error_message="v5 解析失败：无法提取文档内容",
            )
            return ctx

        # 存储新格式
        ctx["parsed_doc"] = parsed_doc

        # 同时产出旧格式 ParseResult（SanitizeStep 仍需要 raw_text）
        old_result = ParseResult(
            file_type=msg.file_type,
            raw_text=parsed_doc.plain_text,
            page_count=parsed_doc.metadata.page_count,
            tables=[],  # 新模块用 TableBlock，旧 ParseResult 的 tables 不再使用
            metadata={
                "title": parsed_doc.metadata.title,
                "has_ocr": parsed_doc.metadata.has_ocr,
            },
        )
        ctx["parse_result"] = old_result

        logger.info(
            f"v5 解析完成: doc_id={msg.doc_id}, type={msg.file_type}, "
            f"blocks={len(parsed_doc.blocks)}, "
            f"text={len(parsed_doc.text_blocks)}, "
            f"tables={len(parsed_doc.table_blocks)}, "
            f"chars={len(parsed_doc.plain_text)}"
        )
        return ctx
