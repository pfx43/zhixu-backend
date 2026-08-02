from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import UserNote


@dataclass(frozen=True)
class NoteUpdateResult:
    """一次笔记乐观更新在当前用户视角下的结果。"""

    note: Optional[UserNote]
    current_revision: Optional[int] = None


def create_note(
    db: Session,
    *,
    user_id: int,
    title: str,
    content_md: str,
    collection_id: Optional[str] = None,
    note_type: str = "manual",
) -> UserNote:
    row = UserNote(
        user_id=user_id,
        title=title,
        content_md=content_md,
        collection_id=collection_id,
        note_type=note_type,
    )
    db.add(row)
    db.flush()
    return row


def list_notes(
    db: Session,
    user_id: int,
    *,
    note_type: Optional[str] = None,
    limit: int = 50,
) -> List[UserNote]:
    query = db.query(UserNote).filter(UserNote.user_id == user_id)
    if note_type:
        query = query.filter(UserNote.note_type == note_type)
    return query.order_by(UserNote.created_at.desc()).limit(limit).all()


def get_latest_note(
    db: Session, user_id: int, note_type: Optional[str] = None
) -> Optional[UserNote]:
    query = db.query(UserNote).filter(UserNote.user_id == user_id)
    if note_type:
        query = query.filter(UserNote.note_type == note_type)
    return query.order_by(UserNote.created_at.desc()).first()


def get_note_by_id(
    db: Session, user_id: int, note_id: str
) -> Optional[UserNote]:
    return (
        db.query(UserNote)
        .filter(UserNote.id == note_id, UserNote.user_id == user_id)
        .first()
    )


def update_note(
    db: Session,
    user_id: int,
    note_id: str,
    *,
    expected_revision: int,
    **fields,
) -> NoteUpdateResult:
    """仅当客户端持久化的 revision 仍为当前值时更新笔记。

    ``updated_at`` 仍只是展示时间；整数 ``revision`` 是唯一并发令牌，因此数据库
    时间戳精度和时区表示不会令两次写入被误判为等价。
    """
    values = {
        key: value
        for key, value in fields.items()
        if key in {"title", "content_md", "collection_id", "note_type"}
        and value is not None
    }
    values["revision"] = UserNote.revision + 1
    values["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)

    result = db.execute(
        update(UserNote)
        .where(
            UserNote.id == note_id,
            UserNote.user_id == user_id,
            UserNote.revision == expected_revision,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 1:
        return NoteUpdateResult(note=get_note_by_id(db, user_id, note_id))

    current_revision = db.scalar(
        select(UserNote.revision).where(
            UserNote.id == note_id,
            UserNote.user_id == user_id,
        )
    )
    return NoteUpdateResult(note=None, current_revision=current_revision)


def delete_note(db: Session, user_id: int, note_id: str) -> bool:
    row = get_note_by_id(db, user_id, note_id)
    if not row:
        return False
    db.delete(row)
    db.flush()
    return True
