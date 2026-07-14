"""Critic Agent — 检索后反思（Stage 4, v12）。

触发条件：
  - top-3 chunks 平均分 < 0.5 → 知识存在验证 → 补充检索
  - 规则检测到文档时间/版本冲突 → SLM 裁决

动作：
  - 知识存在验证: SPLADE + BM25 联合 → "库里没有" vs "搜得不好"
  - 补充检索 (最多 1 次)
  - 文档冲突裁决 + 标签
  - 兜底反问: 补充检索也失败 → 生成澄清问题
"""

from common import get_logger

logger = get_logger(__name__)

# 阈值
LOW_CONFIDENCE_THRESHOLD = 0.5      # top-3 平均分低于此 → 触发 Critic
KNOWLEDGE_EXISTS_THRESHOLD = 0.1    # BM25/SPLADE ts_rank 低于此 → "库里没有"
FALLBACK_THRESHOLD = 0.4            # 补充检索后仍低于此 → 兜底反问


class CriticResult:
    """Critic 评估结果。"""

    def __init__(
        self,
        action: str = "pass",               # pass | supplement | not_in_kb | ask_user | conflict
        supplementary_results: list | None = None,
        conflict_label: str = "",
        clarification_question: str = "",
        note: str = "",
    ):
        self.action = action
        self.supplementary_results = supplementary_results or []
        self.conflict_label = conflict_label
        self.clarification_question = clarification_question
        self.note = note


