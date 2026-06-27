"""PII 脱敏步骤 — v5 同步清理 parsed_doc.blocks。"""

from common import get_logger
from etl.sanitizers.presidio_sanitizer import PresidioSanitizer
from parsing.models import TextBlock
from .base import PipelineStep

logger = get_logger(__name__)


class SanitizeStep(PipelineStep):
    """对解析后的文本执行 PII 脱敏。

    v5 流水线中 ChunkStepV5 从 parsed_doc.blocks 读取文本，
    因此必须同步清理 blocks 中的 TextBlock.text，否则脱敏失效。
    """

    def __init__(self, sanitizer: PresidioSanitizer, security_level: int = 2):
        self._sanitizer = sanitizer
        self._security_level = security_level

    async def execute(self, ctx: dict) -> dict:
        parse_result = ctx["parse_result"]
        parsed_doc = ctx.get("parsed_doc")

        sanitized_text, has_sensitive = await self._sanitizer.sanitize(
            parse_result.raw_text,
            security_level=self._security_level,
        )
        if has_sensitive:
            logger.info(f"检测到敏感信息，已脱敏: doc_id={ctx['msg'].doc_id}")

        parse_result.raw_text = sanitized_text

        # v5: 同步清理 parsed_doc.blocks 中的文本，确保 ChunkStepV5 读取到脱敏后内容
        if parsed_doc is not None and has_sensitive:
            for block in parsed_doc.blocks:
                if isinstance(block, TextBlock):
                    block.text, _ = await self._sanitizer.sanitize(
                        block.text, security_level=self._security_level
                    )

        return ctx
