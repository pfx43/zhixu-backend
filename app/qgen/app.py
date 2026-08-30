"""出题内部 FastAPI。不对用户开放；探活 + 消费 queued job。"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.qgen import settings
from app.core.logging_setup import configure_tina_logging
from app.services.llm.llm_pool import llm_pool

logger = logging.getLogger(__name__)
configure_tina_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = asyncio.Event()
    task = None
    if settings.QGEN_CONSUME:
        from app.qgen.consumer import consume_loop

        task = asyncio.create_task(consume_loop(stop))
        logger.info("出题服务开始消费")
    yield
    stop.set()
    if task is not None:
        await task


app = FastAPI(title="知序出题服务", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok" if llm_pool.instance_count > 0 else "degraded",
        "llm_instances": llm_pool.instance_count,
        "consume": settings.QGEN_CONSUME,
    }
