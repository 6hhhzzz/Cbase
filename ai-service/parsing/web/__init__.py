"""网页文档解析器集合。"""

from .html import HtmlParser
from .markdown import MarkdownParser
from .text import TextParser

__all__ = ["HtmlParser", "MarkdownParser", "TextParser"]
