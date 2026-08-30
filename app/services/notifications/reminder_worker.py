"""提醒到期调度（Issue #36）：worker + 到期处理。

contract-5 只提供 reminders CRUD，没有到期调度：到点不会生成通知、不会改
``reminder.status``。本模块补齐：

- ``compute_next_trigger_at``：按 ``none|daily|weekly|monthly`` 计算下一次触发
- ``process_due_reminders``：扫描到期提醒 → 写 ``notifications``（kind=reminder_due，
  payload 带 reminder_id 与站内 link）→ 更新状态 / 推进下次触发
- ``start_reminder_worker``：进程内守护线程定时扫描（``REMINDER_WORKER_ENABLED``
  可关、``REMINDER_WORKER_INTERVAL_SECONDS`` 可调，默认 30s）
"""
from __future__ import annotations

import calendar
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.job_runner import run_db_worker_safe
from app.crud import notification as notif_crud
from app.models import Reminder

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 30
MIN_INTERVAL_SECONDS = 5


def _as_utc(dt) -> datetime:
    """naive 时间按 UTC 处理，aware 时间统一转 UTC。"""
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _add_month(base: datetime) -> datetime:
    """月份 +1，日按目标月天数钳制（1/31 → 2/28 等）。"""
    year, month = base.year, base.month
    month += 1
    if month > 12:
        year += 1
        month = 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return base.replace(year=year, month=month, day=day)


def compute_next_trigger_at(trigger_at, repeat_rule: Optional[str], now) -> Optional[datetime]:
    """按 repeat_rule 计算下一次触发时间。

    ``none`` 或未知规则返回 ``None``（不再重复）；重复规则若推进后仍已到期
    （进程停机积压多轮），继续推进到未来，但只补发一条通知。
    """
    rule = (repeat_rule or "none").strip().lower()
    base = _as_utc(trigger_at)
    if rule == "daily":
        nxt = base + timedelta(days=1)
    elif rule == "weekly":
        nxt = base + timedelta(days=7)
    elif rule == "monthly":
        nxt = _add_month(base)
    else:
        return None

    now_utc = _as_utc(now)
    while nxt <= now_utc:
        if rule == "daily":
            nxt = nxt + timedelta(days=1)
        elif rule == "weekly":
            nxt = nxt + timedelta(days=7)
        else:  # monthly
            nxt = _add_month(nxt)
    return nxt


def process_due_reminders(db: Session, now=None) -> int:
    """扫描到期提醒：写通知、更新状态 / 推进下一次触发。返回处理条数。"""
    now_utc = _as_utc(now)
    due = (
        db.query(Reminder)
        .filter(
            Reminder.enabled.is_(True),
            Reminder.status == "active",
            Reminder.trigger_at <= now_utc,
        )
        .all()
    )
    processed = 0
    for reminder in due:
        notif_crud.create_notification(
            db,
            user_id=reminder.user_id,
            kind="reminder_due",
            title=reminder.title,
            body=reminder.body,
            payload={"reminder_id": reminder.id, "link": "/reminders"},
        )
        nxt = compute_next_trigger_at(reminder.trigger_at, reminder.repeat_rule, now_utc)
        if nxt is not None:
            reminder.trigger_at = nxt
            reminder.status = "active"
        else:
            reminder.status = "triggered"
        processed += 1
    if processed:
        db.commit()
        logger.info("提醒到期处理 %s 条", processed)
    return processed


def _worker_interval() -> float:
    try:
        return max(
            MIN_INTERVAL_SECONDS,
            float(os.getenv("REMINDER_WORKER_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS))),
        )
    except ValueError:
        return float(DEFAULT_INTERVAL_SECONDS)


def _worker_loop() -> None:
    while True:
        try:
            run_db_worker_safe(lambda db: process_due_reminders(db))
        except Exception:  # noqa: BLE001 — 单轮失败不终止线程
            logger.exception("提醒 worker 单轮扫描失败")
        time.sleep(_worker_interval())


def start_reminder_worker() -> Optional[threading.Thread]:
    """启动后台到期扫描线程（幂等）。``REMINDER_WORKER_ENABLED=false`` 时不启动。"""
    enabled = os.getenv("REMINDER_WORKER_ENABLED", "true").strip().lower()
    if enabled in ("false", "0", "no"):
        logger.info("提醒到期 worker 已禁用（REMINDER_WORKER_ENABLED=false）")
        return None
    thread = threading.Thread(target=_worker_loop, name="reminder-worker", daemon=True)
    thread.start()
    logger.info("提醒到期 worker 已启动，扫描间隔 %ss", _worker_interval())
    return thread
