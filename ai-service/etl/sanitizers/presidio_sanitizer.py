"""脱敏器 — 对 L2/L3 文档进行敏感信息掩码替换。

规则（proposal 7.3）:
    身份证: 110101199001011234 → 110101****1234
    手机号: 13812345678 → 138****5678
    薪资:   年薪 50 万 → 年薪 [REDACTED]
    银行卡: 6222021234567890 → 6222****7890

L1 文档 → 跳过脱敏
L2/L3 文档 → 正则扫描 → 命中则掩码替换
"""

import re

from common import get_logger
from .base import BaseSanitizer

logger = get_logger(__name__)

# 脱敏规则列表（proposal 7.3）
_SANITIZE_RULES: list[tuple[re.Pattern, str]] = [
    # 身份证: 前6位 + 中间8位 + 后4位
    (re.compile(r"(?<![0-9])(\d{6})\d{8}(\d{4})(?![0-9])"), r"\1****\2"),
    # 手机号: 前3位 + 中间4位 + 后4位
    (re.compile(r"(?<![0-9])(1[3-9]\d)\d{4}(\d{4})(?![0-9])"), r"\1****\2"),
    # 银行卡: 前4位 + 中间8-12位 + 后4位
    (re.compile(r"(?<![0-9])(\d{4})\d{8,12}(\d{4})(?![0-9])"), r"\1****\2"),
    # 薪资
    (re.compile(r"(年薪|月薪|工资|收入)\s*[\d.,]+万?"), r"\1 [REDACTED]"),
    # 电子邮件
    (re.compile(r"([a-zA-Z0-9._%+-]{1,3})[a-zA-Z0-9._%+-]*@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"), r"\1***@\2"),
]


class PresidioSanitizer(BaseSanitizer):
    """基于正则的敏感信息脱敏器。

    注意: Presidio 完整集成需要安装 presidio-analyzer 和 presidio-anonymizer。
    当前实现使用正则规则作为基础脱敏方案。后续可扩展为 Presidio NER 识别。
    """

    def __init__(self):
        pass

    async def sanitize(
        self,
        text: str,
        security_level: int,
    ) -> tuple[str, bool]:
        """对文本执行脱敏。

        Args:
            text: 原始文本
            security_level: 文档密级 (1=公开, 2=内部, 3=机密)

        Returns:
            (脱敏后文本, 是否实际触发了脱敏)
        """
        # L1 文档不脱敏
        if security_level <= 1:
            return text, False

        has_sensitive = False
        result = text

        for pattern, replacement in _SANITIZE_RULES:
            if pattern.search(result):
                has_sensitive = True
                result = pattern.sub(replacement, result)

        if has_sensitive:
            logger.info(f"脱敏完成: 密级=L{security_level}")

        return result, has_sensitive
