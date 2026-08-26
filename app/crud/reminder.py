"""提醒 CRUD（Issue #5.X）。"""
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Reminder


def create_reminder(
    db: Session,
    *,
    user_id: int,
    title: str,
    trigger_at,
    body: Optional[str] = None,
    repeat_rule: Optional[str] = None,
    enabled: bool = True,
) -> Reminder:
    row = Reminder(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title=title,
        body=body,
        trigger_at=trigger_at,
        repeat_rule=repeat_rule,
        enabled=enabled,
    )
    db.add(row)
    db.flush()
    return row


def list_reminders(
    db: Session, user_id: int, *, limit: int = 200
) -> List[Reminder]:
    return (
        db.query(Reminder)
        .filter(Reminder.user_id == user_id)
        .order_by(Reminder.trigger_at.asc())
        .limit(limit)
        .all()
    )


def get_reminder(
    db: Session, user_id: int, reminder_id: str
) -> Optional[Reminder]:
    return (
        db.query(Reminder)
        .filter(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
        )
        .first()
    )


def update_reminder(
    db: Session,
    user_id: int,
    reminder_id: str,
    *,
    title: Optional[str] = None,
    body: Optional[str] = None,
    trigger_at=None,
    repeat_rule: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> Optional[Reminder]:
    r = get_reminder(db, user_id, reminder_id)
    if not r:
        return None
    if title is not None:
        r.title = title
    if body is not None:
        r.body = body
    if trigger_at is not None:
        r.trigger_at = trigger_at
    if repeat_rule is not None:
        r.repeat_rule = repeat_rule
    if enabled is not None:
        r.enabled = enabled
    db.flush()
    return r


def delete_reminder(db: Session, user_id: int, reminder_id: str) -> bool:
    r = get_reminder(db, user_id, reminder_id)
    if not r:
        return False
    db.delete(r)
    db.flush()
    return True