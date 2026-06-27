"""Prompt 模板基类。使用 jinja2 进行变量渲染。"""

from jinja2 import Template


class PromptTemplate:
    """可渲染的 Prompt 模板，支持 jinja2 语法。

    使用示例:
        tmpl = PromptTemplate("你好，{{ name }}！")
        result = tmpl.render(name="张三")  # "你好，张三！"
    """

    def __init__(self, template_str: str):
        self._template = Template(template_str)

    def render(self, **kwargs) -> str:
        """渲染模板，将变量替换为实际值。

        Args:
            **kwargs: 模板变量

        Returns:
            渲染后的字符串
        """
        return self._template.render(**kwargs)
