"""意图分类 Prompt — 零样本分类，规则前置 + LLM 兜底。

架构师建议：
    - 正则匹配命中 → 直接路由，不调 LLM
    - 模糊不清的 Query 才丢给 LLM
"""

from .base import PromptTemplate

INTENT_PROMPT = PromptTemplate("""分类用户查询意图，只返回以下四个标签之一：
- factoid: 查找具体事实、数据、定义
- summary: 了解某个主题的概览、概述、总结
- compare: 对比多个对象之间的区别
- howto: 询问操作方法、步骤、流程

只返回意图标签，不要解释。

用户查询：{{ query }}

意图：""")
