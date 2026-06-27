"""脱敏器抽象基类。"""

from abc import ABC, abstractmethod


class BaseSanitizer(ABC):
    """PII 脱敏器抽象。所有脱敏实现必须继承此类。"""

    @abstractmethod
    async def sanitize(self, text: str, security_level: int) -> tuple[str, bool]:
        """对文本执行脱敏。

        Args:
            text: 原始文本
            security_level: 安全级别（1=跳过, 2=正则脱敏, 3=完整NER）

        Returns:
            (脱敏后文本, 是否检测到敏感信息)
        """
        ...
