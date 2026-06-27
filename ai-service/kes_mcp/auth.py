"""MCP 鉴权 — API Key → context_token 交换 + 自动续期。

Token 来源优先级:
    1. 环境变量 KES_API_KEY + KES_SPACE_ID
    2. 文件 ~/.kes/mcp.json {"api_key":"...", "space_id":"..."}
"""

import json
import os
import time
from pathlib import Path

import httpx

from common import get_logger

logger = get_logger(__name__)

_JAVA_BASE = os.environ.get("KES_JAVA_URL", "http://localhost:8080")
_REFRESH_MARGIN = 300  # 过期前 5 分钟刷新


# ---- 自定义异常 ----

class KeyAuthError(RuntimeError):
    """API Key 鉴权相关错误的基类。"""


class KeyRevokedError(KeyAuthError):
    """API 密钥已被撤销。"""


class KeyExpiredError(KeyAuthError):
    """API 密钥已过期。"""


class KeyInvalidError(KeyAuthError):
    """无效的 API 密钥（不存在或格式错误）。"""


class KeyConnectionError(KeyAuthError):
    """无法连接到 Java 鉴权服务。"""


# ---- 鉴权管理器 ----

class MCPAuth:
    """MCP 鉴权管理器 — 缓存 Token，自动续期。"""

    def __init__(self):
        self._api_key: str | None = None
        self._space_id: str | None = None
        self._context_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: float = 0
        self._scope_kb_ids: list[str] | None = None  # Key 级 KB 白名单
        self._invalidated: bool = False       # Key 是否已确认失效
        self._invalidate_reason: str = ""     # 失效原因

    # ---- 初始化 ----

    def load_from_env(self) -> bool:
        """从环境变量加载 API Key。"""
        key = os.environ.get("KES_API_KEY")
        sid = os.environ.get("KES_SPACE_ID")
        if key and sid:
            self._api_key = key
            self._space_id = sid
            logger.info(f"MCP 鉴权: 从环境变量加载, space={sid}")
            return True
        return False

    def load_from_file(self, path: str = "~/.kes/mcp.json") -> bool:
        """从配置文件加载 API Key。"""
        try:
            cfg = json.loads(Path(path).expanduser().read_text())
            key = cfg.get("api_key")
            sid = cfg.get("space_id")
            if key and sid:
                self._api_key = key
                self._space_id = sid
                logger.info(f"MCP 鉴权: 从文件加载, space={sid}")
                return True
        except Exception:
            pass
        return False

    # ---- Token 管理 ----

    async def ensure_token(self) -> str:
        """确保有有效的 context_token，自动交换/续期。"""
        # 快速失败：Key 已确认失效
        if self._invalidated:
            raise self._build_cached_error()

        now = time.time()
        if self._context_token and now < self._token_expiry - _REFRESH_MARGIN:
            return self._context_token

        # 需要刷新
        if self._refresh_token and now < self._token_expiry + 86400:
            try:
                await self._do_refresh()
                return self._context_token
            except Exception as e:
                logger.warning(f"Token 刷新失败，重新交换: {e}")

        # 重新交换
        await self._do_exchange()
        return self._context_token

    async def _do_exchange(self) -> None:
        """POST /api/auth/mcp/exchange — 用 API Key 换 Token。"""
        if not self._api_key or not self._space_id:
            raise KeyInvalidError("未配置 API Key，无法鉴权。请设置 KES_API_KEY + KES_SPACE_ID")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{_JAVA_BASE}/api/auth/mcp/exchange",
                    json={"api_key": self._api_key, "space_id": self._space_id},
                )
        except httpx.TimeoutException:
            raise KeyConnectionError("无法连接到认证服务（超时）")
        except httpx.ConnectError:
            raise KeyConnectionError("无法连接到认证服务（连接失败）")
        except Exception as e:
            raise KeyConnectionError(f"认证服务网络异常: {e}")

        if resp.status_code == 401 or resp.status_code == 400:
            # 解析错误信息
            msg = self._parse_error_message(resp)
            if "已撤销" in msg:
                self._mark_invalidated(KeyRevokedError(msg))
                raise self._build_cached_error()
            elif "已过期" in msg:
                self._mark_invalidated(KeyExpiredError(msg))
                raise self._build_cached_error()
            elif "无效" in msg or "不存在" in msg:
                self._mark_invalidated(KeyInvalidError(msg))
                raise self._build_cached_error()
            else:
                raise KeyInvalidError(msg)

        if resp.status_code != 200:
            raise KeyConnectionError(f"认证服务异常 (HTTP {resp.status_code})")

        data = resp.json()["data"]
        self._context_token = data["context_token"]
        self._refresh_token = data["refresh_token"]
        self._token_expiry = time.time() + 1800
        # 缓存 scope_kb_ids（null = 无限制 → 存 None）
        scope = data.get("scope_kb_ids")
        self._scope_kb_ids = json.loads(scope) if isinstance(scope, str) else scope
        # 交换成功，清除失效状态
        self._invalidated = False
        self._invalidate_reason = ""
        logger.info(f"MCP Token 交换成功, scope={self._scope_kb_ids}")

    async def _do_refresh(self) -> None:
        """POST /api/auth/refresh — 用 refresh_token 续期。"""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_JAVA_BASE}/api/auth/refresh",
                headers={"Authorization": f"Bearer {self._refresh_token}"},
            )
            if resp.status_code != 200:
                raise KeyAuthError(f"Token 刷新失败 ({resp.status_code})")

            data = resp.json()["data"]
            self._context_token = data["context_token"]
            self._refresh_token = data.get("refresh_token", self._refresh_token)
            self._token_expiry = time.time() + 1800
            logger.info("MCP Token 已刷新")

    # ---- 错误处理 ----

    @staticmethod
    def _parse_error_message(resp: httpx.Response) -> str:
        """从 Java 响应中提取可读的错误消息。"""
        try:
            body = resp.json()
            return body.get("message", resp.text)
        except Exception:
            return resp.text

    def _mark_invalidated(self, error: KeyAuthError) -> None:
        """标记 Key 为已失效，后续调用直接失败不再重试。"""
        self._invalidated = True
        self._invalidate_reason = str(error)
        logger.warning(f"API Key 已标记失效: {self._invalidate_reason}")

    def _build_cached_error(self) -> KeyAuthError:
        """根据缓存的失效原因构造对应的异常。"""
        reason = self._invalidate_reason
        if "已撤销" in reason:
            return KeyRevokedError(reason)
        elif "已过期" in reason:
            return KeyExpiredError(reason)
        elif "无效" in reason:
            return KeyInvalidError(reason)
        return KeyAuthError(reason)

    # ---- 属性 ----

    @property
    def context_token(self) -> str | None:
        return self._context_token

    @property
    def space_id(self) -> str | None:
        return self._space_id

    @property
    def scope_kb_ids(self) -> list[str] | None:
        return self._scope_kb_ids
