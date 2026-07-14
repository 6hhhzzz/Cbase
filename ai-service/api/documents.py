"""文档生命周期 API — Java 后端调用，同步文档状态到 knowledge_chunks。

所有端点仅限内部调用（由 Java 后端触发），不直接暴露给前端。
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from common import get_logger
from models.lifecycle import DocumentStatusRequest
from retrieval.vector_store import PGVectorClient
from .dependencies import get_pgvector_client

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/documents", tags=["documents"])


class BatchDeleteChunksRequest(BaseModel):
    doc_ids: list[str]


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


@router.post("/batch/chunks/delete")
async def batch_delete_chunks(
    request: BatchDeleteChunksRequest,
    pgvector_client: PGVectorClient = Depends(get_pgvector_client),
):
    """批量永久删除文档的所有向量 chunks。"""
    results = {}
    total = 0
    for doc_id in request.doc_ids:
        try:
            count = await pgvector_client.delete_by_doc_id(UUID(doc_id))
            results[doc_id] = count
            total += count
        except Exception as e:
            results[doc_id] = 0
            logger.warning(f"批量删除 chunks 失败: doc_id={doc_id}, error={e}")
    logger.info(f"批量删除 chunks 完成: docs={len(request.doc_ids)}, total_chunks={total}")
    return {"ok": True, "results": results, "total_deleted": total}
