"""文档生命周期 API — Java 后端调用，同步文档状态到 knowledge_chunks。

所有端点仅限内部调用（由 Java 后端触发），不直接暴露给前端。
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from common import get_logger
from models.lifecycle import DocumentStatusRequest
from retrieval.vector_store import PGVectorClient
from .dependencies import get_pgvector_client

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.post("/status")
async def update_document_status(
    request: DocumentStatusRequest,
    pgvector_client: PGVectorClient = Depends(get_pgvector_client),
):
    """同步文档状态到 knowledge_chunks 表。"""
    count = await pgvector_client.update_chunk_status(request.doc_id, request.status)
    logger.info(f"文档状态同步: doc_id={request.doc_id}, status={request.status}, updated={count}")
    return {"ok": True, "updated": count}


@router.delete("/{doc_id}/chunks")
async def delete_document_chunks(
    doc_id: str,
    pgvector_client: PGVectorClient = Depends(get_pgvector_client),
):
    """永久删除文档的所有向量 chunks。"""
    count = await pgvector_client.delete_by_doc_id(UUID(doc_id))
    logger.info(f"文档 chunks 已删除: doc_id={doc_id}, count={count}")
    return {"ok": True, "deleted": count}
