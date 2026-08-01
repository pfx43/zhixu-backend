from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import UserNote


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
    db: Session, user_id: int, note_id: str, **fields
) -> Optional[UserNote]:
    row = get_note_by_id(db, user_id, note_id)
    if not row:
        return None
    for key, value in fields.items():
        if value is not None and hasattr(row, key):
            setattr(row, key, value)
    db.flush()
    return row


def delete_note(db: Session, user_id: int, note_id: str) -> bool:
    row = get_note_by_id(db, user_id, note_id)
    if not row:
        return False
    db.delete(row)
    db.flush()
    return True