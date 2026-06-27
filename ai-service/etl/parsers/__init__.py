# 文件解析器：按文件类型路由到对应的 Parser

from .base import BaseParser
from .registry import ParserRegistry

__all__ = ["BaseParser", "ParserRegistry"]
