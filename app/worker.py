"""
独立 Worker 进程 — 处理重计算任务（OCR / 解析 / 出题 / 索引）

启动方式：
    python -m app.worker
    
与 API 分开部署，可绑 GPU 资源。
"""
import logging
import signal
import sys
import time

from app.core.redis_queue import dequeue_job, update_job_status
from app.worker.handlers import handle_ocr_job, handle_parse_job, handle_question_gen_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker")

HANDLERS = {
    "ocr": handle_ocr_job,
    "parse": handle_parse_job,
    "question_gen": handle_question_gen_job,
}

_running = True


def shutdown(signum, frame):
    global _running
    logger.info("收到信号 %s，正在优雅退出...", signum)
    _running = False


def main():
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Worker 已启动，等待任务...")

    while _running:
        try:
            job = dequeue_job(timeout=5)
            if job is None:
                continue

            job_id = job["job_id"]
            job_type = job["type"]
            user_id = job["user_id"]
            payload = job["payload"]

            logger.info(
                "处理任务: type=%s job_id=%s user_id=%s",
                job_type,
                job_id,
                user_id,
            )

            update_job_status(job_id, "processing", progress=0)

            handler = HANDLERS.get(job_type)
            if handler is None:
                update_job_status(
                    job_id,
                    "failed",
                    error=f"未知任务类型: {job_type}",
                )
                logger.warning("未知任务类型: %s", job_type)
                continue

            handler(job_id, user_id, payload)

        except Exception as e:
            logger.exception("Worker 主循环异常")
            time.sleep(1)

    logger.info("Worker 已退出")


if __name__ == "__main__":
    main()