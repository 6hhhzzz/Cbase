"""MCP stdio Server — 对外部 AI Agent 提供权限感知的知识检索。

启动: KES_API_KEY=xxx KES_SPACE_ID=sp-001 python -m kes_mcp.server

架构: 本文件为入口点，Tool/Resource/Prompt 定义和路由分散在独立模块中。
  - tools_def.py     — Tool schema + call_tool 路由
  - resources_def.py — Resource schema + read_resource 处理
  - prompts_def.py   — Prompt schema + get_prompt 生成
  - auth.py          — MCP 鉴权（API Key → Token 交换）
  - tools.py         — Tool 实现（search_chunks / read_document / ask_expert）
"""

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server

from common import get_logger
from kes_mcp.auth import MCPAuth
from kes_mcp.tools_def import register_tools
from kes_mcp.resources_def import register_resources
from kes_mcp.prompts_def import register_prompts

logger = get_logger(__name__)


class MCPComponents:
    """MCP 运行时组件 — 由 app lifespan 注入，通过对象传递消除全局可变状态。"""

    def __init__(self):
        self.retrieval_orch = None
        self.context_assembler = None
        self.llm = None
        self.embedding = None
        self.auth: MCPAuth | None = None


# ---- 组件引用（由 api/app.py lifespan 注入） ----
_components = MCPComponents()


def init_components(retrieval_orch, context_assembler, llm, embedding):
    """初始化 MCP 运行时组件。由 api/app.py 在 lifespan 中调用。"""
    _components.retrieval_orch = retrieval_orch
    _components.context_assembler = context_assembler
    _components.llm = llm
    _components.embedding = embedding


# ---- MCP Server 实例 ----
_server = Server("kes-mcp")
_auth = MCPAuth()
_components.auth = _auth

# 注册 Tool / Resource / Prompt 处理器
register_tools(_server, _components)
register_resources(_server, _components)
register_prompts(_server, _components)


# ---- 入口 ----

async def main():
    if not _auth.load_from_env():
        if not _auth.load_from_file():
            logger.warning("未配置 API Key（KES_API_KEY），将以无权限模式运行")

    if _components.retrieval_orch is None:
        logger.warning("检索组件未注入，search_chunks / ask_expert 将不可用")

    async with stdio_server() as (read_stream, write_stream):
        await _server.run(
            read_stream,
            write_stream,
            _server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
