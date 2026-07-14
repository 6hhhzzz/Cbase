"""AI 原生治理管道三步单元测试。

覆盖 DocUnderstandStep / DocClassifyStep / UpdateKBSummaryStep 的核心逻辑，
全部 mock LLM 与 DB，不触碰真实网络/数据库。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from etl.steps.doc_understand_step import DocUnderstandStep
from etl.steps.doc_classify_step import DocClassifyStep
from etl.steps.kb_summary_step import UpdateKBSummaryStep


# ================================================================
# Helpers
# ================================================================

def make_chunk(text: str):
    """构造带 chunk_text 和真实 dict metadata 的轻量 chunk。"""
    return SimpleNamespace(chunk_text=text, metadata={})


def make_msg(kb_id: str | None = "kb-001", filename="report.pdf"):
    """构造带 metadata.kb_id 的轻量入库消息。"""
    return SimpleNamespace(filename=filename, metadata=SimpleNamespace(kb_id=kb_id))


def slm_returning(content: str):
    """返回一个 slm mock，其 generate_content 产出 content 字符串。"""
    slm = MagicMock()
    slm.generate_content = AsyncMock(
        return_value=SimpleNamespace(content=content)
    )
    return slm


# ================================================================
# DocUnderstandStep
# ================================================================

class TestDocUnderstandStep:

    async def test_happy_path_parses_json_and_injects_metadata(self):
        """合法 JSON（含 ```json 代码块包裹）→ 五字段正确 + 注入每个 chunk。"""
        json_body = (
            '```json\n'
            '{"summary": "本文是请假制度说明", "doc_type": "policy", '
            '"topics": ["请假", "考勤", "审批"], '
            '"key_entities": ["年假", "调休"], '
            '"not_covered": ["薪酬计算"]}\n'
            '```'
        )
        step = DocUnderstandStep(slm=slm_returning(json_body))
        chunks = [make_chunk("请假需提前申请。"), make_chunk("年假 5 天。")]
        ctx = {"chunks": chunks}

        result = await step.execute(ctx)

        meta = result["doc_metadata"]
        assert meta["doc_type"] == "policy"
        assert meta["summary"] == "本文是请假制度说明"
        assert meta["topics"] == ["请假", "考勤", "审批"]
        assert meta["key_entities"] == ["年假", "调休"]
        assert meta["not_covered"] == ["薪酬计算"]
        # 已注入到每个 chunk 的 metadata
        for c in chunks:
            assert c.metadata["doc_doc_type"] == "policy"
            assert c.metadata["doc_topics"] == ["请假", "考勤", "审批"]

    async def test_slm_failure_falls_back_to_empty_metadata(self):
        """SLM 抛异常 → 降级为空元数据默认值（doc_type=manual）。"""
        slm = MagicMock()
        slm.generate_content = AsyncMock(side_effect=RuntimeError("LLM 超时"))
        step = DocUnderstandStep(slm=slm)
        ctx = {"chunks": [make_chunk("任意内容")]}

        result = await step.execute(ctx)

        meta = result["doc_metadata"]
        assert meta["doc_type"] == "manual"
        assert meta["summary"] == ""
        assert meta["topics"] == []
        assert meta["key_entities"] == []
        assert meta["not_covered"] == []

    async def test_empty_chunks_returns_empty_metadata(self):
        """空 chunks → doc_metadata == {}，且不调用 LLM。"""
        slm = slm_returning("{}")
        step = DocUnderstandStep(slm=slm)

        result = await step.execute({"chunks": []})

        assert result["doc_metadata"] == {}
        slm.generate_content.assert_not_called()


# ================================================================
# DocClassifyStep
# ================================================================

