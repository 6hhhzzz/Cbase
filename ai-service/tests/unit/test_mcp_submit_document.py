"""MCP submit_document Tool 单元测试。

重点覆盖：
  1. 空字段校验（doc_title / content / summary）—— 纯逻辑，无网络
  2. 鉴权失败降级
  3. 安全红线：传统 Space (space_type != ai_native) 必须拒绝提交

全部 mock auth 与 httpx，不触碰真实网络。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from kes_mcp.tools import submit_document
from kes_mcp.auth import KeyAuthError


# ================================================================
# Helpers
# ================================================================

def make_auth(token="ctx-token"):
    """构造 auth mock，ensure_token 返回给定 token。"""
    auth = MagicMock()
    auth.ensure_token = AsyncMock(return_value=token)
    return auth


def patch_httpx_get(space_type="ai_native", status_code=200, kb_id="kb-1"):
    """返回一个 patch 上下文，令 httpx.AsyncClient.get 产出指定 spaceType 的响应。"""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(
        return_value={"data": [{"spaceType": space_type, "kbId": kb_id}]}
    )

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.post = AsyncMock(return_value=SimpleNamespace(
        status_code=201, json=lambda: {"data": {"id": "doc-999"}}
    ))

    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=client)
    client_cm.__aexit__ = AsyncMock(return_value=False)

    return patch("kes_mcp.tools.httpx.AsyncClient", return_value=client_cm)


BASE_ARGS = {
    "doc_title": "请假制度",
    "content": "员工请假需提前一天申请。",
    "summary": "请假流程说明",
    "keywords": ["请假", "考勤"],
    "doc_type": "policy",
}


# ================================================================
# 空字段校验（发生在任何网络调用前）
# ================================================================

class TestValidation:

    async def test_empty_doc_title_rejected(self):
        args = {**BASE_ARGS, "doc_title": "   "}
        result = await submit_document(MagicMock(), make_auth(), args)
        assert "doc_title" in result[0]["error"]

    async def test_empty_content_rejected(self):
        args = {**BASE_ARGS, "content": ""}
        result = await submit_document(MagicMock(), make_auth(), args)
        assert "content" in result[0]["error"]

    async def test_empty_summary_rejected(self):
        args = {**BASE_ARGS, "summary": ""}
        result = await submit_document(MagicMock(), make_auth(), args)
        assert "summary" in result[0]["error"]


# ================================================================
# 鉴权失败
# ================================================================

class TestAuth:

    async def test_auth_failure_returns_error(self):
        auth = MagicMock()
        auth.ensure_token = AsyncMock(side_effect=KeyAuthError("token 过期"))
        result = await submit_document(MagicMock(), auth, dict(BASE_ARGS))
        assert "鉴权失败" in result[0]["error"]


# ================================================================
# 安全红线：传统 Space 拒绝提交
# ================================================================

class TestSpaceTypeGuard:

    async def test_default_space_rejected(self):
        """space_type=default → 拒绝，明确提示仅 ai_native 支持。"""
        with patch_httpx_get(space_type="default"):
            result = await submit_document(MagicMock(), make_auth(), dict(BASE_ARGS))
        assert "不支持 submit_document" in result[0]["error"]
        assert "ai_native" in result[0]["error"]

    async def test_no_kbs_treated_as_default_and_rejected(self):
        """accessible-kbs 为空 → 视为 default → 拒绝。"""
        resp = MagicMock()
        resp.status_code = 200
        resp.json = MagicMock(return_value={"data": []})
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        client_cm = MagicMock()
        client_cm.__aenter__ = AsyncMock(return_value=client)
        client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("kes_mcp.tools.httpx.AsyncClient", return_value=client_cm):
            result = await submit_document(MagicMock(), make_auth(), dict(BASE_ARGS))
        assert "error" in result[0]

    async def test_permission_query_failure_returns_error(self):
        """accessible-kbs 返回非 200 → 权限查询失败错误。"""
        resp = MagicMock()
        resp.status_code = 403
        resp.json = MagicMock(return_value={})
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        client_cm = MagicMock()
        client_cm.__aenter__ = AsyncMock(return_value=client)
        client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("kes_mcp.tools.httpx.AsyncClient", return_value=client_cm):
            result = await submit_document(MagicMock(), make_auth(), dict(BASE_ARGS))
        assert "权限查询失败" in result[0]["error"]


# ================================================================
# AI 原生 Space 放行（走到上传）
# ================================================================

class TestAiNativeSpaceAccepted:

    async def test_ai_native_space_uploads_and_returns_ok(self):
        """space_type=ai_native → 放行 → 上传成功返回 doc_id。"""
        with patch_httpx_get(space_type="ai_native", kb_id="kb-hr"):
            result = await submit_document(MagicMock(), make_auth(), dict(BASE_ARGS))
        assert result[0].get("status") == "ok"
        assert result[0].get("doc_id") == "doc-999"
