"""通知 CRUD（Issue #5.X）。"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Notification


def create_notification(
    db: Session,
    *,
    user_id: int,
    kind: str,
    title: str,
    body: Optional[str] = None,
    payload: Optional[dict] = None,
) -> Notification:
    row = Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        payload_json=payload or None,
    )
    db.add(row)
    db.flush()
    return row


def list_notifications(
    db: Session, user_id: int, *, limit: int = 50
) -> List[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )


def count_unread(db: Session, user_id: int) -> int:
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        .count()
    )


def mark_notification_read(
    db: Session, user_id: int, notification_id: str
) -> bool:
    n = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
        .first()
    )
    if not n:
        return False
    if n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
    db.flush()
    return True