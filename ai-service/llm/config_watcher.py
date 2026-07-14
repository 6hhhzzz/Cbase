"""配置文件热重载 — 基于 mtime 的异步监控。

从 model_pool.py 提取，独立类可复用。
"""

import asyncio
import os
from pathlib import Path

from common import get_logger

logger = get_logger(__name__)


class ConfigWatcher:
    """配置文件 mtime 监控器。

    定期检查文件修改时间，变化时调用回调重建池。
    """

    def __init__(self, config_path: Path, callback):
        self._config_path = config_path
        self._callback = callback
        self._config_mtime: float = 0
        self._lock = asyncio.Lock()

    async def watch_loop(self, interval: int = 30) -> None:
        """后台热重载循环：每 N 秒检查文件 mtime。"""
        while True:
            await asyncio.sleep(interval)
            try:
                if not self._config_path.exists():
                    continue
                mtime = self._config_path.stat().st_mtime
                if mtime > self._config_mtime:
                    logger.info(f"检测到 {self._config_path.name} 变更，热重载中...")
                    async with self._lock:
                        self._config_mtime = mtime
                        await self._callback()
                    logger.info("热重载完成")
            except Exception as e:
                logger.warning(f"热重载失败: {e}")
