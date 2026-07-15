"""MCP Resource 定义 — Agent 的"知识地图"，两个 Resource 覆盖全部检索决策。

Resource:
    doc://catalog         → 有权限的 KB 列表 + kb_summary
    doc://kb/{kb_id}/docs → KB 内文档列表（title, summary, type, topics, not_covered, status）

Agent 使用流程:
    ① catalog → 选一个 KB
    ② docs    → 扫描文档概览 → 判断哪些文档可能包含答案
    ③ search_chunks(doc_ids=[选中的文档]) → 精准检索
"""

import json

import httpx

from common import get_logger
from kes_mcp.auth import KeyAuthError, _JAVA_BASE

logger = get_logger(__name__)


def register_resources(server, components):
    """向 MCP Server 注册所有 Resource 的 schema 和读取处理。"""

    @server.list_resources()
    async def handle_list_resources():
        return [
            {
                "uri": "doc://catalog",
                "name": "知识库目录",
                "description": (
                    "当前用户有权限访问的所有知识库列表。"
                    "每个 KB 含 kb_summary——聚合了该 KB 内所有文档的主题摘要，"
                    "Agent 据此判断哪个 KB 可能包含目标信息。"
                    "建议在首次检索前先调用此 Resource。"
                ),
                "mimeType": "application/json",
            },
            {
                "uri": "doc://kb/{kb_id}/docs",
                "name": "知识库文档列表",
                "description": (
                    "指定 KB 内所有文档的概览列表。"
                    "每份文档含 summary（100-200 字）、doc_type、topics、"
                    "not_covered（文档明确不包含的内容）和 status（active/superseded/expired）。"
                    "Agent 据此判断哪些文档可能包含答案，"
                    "然后在 search_chunks 中传 doc_ids 精准限定检索范围。"
                ),
                "mimeType": "application/json",
            },
        ]

    @server.read_resource()
    async def handle_read_resource(uri):
        uri = str(uri)  # MCP SDK passes AnyUrl, convert to str
        if components.rate_limiter:
            allowed, retry_after = await components.rate_limiter.consume()
            if not allowed:
                logger.warning(f"Resource 被限流: {uri}")
                wait = max(1, int(retry_after))
                return _resource_error(
                    f"调用频率超限（突发容量 30 次，填充速率 1 次/秒），请在 {wait} 秒后重试"
                )

        if uri == "doc://catalog":
            return await _read_catalog(components)

        if uri.startswith("doc://kb/") and uri.endswith("/docs"):
            kb_id = uri[len("doc://kb/"):-len("/docs")]
            if kb_id:
                return await _read_kb_docs(components, kb_id)

        return _resource_error(f"Resource 不存在: {uri}")


# ---- Resource 实现 ----

async def _get_pool(components):
    if (components.retrieval_orch
        and components.retrieval_orch._hybrid_search
        and components.retrieval_orch._hybrid_search._dense
        and components.retrieval_orch._hybrid_search._dense._pgvector):
        return components.retrieval_orch._hybrid_search._dense._pgvector.pool
    return None


async def _get_auth_token(components) -> str | None:
    try:
        return await components.auth.ensure_token()
    except KeyAuthError:
        return None


# ---- doc://catalog ----

async def _read_catalog(components):
    """KB 列表 + kb_summary。"""
    token = await _get_auth_token(components)
    if not token:
        return _resource_error("鉴权失败")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{_JAVA_BASE}/api/auth/accessible-kbs",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            return _resource_error(f"权限查询失败 ({resp.status_code})")

        kbs = resp.json().get("data", [])

        # 按 scope_kb_ids 过滤
        if components.auth.scope_kb_ids:
            kbs = [k for k in kbs if k["kb_id"] in components.auth.scope_kb_ids]

        # 为每个 KB 生成 kb_summary：聚合该 KB 下所有文档的 topics
        pool = await _get_pool(components)
        catalog = []
        for k in kbs:
            kb_id = k["kb_id"]
            kb_summary = ""
            if pool:
                kb_summary = await _build_kb_summary(pool, kb_id)

            catalog.append({
                "kb_id": kb_id,
                "name": k.get("name"),
                "description": k.get("description"),
                "kb_summary": kb_summary,
                "doc_count": k.get("doc_count", 0),
                "space_type": k.get("space_type", "default"),
            })

        return json.dumps(catalog, ensure_ascii=False, indent=2)


