from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import QuestionTag


def list_tags_for_user(
    db: Session,
    user_id: int,
    document_id: Optional[str] = None,
) -> List[QuestionTag]:
    query = db.query(QuestionTag).filter(QuestionTag.user_id == user_id)
    if document_id:
        query = query.filter(
            (QuestionTag.document_id == document_id) | (QuestionTag.document_id.is_(None))
        )
    return query.order_by(QuestionTag.name.asc()).all()


def get_tag_by_name(db: Session, user_id: int, name: str) -> Optional[QuestionTag]:
    return (
        db.query(QuestionTag)
        .filter(QuestionTag.user_id == user_id, QuestionTag.name == name)
        .first()
    )


def get_or_create_tag(
    db: Session,
    *,
    user_id: int,
    name: str,
    description: Optional[str] = None,
    document_id: Optional[str] = None,
) -> QuestionTag:
    name = name.strip()
    if not name:
        raise ValueError("tag name empty")
    existing = get_tag_by_name(db, user_id, name)
    if existing:
        if description and not existing.description:
            existing.description = description
            db.flush()
        return existing
    row = QuestionTag(
        user_id=user_id,
        name=name,
        description=description,
        document_id=document_id,
    )
    db.add(row)
    db.flush()
    return row


def ensure_tags(
    db: Session,
    *,
    user_id: int,
    tag_names: List[str],
    document_id: Optional[str] = None,
) -> List[QuestionTag]:
    result: List[QuestionTag] = []
    for raw in tag_names:
        name = (raw or "").strip()
        if not name:
            continue
        result.append(
            get_or_create_tag(db, user_id=user_id, name=name, document_id=document_id)
        )
    return result
