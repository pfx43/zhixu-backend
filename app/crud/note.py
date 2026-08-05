from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Literal, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import UserNote


@dataclass(frozen=True)
class NoteUpdateResult:
    """一次笔记乐观更新在当前用户视角下的结果。"""

    note: Optional[UserNote]
    current_revision: Optional[int] = None


@dataclass(frozen=True)
class NoteDeleteResult:
    """软删除操作结果。"""

    success: bool
    current_revision: Optional[int] = None
    note: Optional[UserNote] = None


@dataclass(frozen=True)
class NoteRestoreResult:
    """恢复操作结果。"""

    success: bool
    current_revision: Optional[int] = None
    note: Optional[UserNote] = None


# ── 7 天保留期 ─────────────────────────────────────────────
_TRASH_RETENTION_DAYS = 7


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
    include_deleted: bool = False,
) -> List[UserNote]:
    query = db.query(UserNote).filter(UserNote.user_id == user_id)
    if not include_deleted:
        query = query.filter(UserNote.deleted_at.is_(None))
    if note_type:
        query = query.filter(UserNote.note_type == note_type)
    return query.order_by(UserNote.created_at.desc()).limit(limit).all()


def get_latest_note(
    db: Session, user_id: int, note_type: Optional[str] = None
) -> Optional[UserNote]:
    query = db.query(UserNote).filter(
        UserNote.user_id == user_id,
        UserNote.deleted_at.is_(None),
    )
    if note_type:
        query = query.filter(UserNote.note_type == note_type)
    return query.order_by(UserNote.created_at.desc()).first()


def get_note_by_id(
    db: Session,
    user_id: int,
    note_id: str,
    *,
    include_deleted: bool = False,
) -> Optional[UserNote]:
    query = db.query(UserNote).filter(
        UserNote.id == note_id,
        UserNote.user_id == user_id,
    )
    if not include_deleted:
        query = query.filter(UserNote.deleted_at.is_(None))
    return query.first()


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
    已软删除的笔记不能在恢复前更新。
    """
    values = {
        key: value
        for key, value in fields.items()
        if key in {"title", "content_md", "collection_id", "note_type"}
        and value is not None
    }
    if not values:
        return NoteUpdateResult(note=get_note_by_id(db, user_id, note_id))
    values["revision"] = UserNote.revision + 1
    values["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)

    result = db.execute(
        update(UserNote)
        .where(
            UserNote.id == note_id,
            UserNote.user_id == user_id,
            UserNote.revision == expected_revision,
            UserNote.deleted_at.is_(None),
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


def delete_note(
    db: Session,
    user_id: int,
    note_id: str,
    *,
    expected_revision: int | None = None,
) -> NoteDeleteResult:
    """软删除笔记（基于乐观锁 revision）。

    如果传入 expected_revision，仅当当前 revision 匹配时才执行软删除；
    否则直接软删除（向后兼容不带 revision 的旧客户端调用）。
    已软删除的笔记幂等返回 success=True。
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 先获取当前状态
    note = (
        db.query(UserNote)
        .filter(UserNote.id == note_id, UserNote.user_id == user_id)
        .first()
    )
    if not note:
        return NoteDeleteResult(success=False)

    # 已软删除 → 幂等
    if note.deleted_at is not None:
        return NoteDeleteResult(success=True, note=note, current_revision=note.revision)

    # 乐观锁检查
    if expected_revision is not None and note.revision != expected_revision:
        return NoteDeleteResult(
            success=False, current_revision=note.revision, note=note
        )

    new_revision = note.revision + 1
    result = db.execute(
        update(UserNote)
        .where(
            UserNote.id == note_id,
            UserNote.user_id == user_id,
            UserNote.revision == note.revision,
            UserNote.deleted_at.is_(None),
        )
        .values(
            deleted_at=now,
            deleted_by_revision=note.revision,
            revision=new_revision,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 1:
        db.flush()
        refreshed = get_note_by_id(db, user_id, note_id, include_deleted=True)
        return NoteDeleteResult(
            success=True,
            note=refreshed,
            current_revision=new_revision,
        )
    # 被并发操作抢先
    current = db.scalar(
        select(UserNote.revision).where(
            UserNote.id == note_id,
            UserNote.user_id == user_id,
        )
    )
    return NoteDeleteResult(success=False, current_revision=current)


def restore_note(
    db: Session,
    user_id: int,
    note_id: str,
    *,
    expected_revision: int,
) -> NoteRestoreResult:
    """恢复笔记（原子条件写入）。

    仅当 deleted_at IS NOT NULL 且 revision == expected_revision 时恢复。
    已恢复的笔记幂等返回 success=True。
    """
    note = (
        db.query(UserNote)
        .filter(UserNote.id == note_id, UserNote.user_id == user_id)
        .first()
    )
    if not note:
        return NoteRestoreResult(success=False)

    # 未删除 → 幂等恢复
    if note.deleted_at is None:
        return NoteRestoreResult(success=True, note=note, current_revision=note.revision)

    # 乐观锁检查
    if note.revision != expected_revision:
        return NoteRestoreResult(
            success=False, current_revision=note.revision, note=note
        )

    new_revision = note.revision + 1
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = db.execute(
        update(UserNote)
        .where(
            UserNote.id == note_id,
            UserNote.user_id == user_id,
            UserNote.revision == expected_revision,
            UserNote.deleted_at.isnot(None),
        )
        .values(
            deleted_at=None,
            deleted_by_revision=None,
            revision=new_revision,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 1:
        db.flush()
        refreshed = get_note_by_id(db, user_id, note_id)
        return NoteRestoreResult(
            success=True,
            note=refreshed,
            current_revision=new_revision,
        )
    # 被并发操作抢先
    current = db.scalar(
        select(UserNote.revision).where(
            UserNote.id == note_id,
            UserNote.user_id == user_id,
        )
    )
    return NoteRestoreResult(success=False, current_revision=current)


def list_trash(
    db: Session,
    user_id: int,
    *,
    page: int = 1,
    limit: int = 50,
) -> List[UserNote]:
    """列出回收站中当前用户的已删除笔记（按删除时间倒序）。"""
    offset = (page - 1) * limit
    return (
        db.query(UserNote)
        .filter(
            UserNote.user_id == user_id,
            UserNote.deleted_at.isnot(None),
        )
        .order_by(UserNote.deleted_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def purge_expired_notes(db: Session) -> int:
    """物理删除超过 7 天保留期的已删除笔记。返回删除条数。"""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=_TRASH_RETENTION_DAYS
    )
    result = db.execute(
        delete(UserNote).where(
            UserNote.deleted_at.isnot(None),
            UserNote.deleted_at < cutoff,
        )
    )
    db.flush()
    return result.rowcount