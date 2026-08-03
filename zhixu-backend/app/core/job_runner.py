"""
后台任务执行器 — 线程 + SessionLocal，或在线程中跑 asyncio 协程。

避免在 FastAPI async 路由里直接阻塞 LLM / OCR 等耗时操作。
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable, Coroutine, TypeVar

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

T = TypeVar("T")


def run_in_background(fn: Callable[[], None], *, name: str = "zhishi-bg") -> threading.Thread:
    thread = threading.Thread(target=fn, daemon=True, name=name)
    thread.start()
    return thread


def run_db_worker(worker: Callable) -> None:
    """执行 worker(db)，自动 commit / rollback 并关闭 Session。"""
    db = SessionLocal()
    try:
        worker(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_db_worker_safe(
    worker: Callable,
    *,
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    try:
        run_db_worker(worker)
    except Exception as exc:
        logger.exception("background db worker failed")
        if on_error:
            try:
                on_error(exc)
            except Exception:
                logger.exception("background db worker on_error failed")


def run_async_coro(coro: Coroutine[object, object, T]) -> T:
    """在线程中运行 async 协程（每次新建事件循环）。"""
    return asyncio.run(coro)