async def _build_kb_summary(pool, kb_id: str) -> str:
    """聚合 KB 内所有文档的 topics 生成一句话摘要。"""
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT metadata->>'doc_summary' AS summary,
                       metadata->'doc_topics' AS topics
                FROM knowledge_chunks
                WHERE kb_id = $1 AND status = 'active'
                  AND metadata->>'doc_summary' IS NOT NULL
                  AND metadata->>'doc_summary' != ''
                LIMIT 20
            """, kb_id)

        if not rows:
            return ""

        # 聚合所有 topics，去重
        all_topics: list[str] = []
        for r in rows:
            topics = r["topics"]
            if isinstance(topics, str):
                topics = json.loads(topics)
            if isinstance(topics, list):
                all_topics.extend(topics)

        # 去重并取前 8 个
        seen = set()
        unique = []
        for t in all_topics:
            if t not in seen:
                seen.add(t)
                unique.append(t)
                if len(unique) >= 8:
                    break

        if unique:
            return "、".join(unique[:6])
        return ""

    except Exception as e:
        logger.warning(f"kb_summary 生成失败: {e}")
        return ""


# ---- doc://kb/{kb_id}/docs ----

async def _read_kb_docs(components, kb_id: str):
    """KB 内文档列表概览。"""
    pool = await _get_pool(components)
    if not pool:
        return _resource_error("检索组件未初始化")

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT ON (source_file)
                source_file AS doc_file,
                doc_id,
                metadata->>'doc_summary' AS summary,
                metadata->>'doc_type' AS doc_type,
                metadata->'doc_topics' AS topics,
                metadata->>'doc_not_covered' AS not_covered,
                doc_effective_date,
                doc_expiry_date,
                doc_version
            FROM knowledge_chunks
            WHERE kb_id = $1 AND status = 'active'
            ORDER BY source_file, chunk_index
            LIMIT 50
        """, kb_id)

    if not rows:
        return _resource_error("该 KB 无文档数据")

    from datetime import date
    today = date.today()

    docs = []
    for r in rows:
        topics = r["topics"]
        if isinstance(topics, str):
            topics = json.loads(topics)
        if not isinstance(topics, list):
            topics = []

        # 推断文档状态
        doc_status = "active"
        expiry = r["doc_expiry_date"]
        if expiry:
            if hasattr(expiry, 'year'):
                if expiry < today:
                    doc_status = "expired"
            elif isinstance(expiry, str) and expiry < str(today):
                doc_status = "expired"

        docs.append({
            "doc_id": r["doc_id"],
            "title": _doc_title(r["doc_file"] or ""),
            "doc_file": r["doc_file"],
            "summary": (r["summary"] or "")[:200],
            "doc_type": r["doc_type"] or "unknown",
            "topics": topics,
            "not_covered": r["not_covered"] or "",
            "status": doc_status,
            "version": r["doc_version"],
        })

    return json.dumps({
        "kb_id": kb_id,
        "document_count": len(docs),
        "documents": docs,
    }, ensure_ascii=False, indent=2)


def _doc_title(doc_file: str) -> str:
    """从文件路径提取文档标题。"""
    # 去掉路径前缀
    name = doc_file.rsplit("/", 1)[-1] if "/" in doc_file else doc_file
    # 去掉扩展名
    for ext in (".md", ".docx", ".pdf", ".txt", ".html"):
        if name.endswith(ext):
            name = name[:-len(ext)]
            break
    return name[:100]


def _resource_error(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)
