"""MCP Tool 实现 — search_chunks / read_document / ask_expert。

每个 Tool 在执行业务逻辑前强制做权限解析（kb_ids 交集）。
检索链路使用 McpQueryPreparator（纯本地增强） + RetrievalOrchestrator.execute()（共享执行层）。
"""

from dataclasses import dataclass, field
from typing import Any

import httpx

from common import get_logger
from kes_mcp.auth import (
    KeyAuthError,
    _JAVA_BASE,
)
from retrieval.mcp_query_preparator import McpQueryPreparator

logger = get_logger(__name__)

# 全局单例
_preparator = McpQueryPreparator()


# ---- Tool 结果模型 ----

@dataclass
class ChunkResult:
    chunk_id: str
    content: str
    content_exact: str
    score: float
    rerank_score: float | None = None
    source: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


# ---- 权限解析 ----

async def resolve_kb_ids(context_token: str, space_id: str) -> list[str]:
    """调用 Java 鉴权 API 获取当前用户有权限的 kb_ids。"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{_JAVA_BASE}/api/auth/accessible-kbs",
            headers={"Authorization": f"Bearer {context_token}"},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"权限查询失败 ({resp.status_code})")
        kbs = resp.json().get("data", [])
        return [kb["kb_id"] for kb in kbs]


def intersect_kb_ids(tool_kb_ids: list[str] | None, ace_kb_ids: list[str],
                      scope_kb_ids: list[str] | None = None) -> list[str]:
    """三层交集——tool ∩ ace ∩ scope，每层只减不增。

    Args:
        tool_kb_ids: Agent 调用时传入的 kb_ids（可选）
        ace_kb_ids:  Java ACE 解析的用户完整权限
        scope_kb_ids: API Key 级别的 KB 白名单（可选）
    """
    if not ace_kb_ids:
        return []
    result = set(ace_kb_ids)
    if tool_kb_ids:
        result &= set(tool_kb_ids)
    if scope_kb_ids:
        result &= set(scope_kb_ids)
    return list(result)


# ---- 共享鉴权解析（search_chunks / ask_expert 共用）----

async def _resolve_effective_kb_ids(auth, tool_kb_ids: list[str] | None) -> list[str] | None:
    """鉴权 + 三层权限交集。返回 None 表示鉴权失败（调用方自行处理错误消息）。"""
    try:
        token = await auth.ensure_token()
    except KeyAuthError as e:
        return None  # 调用方返回 [{"error": str(e)}]

    try:
        ace_kb_ids = await resolve_kb_ids(token, auth.space_id)
    except Exception as e:
        return None  # 调用方返回 [{"error": f"权限查询失败: {e}"}]

    return intersect_kb_ids(tool_kb_ids, ace_kb_ids, auth.scope_kb_ids)


# ---- 元数据过滤 ----

def _describe_binary_document(doc: dict) -> str:
    """为二进制文档生成有信息量的描述文本，而非仅报告文件体积。

    提示 Agent：该文档已通过 ETL pipeline 处理，可通过 search_chunks 检索其内容。
    """
    file_type = doc.get("file_type", "unknown")
    filename = doc.get("filename", "未知文件")
    page_count = doc.get("page_count", "")
    kb_name = doc.get("kb_name", "")
    doc_id = doc.get("doc_id", "")

    parts = [
        f"[二进制文件: {file_type}]",
        f"文件名: {filename}",
    ]
    if page_count:
        parts.append(f"页数: {page_count}")
    if kb_name:
        parts.append(f"所属知识库: {kb_name}")

    parts.append(
        f"\n该文档已通过 ETL 管道处理，其文本内容可通过 search_chunks 检索。"
        f"使用 doc_id=\"{doc_id}\" 过滤可限定到此文档的块。"
        f"如需下载原始文件，请通过 KES Web 界面操作。"
    )
    return "\n".join(parts)


def _apply_doc_type_filter(chunks: list[dict], doc_type: str | None) -> list[dict]:
    """按文档类型过滤检索结果（简易实现：依赖 chunk metadata 中的 file_type）。"""
    if not doc_type or doc_type == "any":
        return chunks
    return [
        c for c in chunks
        if c.get("metadata", {}).get("doc_type", "").startswith(doc_type)
        or c.get("source", {}).get("filename", "").endswith(_doc_type_ext(doc_type))
    ]


def _doc_type_ext(doc_type: str) -> str:
    """将语义类型映射为常见文件扩展名。"""
    _map = {
        "manual": ".md",
        "specification": ".md",
        "policy": ".md",
        "report": ".docx",
        "guide": ".md",
    }
    return _map.get(doc_type, "")


# ---- Tool: search_chunks ----

async def search_chunks(
    retrieval_orch,
    auth,
    arguments: dict,
) -> list[dict]:
    """混合检索文档块，返回带完整元数据的结构化结果。

    使用 McpQueryPreparator（纯本地增强） → RetrievalOrchestrator.execute()。
    """
    query = arguments.get("query", "")
    kb_ids: list[str] | None = arguments.get("kb_ids")
    top_k: int = arguments.get("top_k", 10)
    include_context: bool = arguments.get("include_context", True)
    context_hint: str | None = arguments.get("context_hint")
    focus_aspects: list[str] | None = arguments.get("focus_aspects")
    doc_type: str | None = arguments.get("doc_type")

    if not query.strip():
        return [{"error": "query 不能为空"}]

    # 鉴权 + 三层权限交集
    effective = await _resolve_effective_kb_ids(auth, kb_ids)
    if effective is None:
        return [{"error": "鉴权失败或权限查询异常"}]
    if not effective:
        return [{"total": 0, "chunks": [], "notice": "无权限访问任何匹配的知识库"}]

    # MCP 查询准备 — jieba 关键词提取（零 LLM 调用）
    prepared = _preparator.prepare(
        query=query,
        top_k=top_k,
        context_hint=context_hint,
        focus_aspects=focus_aspects,
        doc_type=doc_type,
    )

    # 检索执行 — 共享执行层
    try:
        ctx = await retrieval_orch.execute(
            query=prepared.query,
            kb_ids=effective,
            keywords=prepared.keywords,
            top_k=prepared.top_k,
        )
    except Exception as e:
        logger.error(f"检索失败: {e}")
        return [{"error": f"检索失败: {e}"}]

    chunks: list[dict] = []
    for c in ctx.chunks:
        chunks.append({
            "chunk_id": c.chunk_id,
            "content": c.content if include_context else c.content,
            "content_exact": c.content,
            "score": round(c.score, 4),
            "source": {
                "doc_id": c.metadata.get("doc_id", ""),
                "filename": c.source_file,
                "page_range": list(c.page_range) if c.page_range else None,
            },
            "metadata": {"retriever": c.metadata.get("retriever", "fused")},
        })

    # 元数据过滤（可选）
    if doc_type and doc_type != "any":
        chunks = _apply_doc_type_filter(chunks, doc_type)

    result_data: dict[str, Any] = {
        "total": len(chunks),
        "chunks": chunks,
        "query": query,
    }
    if prepared.keywords:
        result_data["keywords_applied"] = prepared.keywords

    return [result_data]


# ---- Tool: read_document ----

async def read_document(
    auth,  # MCPAuth 实例
    arguments: dict,
) -> list[dict]:
    """读取文档完整内容 + 元数据。

    权限校验：先通过 _resolve_effective_kb_ids 获取 ACE 权限 kb_ids，
    再验证文档所属 KB 是否在权限范围内。
    """
    doc_id = arguments.get("doc_id", "")

    # 鉴权 + ACE 权限解析（与 search_chunks / ask_expert 统一路径）
    effective = await _resolve_effective_kb_ids(auth, None)
    if effective is None:
        return [{"error": "鉴权失败或权限查询异常"}]
    if not effective:
        return [{"error": "无权限访问任何知识库"}]

    try:
        context_token = await auth.ensure_token()
    except KeyAuthError as e:
        return [{"error": str(e)}]

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. 获取元数据
        meta_resp = await client.get(
            f"{_JAVA_BASE}/api/documents/{doc_id}",
            headers={"Authorization": f"Bearer {context_token}"},
        )
        if meta_resp.status_code != 200:
            return [{"error": f"文档不存在或无权限 ({meta_resp.status_code})"}]

        doc = meta_resp.json().get("data", {})

        # ACE 权限校验：文档所属 KB 必须在 effective_kb_ids 中
        doc_kb_id = doc.get("kb_id", "")
        if doc_kb_id not in effective:
            return [{"error": f"无权访问此文档所属的知识库 ({doc_kb_id})"}]

        # scope 检查已由 _resolve_effective_kb_ids 的三层交集覆盖
        # effective = ace_kb_ids ∩ scope_kb_ids，此处无需重复检查

        # 2. 获取文件内容（纯文本提取）
        content = ""
        try:
            file_resp = await client.get(
                f"{_JAVA_BASE}/api/documents/{doc_id}/file?token={context_token}",
            )
            if file_resp.status_code == 200:
                content_type = file_resp.headers.get("content-type", "")
                if "text" in content_type or "json" in content_type or "xml" in content_type:
                    content = file_resp.text[:50000]  # 截断 50KB
                else:
                    content = _describe_binary_document(doc)
        except Exception as e:
            content = f"[文件读取失败: {e}]"

        return [{
            "doc_id": doc.get("doc_id"),
            "filename": doc.get("filename"),
            "file_type": doc.get("file_type"),
            "kb_id": doc.get("kb_id"),
            "kb_name": doc.get("kb_name"),
            "page_count": doc.get("page_count"),
            "created_at": doc.get("created_at"),
            "status": doc.get("status"),
            "content": content,
        }]


# ---- Tool: ask_expert ----

async def ask_expert(
    llm,
    retrieval_orch,
    context_assembler,
    auth,
    arguments: dict,
) -> list[dict]:
    """RAG 问答：检索 + LLM 生成答案 + 引用。

    使用 McpQueryPreparator（纯本地增强） → RetrievalOrchestrator.execute()
    → context_assembler → LLM 生成。
    """
    query = arguments.get("query", "")
    kb_ids: list[str] | None = arguments.get("kb_ids")
    top_k: int = arguments.get("top_k", 5)
    context_hint: str | None = arguments.get("context_hint")
    focus_aspects: list[str] | None = arguments.get("focus_aspects")

    if not query.strip():
        return [{"error": "query 不能为空"}]

    # 鉴权 + 三层权限交集
    effective = await _resolve_effective_kb_ids(auth, kb_ids)
    if effective is None:
        return [{"error": "鉴权失败或权限查询异常"}]
    if not effective:
        return [{"answer": "无权限访问任何匹配的知识库", "citations": []}]

    # MCP 查询准备 — jieba 关键词提取
    prepared = _preparator.prepare(
        query=query,
        top_k=top_k,
        context_hint=context_hint,
        focus_aspects=focus_aspects,
    )

    # 检索执行 — 共享执行层
    ctx = await retrieval_orch.execute(
        query=prepared.query,
        kb_ids=effective,
        keywords=prepared.keywords,
        top_k=prepared.top_k,
    )

    if not ctx.chunks:
        return [{"answer": "未找到相关文档。", "citations": []}]

    # LLM 生成 — 注入 context_hint 作为背景
    context = context_assembler.assemble(
        query=query,
        chunks=ctx.chunks,
        history=[],
    )

    # 如果有 context_hint，注入 system prompt 补充
    system_prompt = context.system_prompt
    if context_hint:
        system_prompt = (
            f"{system_prompt}\n\n"
            f"[Agent 提供的用户背景信息]\n{context_hint}"
        )

    try:
        response = await llm.generate_content(
            system_prompt=system_prompt,
            context=context.messages,
        )
    except Exception as e:
        return [{"answer": f"答案生成失败: {e}", "citations": []}]

    # 引用
    citations = []
    for i, c in enumerate(ctx.chunks[:top_k]):
        if c.chunk_id:
            citations.append({
                "index": i + 1,
                "chunk_id": c.chunk_id,
                "filename": c.source_file,
                "page_range": list(c.page_range) if c.page_range else None,
            })

    result: dict[str, Any] = {
        "query": query,
        "answer": response,
        "citations": citations,
    }
    if prepared.keywords:
        result["keywords_applied"] = prepared.keywords

    return [result]
