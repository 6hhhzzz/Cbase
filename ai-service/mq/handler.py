"""RabbitMQ 消息消费处理接口。由 ETL 模块实现。"""

from abc import ABC, abstractmethod

from models.document import DocumentIngestMessage, IngestCallbackMessage


class IngestMessageHandler(ABC):
    """文档入库消息处理器接口。

    ETL 管道实现此接口，被 MQClient 回调。
    """

    @abstractmethod
    async def handle(self, msg: DocumentIngestMessage) -> IngestCallbackMessage:
        """处理一条入库消息。

        Args:
            msg: 文档入库消息

        Returns:
            IngestCallbackMessage(status=completed) 成功
            IngestCallbackMessage(status=failed, error_message=...) 失败
        """
        ...
