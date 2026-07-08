from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(level: str = "INFO") -> None:
    """配置 structlog + 标准库 logging，统一输出 JSON 日志。

    业务代码主要使用 structlog 写日志；但 uvicorn、SQLAlchemy 和很多第三方库
    仍然通过 Python 标准库 logging 输出日志，所以这里要把两套日志接到一起。
    """

    log_level = getattr(logging, level.upper(), logging.INFO)

    # 这些处理器会同时作用于 structlog 日志和标准库 logging 日志，
    # 这样 request_id 等上下文字段在两类日志里都保持同一种结构。
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    # ProcessorFormatter 会把普通 logging 记录转换成和 structlog 一样的 JSON 格式。
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # 默认压低噪音较大的依赖日志；调试 SQL 或 HTTP 底层问题时可以再调高。
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
