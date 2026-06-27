"""MCP Resource 定义与读取 — 增强版 KB 目录。

由 server.py 调用 register_resources() 注册到 MCP Server 实例。
"""

import json

import httpx

from common import get_logger
from kes_mcp.auth import KeyAuthError, _JAVA_BASE

logger = get_logger(__name__)


def register_resources(server, components):
    """向 MCP Server 注册 Resource 的 schema 和读取处理。"""

    @server.list_resources()
    async def handle_list_resources():
        return [
            {
                "uri": "doc://catalog",
                "name": "知识库目录",
                "description": (
                    "当前用户有权限访问的所有知识库列表，包含名称、描述、文档数量等概览信息。"
                    "建议在首次检索前先调用此 Resource 了解可用的知识库，"
                    "然后选择相关的 kb_id 传入 search_chunks 或 ask_expert 以缩小检索范围。"
                ),
                "mimeType": "application/json",
            },
        ]

    @server.read_resource()
    async def handle_read_resource(uri: str):
        if uri == "doc://catalog":
            try:
                token = await components.auth.ensure_token()
            except KeyAuthError as e:
                return _resource_error(f"鉴权失败: {e}")

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{_JAVA_BASE}/api/auth/accessible-kbs",
                    headers={"Authorization": f"Bearer {token}"},
                )
                kbs = resp.json().get("data", [])
                # 应用 scope_kb_ids 过滤
                if components.auth.scope_kb_ids:
                    kbs = [k for k in kbs if k["kb_id"] in components.auth.scope_kb_ids]

                catalog = [
                    {
                        "kb_id": k["kb_id"],
                        "name": k.get("name"),
                        "description": k.get("description"),
                        "visibility": k.get("visibility", "unknown"),
                        "doc_count": k.get("doc_count"),
                        "created_at": k.get("created_at"),
                    }
                    for k in kbs
                ]
                return [{"type": "text", "text": json.dumps(catalog, ensure_ascii=False, indent=2)}]
        return [{"type": "text", "text": json.dumps({"error": "Resource not found"})}]


def _resource_error(message: str) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps({"error": message}, ensure_ascii=False)}],
        "isError": True,
    }
