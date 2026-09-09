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
    file_level_no = logging._nameToLevel.get(file_level.upper(), logging.INFO)
    console_level_no = logging._nameToLevel.get(console_level.upper(), logging.ERROR)

    try:
        from tina.core import logger as tina_logger
    except ImportError:
        tina = logging.getLogger("tina")
        tina.setLevel(file_level_no)
        tina.propagate = False
        _enforce_tina_handler_levels(tina, file_level_no, console_level_no)
        return

    tina_logger.set_level(file_level)
    tina_logger.set_console_level(console_level)
    tina = tina_logger.get_logger()
    tina.propagate = False
    _enforce_tina_handler_levels(tina, file_level_no, console_level_no)
    logger.info(
        "Tina 日志已限制：file=%s console=%s",
        file_level,
        console_level,
    )


def _enforce_tina_handler_levels(
    tina: logging.Logger, file_level_no: int, console_level_no: int
) -> None:
    """Tina 可能挂多个 FileHandler；把未设级别的一并抬到约定阈值。"""
    for handler in tina.handlers:
        if type(handler) is logging.StreamHandler:
            handler.setLevel(max(handler.level or 0, console_level_no))
        elif isinstance(handler, logging.FileHandler):
            handler.setLevel(max(handler.level or 0, file_level_no))
