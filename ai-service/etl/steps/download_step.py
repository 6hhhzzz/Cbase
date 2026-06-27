"""MinIO 文件下载步骤。"""

import asyncio
import os
import tempfile
from typing import TYPE_CHECKING

from common import get_logger
from .base import PipelineStep

if TYPE_CHECKING:
    from minio import Minio

logger = get_logger(__name__)


class DownloadStep(PipelineStep):
    """从 MinIO 下载文件到本地临时路径。"""

    def __init__(self, minio_client: "Minio", minio_bucket: str):
        self._minio_client = minio_client
        self._minio_bucket = minio_bucket

    async def execute(self, ctx: dict) -> dict:
        msg = ctx["msg"]
        object_key = msg.file_path

        original_name = os.path.basename(object_key) or "download.tmp"
        fd, temp_path = tempfile.mkstemp(suffix=f"_{original_name}")
        os.close(fd)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._minio_client.fget_object(
                self._minio_bucket, object_key, temp_path,
            ),
        )
        logger.info(f"MinIO 下载完成: bucket={self._minio_bucket}, key={object_key}")
        ctx["temp_path"] = temp_path
        return ctx
