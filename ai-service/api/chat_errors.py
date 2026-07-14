"""Chat 错误消息映射 — 从 chat.py 提取，集中管理用户可见的错误提示。"""

from typing import Mapping


# 错误码 → 中文错误消息
ERROR_MESSAGES: Mapping[str, str] = {
    "timeout": "抱歉，AI 服务响应超时，请稍后重试。",
    "auth": "抱歉，AI 服务认证失败，请联系管理员检查 API Key 配置。",
    "not_found": "抱歉，AI 模型未找到，请联系管理员检查模型配置。",
    "connect": "抱歉，AI 服务连接失败，请检查网络或服务状态。",
}

_DEFAULT_MESSAGE = "抱歉，AI 服务暂时不可用，请稍后重试。"


def get_error_message(error: str) -> str:
    """根据异常信息返回用户可见的错误消息。

    Args:
        error: 异常消息字符串

    Returns:
        中文错误提示
    """
    err_lower = error.lower()
    if "401" in error or "unauthorized" in err_lower or "authentication" in err_lower:
        return ERROR_MESSAGES["auth"]
    if "404" in error or "not found" in err_lower:
        return ERROR_MESSAGES["not_found"]
    if "timeout" in err_lower or "timed out" in err_lower:
        return ERROR_MESSAGES["timeout"]
    if "connect" in err_lower or "refused" in err_lower:
        return ERROR_MESSAGES["connect"]
    return _DEFAULT_MESSAGE + f"（错误：{error[:100]}）"
