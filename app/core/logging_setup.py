"""第三方库日志级别。Tina 默认把 DEBUG 打到控制台旁路的文件 handler，并 propagate。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def configure_tina_logging(
    *,
    file_level: str = "INFO",
    console_level: str = "ERROR",
) -> None:
    """Tina 控制台只保留 ERROR+；文件与 logger 本身降到 INFO，避免刷屏。"""
    try:
        from tina.core import logger as tina_logger
    except ImportError:
        tina = logging.getLogger("tina")
        tina.setLevel(logging.INFO)
        tina.propagate = False
        return

    tina_logger.set_level(file_level)
    tina_logger.set_console_level(console_level)
    tina_logger.get_logger().propagate = False
    logger.info(
        "Tina 日志已限制：file=%s console=%s",
        file_level,
        console_level,
    )
