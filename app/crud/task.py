"""今日任务 CRUD（Issue #19）。"""
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import DailyTask


def list_tasks(
    db: Session, user_id: int, task_date: date
) -> List[DailyTask]:
    """某用户某天的全部任务（pending 在前，按创建时间）。"""
    return (
        db.query(DailyTask)
        .filter(DailyTask.user_id == user_id, DailyTask.task_date == task_date)
        .order_by(DailyTask.status.asc(), DailyTask.created_at.asc())
        .all()
    )


def list_pending_tasks(
    db: Session, user_id: int, task_date: Optional[date] = None
) -> List[DailyTask]:
    """某用户未完成任务；不传日期则查全部历史未完成（正常情况下没有）。"""
    query = db.query(DailyTask).filter(
        DailyTask.user_id == user_id, DailyTask.status == "pending"
    )
    if task_date is not None:
        query = query.filter(DailyTask.task_date == task_date)
    return query.order_by(DailyTask.created_at.asc()).all()


def list_pending_by_type(
    db: Session, user_id: int, task_type: str, task_date: date
) -> List[DailyTask]:
    return (
        db.query(DailyTask)
        .filter(
            DailyTask.user_id == user_id,
            DailyTask.task_date == task_date,
            DailyTask.task_type == task_type,
            DailyTask.status == "pending",
        )
        .order_by(DailyTask.created_at.asc())
        .all()
    )


def create_task(
    db: Session,
    *,
    user_id: int,
    goal_id: Optional[int],
    task_date: date,
    title: str,
    reason: Optional[str],
    task_type: str,
    payload: Optional[dict],
    completion_rule: Optional[dict],
) -> DailyTask:
    task = DailyTask(
        user_id=user_id,
        goal_id=goal_id,
        task_date=task_date,
        title=title,
        reason=reason,
        task_type=task_type,
        payload=payload or {},
        completion_rule=completion_rule or {},
        status="pending",
    )
    db.add(task)
    db.flush()
    return task


def mark_completed(db: Session, task: DailyTask) -> None:
    task.status = "completed"
