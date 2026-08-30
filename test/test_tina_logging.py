"""Tina 默认 DEBUG，启动时应压到 INFO，控制台保持 ERROR。"""
import logging

from app.core.logging_setup import configure_tina_logging


def test_configure_tina_logging_drops_debug_from_console_and_file():
    configure_tina_logging()
    tina = logging.getLogger("tina")
    assert tina.level == logging.INFO
    assert tina.propagate is False

    stream_levels = []
    file_levels = []
    for handler in tina.handlers:
        if type(handler) is logging.StreamHandler:
            stream_levels.append(handler.level)
        elif isinstance(handler, logging.FileHandler):
            file_levels.append(handler.level)

    assert stream_levels and all(level >= logging.ERROR for level in stream_levels)
    assert file_levels and all(level >= logging.INFO for level in file_levels)
    assert not tina.isEnabledFor(logging.DEBUG)
