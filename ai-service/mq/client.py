"""RabbitMQ 客户端 — 连接管理、消息消费和回执发布。

对应 openapi.yaml 的 MQ 消息格式:
    Exchange: kes.document
    消费: document.ingest (Java → Python)
    发布: document.ingest.callback (Python → Java)
"""

import json

from common import get_logger
from models.config import RabbitMQConfig
from models.document import DocumentIngestMessage, IngestCallbackMessage

from .handler import IngestMessageHandler

logger = get_logger(__name__)


class MQClient:
    """RabbitMQ 异步客户端。

    负责:
    - 连接管理和自动重连
    - 消费 document.ingest 消息
    - 发布 document.ingest.callback 回执
    - manual ack（ETL 成功后才确认）
    """

    def __init__(self, config: RabbitMQConfig):
        self._config = config
        self._connection = None
        self._channel = None
        self._connected = False

    async def connect(self) -> None:
        """建立连接和 Channel。启动时调用。"""
        try:
            import aio_pika

            url = f"amqp://{self._config.user}:{self._config.password}@{self._config.host}:{self._config.port}/"
            self._connection = await aio_pika.connect_robust(url)
            self._channel = await self._connection.channel()
            # 设置 QoS：每次只取一条消息，处理完再取下一条
            await self._channel.set_qos(prefetch_count=1)
            self._connected = True
            logger.info(f"RabbitMQ 连接成功: {self._config.host}:{self._config.port}")
        except Exception as e:
            logger.warning(f"RabbitMQ 连接失败: {e}")
            self._connected = False

    async def close(self) -> None:
        """优雅关闭连接。"""
        if self._connection:
            await self._connection.close()
            self._connected = False
            logger.info("RabbitMQ 连接已关闭")

    async def ping(self) -> bool:
        """检查 RabbitMQ 连通性。"""
        return self._connected and self._connection is not None

    async def publish_callback(self, msg: IngestCallbackMessage) -> None:
        """发布入库完成回执。

        Exchange: kes.document
        Routing Key: document.ingest.callback
        """
        if not self._connected or self._channel is None:
            logger.warning("RabbitMQ 未连接，无法发布回执")
            return

        try:
            import aio_pika

            body = msg.model_dump_json().encode("utf-8")
            exchange = await self._channel.get_exchange(self._config.exchange)
            await exchange.publish(
                aio_pika.Message(
                    body=body,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=self._config.callback_routing_key,
            )
            logger.info(f"回执已发布: doc_id={msg.doc_id}, status={msg.status.value}")
        except Exception as e:
            logger.error(f"回执发布失败: {e}")

    async def consume_ingest(self, handler: IngestMessageHandler) -> None:
        """开始消费 document.ingest 消息。

        每条消息处理完成后 manual ack；处理失败时 nack 不 requeue（避免死循环）。

        Args:
            handler: 实现了 IngestMessageHandler 的 ETL 管道
        """
        if not self._connected or self._channel is None:
            logger.warning("RabbitMQ 未连接，无法消费消息")
            return

        import aio_pika

        # 声明 Exchange 和 Queue
        exchange = await self._channel.declare_exchange(
            self._config.exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        queue = await self._channel.declare_queue(
            "document.ingest",
            durable=True,
        )
        await queue.bind(exchange, routing_key=self._config.ingest_routing_key)

        logger.info(f"开始消费: {self._config.ingest_routing_key}")

        async with queue.iterator() as iterator:
            async for message in iterator:
                async with message.process(ignore_processed=True):
                    try:
                        # 反序列化消息
                        body = json.loads(message.body.decode("utf-8"))
                        ingest_msg = DocumentIngestMessage(**body)

                        logger.info(f"收到入库消息: doc_id={ingest_msg.doc_id}, type={ingest_msg.file_type}")

                        # 调用 ETL 管道处理
                        result = await handler.handle(ingest_msg)

                        # 发布回执
                        await self.publish_callback(result)

                        # 成功 → ack（message.process 上下文管理器自动处理）
                        if result.status.value == "completed":
                            logger.info(f"入库成功: doc_id={ingest_msg.doc_id}, chunks={result.chunks_created}")
                        else:
                            logger.error(f"入库失败: doc_id={ingest_msg.doc_id}, error={result.error_message}")

                    except Exception as e:
                        logger.error(f"消息处理异常: {e}")

                        # 构建失败回执
                        try:
                            body = json.loads(message.body.decode("utf-8"))
                            doc_id = body.get("doc_id", "unknown")
                            await self.publish_callback(IngestCallbackMessage(
                                doc_id=doc_id,
                                status="failed",
                                error_message=str(e),
                            ))
                        except Exception:
                            pass
