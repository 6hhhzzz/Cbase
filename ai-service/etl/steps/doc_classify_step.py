"""DocClassifyStep — 文档自动分类归档。

在 DocUnderstandStep 之后运行，读 doc_metadata + 已有 KB 列表 → SLM 决策：
  - 归入现有 KB 或 新建 KB
  - 检测 supersedes 关系
  - 更新 KB 摘要

产出: ctx["target_kb_id"] + ctx["kb_action"]（existing | create）
"""

import json
import re

from common import get_logger
from llm.base import BaseLLM
from .base import PipelineStep

logger = get_logger(__name__)

_CLASSIFY_PROMPT = """你是知识库管理专家。需要为一份新文档选择最合适的知识库。

## 新文档信息
- 标题: {doc_title}
- 类型: {doc_type}
- 摘要: {summary}
- 主题: {topics}
- 关键实体: {entities}

## 已有知识库
{kb_list}

## 任务
1. 新文档最适合放入哪个已有 KB？（匹配 topics 和内容范围）
2. 如果没有任何 KB 匹配，建议创建新 KB（给出 name 和 description）
3. 检测文档是否声明了替代旧文档（如开头有「替代: <旧文档名>」）

## 输出 JSON
{{
  "action": "existing|create",
  "kb_id": "如果 action=existing，填已有 KB 的 ID；否则填 null",
  "new_kb_name": "如果 action=create，填建议的 KB 名称",
  "new_kb_description": "如果 action=create，填 KB 描述",
  "supersedes": "如果检测到替代关系，填被替代的文档标题，否则填 null",
  "reasoning": "简短说明分类理由"
}}

只返回 JSON。"""


class DocClassifyStep(PipelineStep):
    """文档自动分类步骤。

    输入: ctx["doc_metadata"] + ctx["msg"].metadata
    产出: ctx["target_kb_id"] + ctx["kb_action"]
    """

    def __init__(self, slm: BaseLLM):
        self._slm = slm

    async def execute(self, ctx: dict) -> dict:
        doc_meta = ctx.get("doc_metadata", {})
        msg = ctx.get("msg")

        if not doc_meta or not msg:
            ctx["target_kb_id"] = msg.metadata.kb_id if msg else None
            ctx["kb_action"] = "existing"
            return ctx

        # 获取已有 KB 列表
        existing_kbs = await self._fetch_kb_list(ctx)
        kb_list_text = self._format_kb_list(existing_kbs)

        doc_title = getattr(msg, "filename", "") or doc_meta.get("summary", "")[:50]
        prompt = _CLASSIFY_PROMPT.format(
            doc_title=doc_title,
            doc_type=doc_meta.get("doc_type", "manual"),
            summary=doc_meta.get("summary", ""),
            topics=", ".join(doc_meta.get("topics", [])),
            entities=", ".join(doc_meta.get("key_entities", [])),
            kb_list=kb_list_text,
        )

        try:
            response = await self._slm.generate_content(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

            data = json.loads(text)
            action = data.get("action", "existing")

            if action == "create":
                ctx["kb_action"] = "create"
                ctx["new_kb_name"] = data.get("new_kb_name", "未命名知识库")
                ctx["new_kb_description"] = data.get("new_kb_description", "")
                ctx["target_kb_id"] = None
                logger.info(f"DocClassify: 建议新建 KB「{ctx['new_kb_name']}」")
            else:
                ctx["kb_action"] = "existing"
                ctx["target_kb_id"] = data.get("kb_id") or msg.metadata.kb_id
                logger.info(f"DocClassify: 归入已有 KB {ctx['target_kb_id']}")

            # supersedes 检测
            supersedes = data.get("supersedes")
            if supersedes:
                ctx["supersedes_title"] = supersedes
                logger.info(f"DocClassify: 检测到替代关系 → {supersedes}")

            ctx["classify_reasoning"] = data.get("reasoning", "")

        except Exception as e:
            logger.warning(f"DocClassify 失败，使用默认 KB: {e}")
            ctx["kb_action"] = "existing"
            ctx["target_kb_id"] = msg.metadata.kb_id if msg else None

        return ctx

    async def _fetch_kb_list(self, ctx: dict) -> list[dict]:
        """从数据库获取当前 Space 下的 KB 列表。"""
        try:
            # 尝试通过 orchestrator 获取 pgvector pool
            pool = None
            if hasattr(ctx.get("_orchestrator"), "_hybrid_search"):
                pool = ctx["_orchestrator"]._hybrid_search._dense._pgvector.pool
            if not pool:
                return []

            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT kb.id, kb.name, kb.description
                    FROM knowledge_bases kb
                    WHERE kb.space_id = (
                        SELECT kb2.space_id FROM knowledge_bases kb2
                        WHERE kb2.id = $1 LIMIT 1
                    ) AND kb.deleted_at IS NULL
                """, ctx["msg"].metadata.kb_id)
                return [{"id": r["id"], "name": r["name"], "description": r["description"]} for r in rows]
        except Exception:
            return []

    def _format_kb_list(self, kbs: list[dict]) -> str:
        if not kbs:
            return "（暂无已有知识库）"
        lines = []
        for kb in kbs:
            desc = kb.get("description", "")[:80] or "无描述"
            lines.append(f"- KB ID: {kb['id']}\n  名称: {kb['name']}\n  描述: {desc}")
        return "\n".join(lines)
