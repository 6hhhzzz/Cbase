"""查询路由规则 — 闲聊检测 + Planner 触发判断（纯函数，无状态）。

从 orchestrator.py 提取，用于：
  - is_chitchat: 判断查询是否属于闲聊/寒暄（不需要检索文档）
  - should_plan: 规则前置判断是否需要调 QueryPlanner 做 DAG 拆解
  - plan_rule_reason: 返回 should_plan 的决策原因字符串
  - chunk_snapshot: 序列化 ScoredChunk 为 trace 用 dict
  - sub_query_summary: 序列化 SubQuery 为 trace 用 dict
"""

from .models import ScoredChunk, SubQuery

# ---- 复杂查询标记词（出现才调 Planner，否则直接 simple） ----
COMPLEX_MARKERS = [
    "对比", "比较", "区别", "优缺点", "分别", "综合",
    "分析", "评估", "为什么", "如何评估", "原因",
    "多个", "各个方面", "全面", "同时",
    "各有什么", "有什么不同", "有何不同", "异同",
    "两者", "二者", "两种", "各自的",
]

# ---- 闲聊/寒暄模式（不需要检索文档，直接 LLM 回答） ----
CHITCHAT_PATTERNS = [
    "你好", "您好", "嗨", "hello", "hi", "hey",
    "谢谢", "感谢", "多谢", "thanks", "thank",
    "再见", "拜拜", "bye", "晚安", "早安",
    "你是谁", "你叫什么", "你能做什么", "介绍一下自己",
    "今天天气", "讲个笑话", "聊聊天",
]

# 检索意图词 — 匹配这些词表示不是纯闲聊
_INTENT_WORDS = ["怎么", "如何", "什么", "为什么", "问题", "问一下", "请问",
                 "部署", "配置", "安装", "文档", "规范", "查", "找", "搜"]


def is_chitchat(query: str) -> bool:
    """检测查询是否属于闲聊/寒暄（不需要检索文档）。

    条件（必须同时满足）:
      1. 查询较短（≤15 字符）
      2. 匹配闲聊模式
      3. 不含检索意图词（问具体问题时不算闲聊）
    """
    q = query.strip().lower()
    if len(q) > 15:
        return False

    matched = any(p in q for p in CHITCHAT_PATTERNS)
    if not matched:
        return False

    for w in _INTENT_WORDS:
        if w in q:
            return False

    # 闲聊模式覆盖度过低 → 不是纯闲聊（如 "你好啊想问问题"）
    match_len = sum(len(p) for p in CHITCHAT_PATTERNS if p in q)
    if len(q) > 6 and match_len < len(q) * 0.4:
        return False

    return True


def should_plan(original_query: str, rewritten_query: str) -> bool:
    """规则前置：判断是否需要调 QueryPlanner（LLM）做 DAG 拆解。

    返回 True → 调 Planner；False → 跳过，强制 simple。
    """
    q = original_query.strip()
    if not q:
        return False

    # 先看有没有复杂标记（有标记 → 必须 Planner 判断）
    has_marker = any(m in q for m in COMPLEX_MARKERS)

    # 条件 1: 短查询无标记 → simple
    if len(q) <= 15 and not has_marker:
        return False

    # 条件 2: 有复杂标记 → 必须 Planner
    if has_marker:
        return True

    # 条件 3: 纯名词/术语查询（无问句、无动词、30 字以内）→ simple
    question_words = ["怎么", "如何", "什么", "为什么", "怎样", "是否", "能不能", "可以", "多少"]
    has_question = any(w in q for w in question_words)
    has_action = any(w in q for w in ["部署", "安装", "配置", "排查", "优化", "迁移", "升级", "设计", "实现"])
    if not has_question and not has_action and len(q) <= 30:
        return False

    return True


def plan_rule_reason(original_query: str) -> str:
    """返回 should_plan 的决策原因字符串（供 trace 记录）。"""
    q = original_query.strip()
    if not q:
        return "empty_query"
    has_marker = any(m in q for m in COMPLEX_MARKERS)
    if len(q) <= 15 and not has_marker:
        return "short_query_no_marker"
    if has_marker:
        return "complex_marker"
    question_words = ["怎么", "如何", "什么", "为什么", "怎样", "是否", "能不能", "可以", "多少"]
    has_question = any(w in q for w in question_words)
    has_action = any(w in q for w in ["部署", "安装", "配置", "排查", "优化", "迁移", "升级", "设计", "实现"])
    if not has_question and not has_action and len(q) <= 30:
        return "noun_phrase"
    return "default"


def chunk_snapshot(c: ScoredChunk, include_snippet: bool = True) -> dict:
    """将 ScoredChunk 序列化为 trace 用的精简 dict。"""
    d = {
        "chunk_id": c.chunk_id,
        "doc_id": c.metadata.get("doc_id", "") if c.metadata else "",
        "doc_title": c.source_file or "",
        "score": round(c.score, 4),
    }
    if include_snippet:
        d["snippet"] = (c.content or "")[:150]
    return d


def sub_query_summary(sq: SubQuery) -> dict:
    """将 SubQuery 序列化为 trace 用的概要 dict。"""
    return {
        "id": sq.id,
        "purpose": sq.purpose or "",
        "query": sq.query or "",
        "depends_on": list(sq.depends_on) if sq.depends_on else [],
        "hyde": sq.hyde,
        "needs_context": sq.needs_context,
    }
