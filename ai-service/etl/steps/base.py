"""ETL Pipeline Step 抽象基类。"""

from abc import ABC, abstractmethod
from typing import Any


class PipelineStep(ABC):
    """ETL 管道中的单个处理步骤。

    每个步骤接收一个 context dict，对其进行处理，并返回（可能修改过的）context。
    这种设计允许步骤按顺序链式执行，每个步骤只关注自己的职责。
    """

    @abstractmethod
    async def execute(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """执行此步骤并返回更新后的 context。

        Args:
            ctx: 当前管道上下文，至少包含 ``"msg"`` (DocumentIngestMessage)。

        Returns:
            更新后的上下文字典。
        """
        ...
