"""消费 queued job：同一用户一次只领一单；单内 Agent 数由配置限。"""
from __future__ import annotations

import asyncio
import logging

from app.qgen import client, settings
from app.qgen.runner import run_page

logger = logging.getLogger(__name__)


async def _run_one_page(job: dict, page: dict) -> tuple[int, str, list, dict | None, str]:
    page_number = int(page["page_number"])
    await asyncio.to_thread(client.mark_progress, job["job_id"], page_number)
    status, questions, usage, error = await run_page(job, page)
    return page_number, status, questions, usage, error


async def process_job(job: dict) -> None:
    job_id = job["job_id"]
    pages = [p for p in job.get("pages") or [] if p.get("status") in ("queued", "running")]
    pages.sort(key=lambda p: int(p["page_number"]))
    limit = settings.max_agents()
    sem = asyncio.Semaphore(limit)
    logger.info("出题 job=%s pages=%d max_agents=%d", job_id, len(pages), limit)

    async def _guarded(page: dict):
        async with sem:
            return await _run_one_page(job, page)

    results = await asyncio.gather(
        *[_guarded(page) for page in pages], return_exceptions=True
    )
    # 交卷串行，避免两页同时 complete 抢 job 状态
    for page, item in zip(pages, results):
        page_number = int(page["page_number"])
        if isinstance(item, Exception):
            logger.exception(
                "出题页失败: job_id=%s page=%s", job_id, page_number, exc_info=item
            )
            try:
                await asyncio.to_thread(
                    client.fail_page, job_id, page_number, "worker_exception"
                )
            except Exception:
                logger.exception("回报 fail 失败: job_id=%s page=%s", job_id, page_number)
            continue
        _, status, questions, usage, error = item
        try:
            if status == "ok":
                await asyncio.to_thread(
                    client.complete_page, job_id, page_number, questions, usage
                )
            else:
                await asyncio.to_thread(client.fail_page, job_id, page_number, error)
        except Exception:
            logger.exception("回报 complete/fail 失败: job_id=%s page=%s", job_id, page_number)


async def consume_loop(stop: asyncio.Event) -> None:
    logger.info(
        "出题消费循环已启动 main=%s max_agents=%d",
        settings.QGEN_MAIN_URL,
        settings.max_agents(),
    )
    while not stop.is_set():
        try:
            job = await asyncio.to_thread(client.claim_job)
        except Exception:
            logger.exception("claim 出题任务失败")
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.QGEN_POLL_SECONDS)
            except asyncio.TimeoutError:
                pass
            continue
        if job is None:
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.QGEN_POLL_SECONDS)
            except asyncio.TimeoutError:
                pass
            continue
        await process_job(job)
