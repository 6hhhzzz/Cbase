"""上下文组装 + Grounding 校验 — 检索后、LLM 生成前。

从 orchestrator.py 提取，纯数据转换函数。
"""

import re

from common import get_logger

logger = get_logger(__name__)


def assemble_grouped_context(ctx, max_chars_per_sq: int) -> str:
    """按 DAG 子查询分组排列检索结果。

    Args:
        ctx: RetrievalContext（含 sub_query_groups + upstream_contexts）
        max_chars_per_sq: 每个子查询的最大字符预算

    Returns:
        分组后的文本
    """
    sections = []
    sq_count = len(ctx.sub_query_groups)
    per_sq_budget = max_chars_per_sq // max(sq_count, 1)

    # 推理链概述
    if sq_count > 1:
        sections.append(f"## 推理链路\n以下检索结果来自 {sq_count} 个不同角度的子查询，请综合各角度信息。\n")

    for sq_id, chunk_ids in ctx.sub_query_groups.items():
        sq_chunks = [c for c in ctx.chunks if c.chunk_id in chunk_ids]
        if not sq_chunks:
            continue

        # 取上游上下文（如有）
        upstream_ctx = ctx.upstream_contexts.get(sq_id)
        reasoning_note = ""
        if upstream_ctx and upstream_ctx.reasoning_state:
            reasoning_note = f"\n> 推理中间态：{upstream_ctx.reasoning_state[:200]}\n"

        sections.append(f"\n### 检索角度 {sq_id}{reasoning_note}")

        chars = 0
        for c in sq_chunks[:3]:  # 每子查询最多 3 条
            # parent_content 存在时不截断（保留完整语义单元）
            has_parent = c.metadata.get("parent_content") if hasattr(c, "metadata") else False
            max_chars = 2000 if has_parent else 300
            text = f"[来源: {c.source_file} (相关度: {c.score:.2f})]\n{c.content[:max_chars]}\n"
            if chars + len(text) > per_sq_budget:
                break
            sections.append(text)
            chars += len(text)

    return "\n".join(sections)


def validate_grounding(answer: str, sources: list) -> bool:
    """检查 LLM 输出是否包含至少一个引用标记。

    无来源时不校验（返回 True）。
    """
    if not sources:
        return True
    has_ref = bool(re.search(r'\[Ref\s*\d+\]|\[来源:', answer))
    if not has_ref:
        logger.warning("LLM 生成结果无引用标记，疑似幻觉，拦截")
        return False
    return True