class CriticAgent:
    """检索后反思代理 — 评估检索质量并采取行动。

    用法::

        critic = CriticAgent(llm, hybrid_search)
        result = await critic.evaluate(query, chunks, kb_ids)
    """

    def __init__(self, slm, hybrid_search):
        self._slm = slm
        self._hybrid_search = hybrid_search

    async def evaluate(
        self,
        query: str,
        chunks: list,
        kb_ids: list[str],
    ) -> CriticResult:
        """评估检索质量并采取行动。

        Args:
            query: 用户查询
            chunks: Reranker 精排后的 ScoredChunk 列表
            kb_ids: 权限过滤 kb_id 列表

        Returns:
            CriticResult（action + 补充结果/标签/反问）
        """
        if not chunks:
            return await self._handle_empty(query, kb_ids)

        # 1. 文档冲突检测（规则优先，不调 SLM）
        conflict_label = self._detect_document_conflict(chunks)
        if conflict_label:
            # 有冲突 → SLM 裁决
            conflict_result = await self._resolve_conflict(query, chunks)
            if conflict_result.get("has_conflict"):
                return CriticResult(
                    action="conflict",
                    conflict_label=conflict_result.get("resolution", conflict_label),
                )

        # 2. 置信度检查
        avg_score = sum(c.score for c in chunks[:3]) / min(len(chunks), 3)
        if avg_score >= LOW_CONFIDENCE_THRESHOLD:
            return CriticResult(action="pass")

        # 3. 知识存在验证（SPLADE + BM25，不调 LLM）
        exists = await self._verify_knowledge_exists(query, kb_ids)
        if not exists:
            return CriticResult(
                action="not_in_kb",
                note="知识库中未找到相关信息",
            )

        # 4. 补充检索
        supplementary_query = await self._generate_supplementary_query(query, chunks)
        if supplementary_query:
            try:
                supp_chunks = await self._hybrid_search.search(
                    supplementary_query, kb_ids, top_k=5
                )
                if supp_chunks:
                    # 补充成功
                    supp_avg = sum(c.score for c in supp_chunks[:3]) / min(len(supp_chunks), 3)
                    if supp_avg >= FALLBACK_THRESHOLD:
                        return CriticResult(
                            action="supplement",
                            supplementary_results=supp_chunks,
                            note=f"补充检索完成: '{supplementary_query[:40]}'",
                        )
            except Exception as e:
                logger.warning(f"补充检索失败: {e}")

        # 5. 兜底反问
        clarification = await self._generate_clarification(query, chunks)
        return CriticResult(
            action="ask_user",
            clarification_question=clarification,
            note="补充检索未能获得足够信息",
        )

    # ---- 内部方法 ----

    async def _verify_knowledge_exists(self, query: str, kb_ids: list[str]) -> bool:
        """BM25 验证：库里到底有没有相关内容。

        不调 LLM，只用检索模型判断。
        """
        try:
            if hasattr(self._hybrid_search, '_sparse'):
                bm25_results = await self._hybrid_search._sparse.search(
                    query, kb_ids, top_k=10
                )
                if bm25_results and any(r.score > KNOWLEDGE_EXISTS_THRESHOLD for r in bm25_results):
                    return True
                return False
        except Exception as e:
            logger.warning(f"知识存在验证失败: {e}")
            return True  # 保守：验证失败时假设存在，继续 Critic 流程

        return True

    def _detect_document_conflict(self, chunks: list) -> str:
        """规则驱动：检测文档时间/版本冲突。

        不调 SLM，纯规则判断。
        """
        if len(chunks) < 2:
            return ""

        # 收集文档元数据
        docs = {}
        for c in chunks[:5]:  # 只看 top-5
            source = c.source_file
            eff_date = c.metadata.get("doc_effective_date", "")
            version = c.metadata.get("doc_version", "")
            if source and eff_date:
                if source not in docs:
                    docs[source] = []
                docs[source].append((eff_date, version))

        # 检测同一 source 下是否存在多个版本
        for source, versions in docs.items():
            if len(versions) >= 2:
                dates = sorted(set(v[0] for v in versions if v[0]))
                if len(dates) >= 2:
                    return (
                        f"检测到文档 '{source}' 存在多个时间版本 "
                        f"({dates[0]} vs {dates[-1]})，可能存在内容冲突"
                    )

        return ""

    async def _resolve_conflict(self, query: str, chunks: list) -> dict:
        """SLM 裁决文档冲突。"""
        chunk_texts = "\n---\n".join(
            f"[{c.source_file} (date={c.metadata.get('doc_effective_date', 'N/A')})] {c.content[:200]}"
            for c in chunks[:3]
        )

        prompt = f"""以下两个文档片段存在潜在冲突。判断：
1. 是否存在实质性矛盾？
2. 如果存在，哪个更权威（考虑时间/版本/来源）？

文档片段：
{chunk_texts}

输出 JSON：
{{"has_conflict": true/false, "resolution": "冲突说明（如：2023年制度已废止，以2024年通知为准）"}}
"""

        try:
            response_wrapper = await self._slm.generate_content(prompt)
            response = (
                response_wrapper.content
                if hasattr(response_wrapper, "content")
                else str(response_wrapper)
            )
            import json, re
            response = response.strip()
            if response.startswith("```"):
                response = re.sub(r"^```(?:json)?\s*", "", response)
                response = re.sub(r"\s*```$", "", response)
            return json.loads(response)
        except Exception as e:
            logger.warning(f"冲突裁决失败: {e}")
            return {"has_conflict": False, "resolution": ""}

    async def _generate_supplementary_query(self, query: str, chunks: list) -> str:
        """生成补充检索查询。"""
        chunk_summary = "\n".join(
            f"[{c.source_file} score={c.score:.2f}] {c.content[:150]}"
            for c in chunks[:3]
        )

        prompt = f"""这些检索结果的平均置信度较低。判断这些信息是否足够回答用户问题。
如果不够，生成一个补充检索查询。

用户问题: {query}

检索结果:
{chunk_summary}

输出 JSON:
{{"sufficient": true/false, "supplementary_query": "补充检索查询（sufficient=false时填写）"}}
"""

        try:
            response_wrapper = await self._slm.generate_content(prompt)
            response = (
                response_wrapper.content
                if hasattr(response_wrapper, "content")
                else str(response_wrapper)
            )
            import json, re
            response = response.strip()
            if response.startswith("```"):
                response = re.sub(r"^```(?:json)?\s*", "", response)
                response = re.sub(r"\s*```$", "", response)
            data = json.loads(response)
            if not data.get("sufficient", True) and data.get("supplementary_query"):
                return data["supplementary_query"]
        except Exception as e:
            logger.warning(f"生成补充查询失败: {e}")

        return ""

    async def _generate_clarification(self, query: str, chunks: list) -> str:
        """生成兜底反问。"""
        chunk_summary = "\n".join(
            f"[{c.source_file}] {c.content[:150]}" for c in chunks[:3]
        ) if chunks else "（无检索结果）"

        prompt = f"""知识库中的信息不足以完整回答用户问题。请基于已检索到的部分信息，
生成一个友好的澄清问题（1-2句话），帮助用户缩小查询范围。

用户问题: {query}
已检索到的部分信息: {chunk_summary}

澄清问题:"""

        try:
            response_wrapper = await self._slm.generate_content(prompt)
            response = (
                response_wrapper.content
                if hasattr(response_wrapper, "content")
                else str(response_wrapper)
            )
            return response.strip() or "抱歉，我未能在知识库中找到相关信息。您能具体描述一下您想了解的内容吗？"
        except Exception as e:
            logger.warning(f"生成澄清问题失败: {e}")
            return "抱歉，我未能在知识库中找到相关信息。您能具体描述一下您想了解的内容吗？"

    async def _handle_empty(self, query: str, kb_ids: list[str]) -> CriticResult:
        """处理检索结果为空的情况。"""
        exists = await self._verify_knowledge_exists(query, kb_ids)
        if not exists:
            return CriticResult(action="not_in_kb", note="知识库中未找到相关信息")
        clarification = await self._generate_clarification(query, [])
        return CriticResult(action="ask_user", clarification_question=clarification)