class TestDocClassifyStep:

    async def test_action_existing_sets_target_kb(self):
        """action=existing → target_kb_id 取 LLM 返回的 kb_id。"""
        body = (
            '{"action": "existing", "kb_id": "kb-hr-001", '
            '"reasoning": "主题匹配人力资源库"}'
        )
        step = DocClassifyStep(slm=slm_returning(body))
        ctx = {
            "doc_metadata": {"summary": "请假制度", "topics": ["请假"], "doc_type": "policy"},
            "msg": make_msg(kb_id="kb-fallback"),
        }

        result = await step.execute(ctx)

        assert result["kb_action"] == "existing"
        assert result["target_kb_id"] == "kb-hr-001"

    async def test_action_create_sets_new_kb_name(self):
        """action=create → kb_action=create + new_kb_name。"""
        body = (
            '{"action": "create", "kb_id": null, '
            '"new_kb_name": "考勤制度库", "new_kb_description": "考勤相关制度"}'
        )
        step = DocClassifyStep(slm=slm_returning(body))
        ctx = {
            "doc_metadata": {"summary": "考勤", "topics": ["考勤"], "doc_type": "policy"},
            "msg": make_msg(),
        }

        result = await step.execute(ctx)

        assert result["kb_action"] == "create"
        assert result["new_kb_name"] == "考勤制度库"
        assert result["target_kb_id"] is None

    async def test_supersedes_detected(self):
        """检测到替代关系 → 写入 supersedes_title。"""
        body = (
            '{"action": "existing", "kb_id": "kb-001", '
            '"supersedes": "2023 版请假制度"}'
        )
        step = DocClassifyStep(slm=slm_returning(body))
        ctx = {
            "doc_metadata": {"summary": "请假 2024", "topics": ["请假"]},
            "msg": make_msg(),
        }

        result = await step.execute(ctx)

        assert result["supersedes_title"] == "2023 版请假制度"

    async def test_slm_failure_falls_back_to_msg_kb_id(self):
        """SLM 异常 → 回落 msg.metadata.kb_id。"""
        slm = MagicMock()
        slm.generate_content = AsyncMock(side_effect=ValueError("bad json"))
        step = DocClassifyStep(slm=slm)
        ctx = {
            "doc_metadata": {"summary": "x", "topics": ["y"]},
            "msg": make_msg(kb_id="kb-original"),
        }

        result = await step.execute(ctx)

        assert result["kb_action"] == "existing"
        assert result["target_kb_id"] == "kb-original"

    async def test_empty_metadata_short_circuits(self):
        """无 doc_metadata → 直接用 msg.metadata.kb_id，不调用 LLM。"""
        slm = slm_returning("{}")
        step = DocClassifyStep(slm=slm)
        ctx = {"doc_metadata": {}, "msg": make_msg(kb_id="kb-x")}

        result = await step.execute(ctx)

        assert result["target_kb_id"] == "kb-x"
        assert result["kb_action"] == "existing"
        slm.generate_content.assert_not_called()

    async def test_fetch_kb_list_without_pool_returns_empty(self):
        """ctx 无 orchestrator → _fetch_kb_list 返回 []。"""
        step = DocClassifyStep(slm=slm_returning("{}"))
        kbs = await step._fetch_kb_list({"msg": make_msg()})
        assert kbs == []

    def test_format_kb_list_empty(self):
        step = DocClassifyStep(slm=slm_returning("{}"))
        assert "暂无" in step._format_kb_list([])


# ================================================================
# UpdateKBSummaryStep
# ================================================================

def make_pool_with_rows(rows):
    """构造一个 async pool，其 conn.fetch 返回给定 rows。"""
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    conn.fetchrow = AsyncMock(return_value={"space_id": "space-001"})

    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool


class TestUpdateKBSummaryStep:

    async def test_aggregate_topics_dedupes_and_preserves_order(self):
        """重复 topics → 去重且保持首次出现顺序。"""
        rows = [
            {"topics": ["请假", "考勤"]},
            {"topics": ["考勤", "审批"]},
            {"topics": ["请假", "调休"]},
        ]
        step = UpdateKBSummaryStep()
        pool = make_pool_with_rows(rows)

        topics = await step._aggregate_topics(pool, "kb-001")

        assert topics == ["请假", "考勤", "审批", "调休"]

    async def test_aggregate_topics_parses_json_string_rows(self):
        """topics 以 JSON 字符串存储时也能解析。"""
        rows = [{"topics": '["请假", "考勤"]'}]
        step = UpdateKBSummaryStep()
        pool = make_pool_with_rows(rows)

        topics = await step._aggregate_topics(pool, "kb-001")

        assert topics == ["请假", "考勤"]

    async def test_execute_without_pool_skips_gracefully(self):
        """无 pool → 优雅跳过，不抛异常，原样返回 ctx。"""
        step = UpdateKBSummaryStep()
        step._get_pool = AsyncMock(return_value=None)
        ctx = {"msg": make_msg(kb_id="kb-001")}

        result = await step.execute(ctx)

        assert result is ctx

    async def test_execute_without_kb_id_returns_early(self):
        """无 kb_id → 提前返回。"""
        step = UpdateKBSummaryStep()
        ctx = {"msg": make_msg(kb_id=None)}

        result = await step.execute(ctx)

        assert result is ctx

    async def test_get_space_id_reads_row(self):
        step = UpdateKBSummaryStep()
        pool = make_pool_with_rows([])
        space_id = await step._get_space_id(pool, "kb-001")
        assert space_id == "space-001"
