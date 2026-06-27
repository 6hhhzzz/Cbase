"""结构化日志配置。全服务统一使用此模块输出 JSON 格式日志。"""

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """将日志格式化为 JSON，便于日志采集和检索。"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """初始化根日志器，输出 JSON 结构化日志到 stdout。

    Args:
        level: 日志级别，默认 INFO

    Returns:
        根 logger
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper()))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    # 移除已有 handler，避免重复添加
    root.handlers.clear()
    root.addHandler(handler)

    # 抑制第三方库的 DEBUG 日志
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("aio_pika").setLevel(logging.WARNING)

    return root


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger。"""
    return logging.getLogger(name)
