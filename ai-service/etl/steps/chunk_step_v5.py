"""分块步骤 v5 — 使用 chunking/ 模块。

与旧 ChunkStep 的区别：
    - 输入 ParsedDocument（结构化 blocks）
    - 使用 ChunkOrchestrator（TokenChunker + TitleChunker + ContextEnricher）
    - 产出带内容加权的 Chunk（content_with_weight 传给 BM25）
    - 转换为旧 DocumentChunk 格式，保持 EmbedStep/IndexStep 兼容
"""

from common import get_logger
from models.document import DocumentChunk, IngestCallbackMessage, IngestStatus
from chunking.orchestrator import ChunkOrchestrator
from .base import PipelineStep

logger = get_logger(__name__)


class ChunkStepV5(PipelineStep):
    """v5 分块步骤 — 使用新的 chunking/ 模块。

    输入: ctx["parsed_doc"] (ParsedDocument)
    产出: ctx["chunks"] (list[DocumentChunk]) — 兼容 EmbedStep/IndexStep
    """

    def __init__(self, orchestrator: ChunkOrchestrator):
        self._orchestrator = orchestrator

    async def execute(self, ctx: dict) -> dict:
        msg = ctx["msg"]
        parsed_doc = ctx.get("parsed_doc")

        if parsed_doc is None:
            ctx["_early_exit"] = IngestCallbackMessage(
                doc_id=msg.doc_id,
                status=IngestStatus.FAILED,
                error_message="v5 分块失败：parsed_doc 未生成",
            )
            return ctx

        # 注入 doc_id 供 chunking 模块使用
        parsed_doc.metadata.extra["doc_id"] = str(msg.doc_id)

        # 使用新 ChunkOrchestrator 分块
        new_chunks, relations = await self._orchestrator.chunk(
            parsed_doc, strategy="auto"
        )

        if not new_chunks:
            ctx["_early_exit"] = IngestCallbackMessage(
                doc_id=msg.doc_id,
                status=IngestStatus.FAILED,
                error_message="v5 分块结果为空",
            )
            return ctx

        # 转换为旧 DocumentChunk 格式（兼容 EmbedStep/IndexStep）
        old_chunks = []
        for i, chunk in enumerate(new_chunks):
            meta = {
                "kb_id": msg.metadata.kb_id,
                "source_file": msg.file_path,
                "effective_date": msg.metadata.effective_date,
                "expiry_date": msg.metadata.expiry_date,
                "version": msg.metadata.version,
                # v5 新增：传 content_with_weight 给 IndexStep
                "content_with_weight": chunk.content_with_weight,
                # v5 新增：chunk 类型和标题
                "chunk_type": chunk.chunk_type,
                "title": chunk.title,
                "page_range": chunk.page_range,
                # v12 parent-child: 两级分块元数据
                "parent_id": chunk.metadata.get("parent_id"),
                "parent_content": chunk.metadata.get("parent_content"),
                "parent_title": chunk.metadata.get("parent_title"),
                "parent_type": chunk.metadata.get("parent_type"),
            }
            # 保留 chunker 产出的额外 metadata（如 TitleChunker 设置的 level）
            for k, v in chunk.metadata.items():
                if k not in meta:
                    meta[k] = v
            old_chunks.append(DocumentChunk(
                doc_id=msg.doc_id,
                chunk_index=i,
                chunk_text=chunk.content,
                metadata=meta,
            ))

        ctx["chunks"] = old_chunks
        logger.info(
            f"v5 分块完成: doc_id={msg.doc_id}, "
            f"blocks={len(parsed_doc.blocks)} → chunks={len(old_chunks)}, "
            f"strategy=auto"
        )
        return ctx
