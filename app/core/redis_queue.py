"""
Redis 任务队列 — 用于将重计算（OCR / 解析 / 出题）迁出 API 进程

设计：
    - 使用 Redis List 实现 FIFO 队列
    - 任务状态写入 Redis Hash
    - 生产禁用 job_runner daemon 线程，改用独立 Worker 进程

键规范：
    queue:jobs           — List，待处理任务 JSON
    job:status:{job_id}  — Hash，{state, progress, error, result, created_at, updated_at}
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

QUEUE_KEY = "queue:jobs"
JOB_STATUS_PREFIX = "job:status:"

# Redis 客户端（惰性初始化）
_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        import os
        import redis as _redis_lib

        redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        _redis = _redis_lib.from_url(redis_url, decode_responses=True)
        _redis.ping()
        logger.info("Redis 连接成功: %s", redis_url)
    return _redis


# ─── 入队（API 侧）──────────────────────────────────

def enqueue_job(
    job_type: str,
    user_id: int,
    payload: Dict[str, Any],
) -> str:
    """
    将任务入队，返回 job_id。
    
    Args:
        job_type: 任务类型（ocr / parse / question_gen / index）
        user_id: 用户 ID
        payload: 任务参数（如 document_id, file_hash 等）
    
    Returns:
        job_id (str)
    """
    redis = _get_redis()
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "type": job_type,
        "user_id": user_id,
        "payload": payload,
        "created_at": _now_iso(),
    }
    redis.rpush(QUEUE_KEY, json.dumps(job, ensure_ascii=False))
    redis.hset(
        f"{JOB_STATUS_PREFIX}{job_id}",
        mapping={
            "state": "pending",
            "progress": "0",
            "error": "",
            "result": "",
            "created_at": job["created_at"],
            "updated_at": job["created_at"],
        },
    )
    logger.info("enqueue_job: type=%s job_id=%s user_id=%s", job_type, job_id, user_id)
    return job_id


# ─── 出队（Worker 侧）────────────────────────────────

def dequeue_job(timeout: int = 5) -> Optional[Dict[str, Any]]:
    """
    阻塞式从队列取出一个任务（BLPOP）。
    
    Args:
        timeout: 阻塞超时（秒），0 表示无限等待
    
    Returns:
        job dict 或 None（超时）
    """
    redis = _get_redis()
    result = redis.blpop(QUEUE_KEY, timeout=timeout)
    if result is None:
        return None
    _, raw = result
    try:
        job = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("dequeue_job: 无法解析任务 JSON")
        return None
    return job


# ─── 状态更新（Worker 侧）─────────────────────────────

def update_job_status(
    job_id: str,
    state: str,
    progress: int = 0,
    error: str = "",
    result: str = "",
):
    """
    更新任务状态。
    
    Args:
        state: pending / processing / completed / failed
        progress: 0-100
        error: 错误信息（失败时）
        result: 结果 JSON（完成时）
    """
    redis = _get_redis()
    mapping = {
        "state": state,
        "progress": str(progress),
        "error": error,
        "result": result,
        "updated_at": _now_iso(),
    }
    redis.hset(f"{JOB_STATUS_PREFIX}{job_id}", mapping=mapping)


def get_job_status(job_id: str) -> Optional[Dict[str, str]]:
    """查询任务状态（API 侧：供前端轮询）"""
    redis = _get_redis()
    data = redis.hgetall(f"{JOB_STATUS_PREFIX}{job_id}")
    if not data:
        return None
    return dict(data)


# ─── 工具 ────────────────────────────────────────────

def _now_iso() -> str:
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).isoformat()