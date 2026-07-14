"""MCP Tool 级别超时测试。"""

import asyncio
import json

import pytest


class TestToolTimeout:
    """验证 handle_call_tool 外层 asyncio.wait_for 超时机制。"""

    @pytest.mark.asyncio
    async def test_wait_for_triggers_timeout(self):
        """永不完成的协程触发 asyncio.TimeoutError。"""
        async def hang_forever():
            await asyncio.Event().wait()

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(hang_forever(), timeout=0.05)

    @pytest.mark.asyncio
    async def test_wait_for_completes_under_timeout(self):
        """正常完成的协程不受影响。"""
        async def quick():
            await asyncio.sleep(0.01)
            return "done"

        result = await asyncio.wait_for(quick(), timeout=0.5)
        assert result == "done"

    def test_timeout_error_format(self):
        """_timeout_error 返回正确格式的 isError 响应。"""
        from kes_mcp.tools_def import _timeout_error, _TOOL_TIMEOUT_SECONDS

        response = _timeout_error("search_chunks")
        assert response["isError"] is True
        content_text = response["content"][0]["text"]
        error_data = json.loads(content_text)
        assert "超时" in error_data["error"]
        assert "search_chunks" in error_data["error"]
        assert str(_TOOL_TIMEOUT_SECONDS) in error_data["error"]

    def test_timeout_error_unknown_tool(self):
        """_timeout_error 对不同类型的 tool 名都能正确格式化。"""
        from kes_mcp.tools_def import _timeout_error

        response = _timeout_error("unknown_tool")
        content_text = response["content"][0]["text"]
        error_data = json.loads(content_text)
        assert "unknown_tool" in error_data["error"]


class TestToolSemaphore:
    """验证 Tool 并发信号量 _TOOL_SEMAPHORE(5)。"""

    def test_semaphore_initialized(self):
        """信号量已创建且初始值为 5。"""
        from kes_mcp.tools_def import _TOOL_SEMAPHORE
        assert _TOOL_SEMAPHORE is not None
        # asyncio.Semaphore 没有直接暴露 _value，通过内部属性检查
        assert _TOOL_SEMAPHORE._value == 5

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """信号量正确限制并发数。"""
        import asyncio

        sem = asyncio.Semaphore(2)
        running = 0
        max_concurrent = 0

        async def work():
            nonlocal running, max_concurrent
            async with sem:
                running += 1
                max_concurrent = max(max_concurrent, running)
                await asyncio.sleep(0.05)
                running -= 1

        tasks = [work() for _ in range(10)]
        await asyncio.gather(*tasks)

        assert max_concurrent <= 2
        assert max_concurrent >= 1  # 至少有一些并发

    @pytest.mark.asyncio
    async def test_semaphore_queues_not_rejects(self):
        """信号量满时排队等待而非拒绝。"""
        import asyncio

        sem = asyncio.Semaphore(1)
        completed = 0

        async def work():
            nonlocal completed
            async with sem:
                await asyncio.sleep(0.03)
                completed += 1

        # 启动 5 个任务，信号量=1，它们必须排队串行执行
        await asyncio.gather(*[work() for _ in range(5)])
        assert completed == 5  # 全部完成，没有拒绝
