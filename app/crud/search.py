from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Document, DocumentSegment, UserNote


def _lexical_contains(column, query: str):
    """Build a case-insensitive literal substring predicate for SQL backends."""
    escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike("%" + escaped_query + "%", escape="\\")


def find_notes(
    db: Session,
    *,
    user_id: int,
    query: str,
    collection_id: Optional[str] = None,
) -> List[UserNote]:
    filters = [
        UserNote.user_id == user_id,
        or_(
            _lexical_contains(UserNote.title, query),
            _lexical_contains(UserNote.content_md, query),
        ),
    ]
    if collection_id:
        filters.append(UserNote.collection_id == collection_id)
    return (
        db.query(UserNote)
        .filter(*filters)
        .order_by(UserNote.updated_at.desc(), UserNote.id.asc())
        .all()
    )


def find_documents_by_title(
    db: Session,
    *,
    user_id: int,
    query: str,
    collection_id: Optional[str] = None,
) -> List[Document]:
    filters = [
        Document.user_id == user_id,
        _lexical_contains(Document.display_name, query),
    ]
    if collection_id:
        filters.append(Document.collection_id == collection_id)
    return (
        db.query(Document)
        .filter(*filters)
        .order_by(Document.updated_at.desc(), Document.id.asc())
        .all()
    )


def find_completed_document_segments(
    db: Session,
    *,
    user_id: int,
    query: str,
    collection_id: Optional[str] = None,
) -> List[Tuple[Document, DocumentSegment]]:
    """Only return segments whose document has finished the study-zone pipeline."""
    filters = [
        Document.user_id == user_id,
        Document.zone == "study",
        Document.segment_status == "completed",
        Document.indexing_status == "completed",
        _lexical_contains(DocumentSegment.content, query),
    ]
    if collection_id:
        filters.append(Document.collection_id == collection_id)
    return (
        db.query(Document, DocumentSegment)
        .join(DocumentSegment, DocumentSegment.document_id == Document.id)
        .filter(*filters)
        .order_by(
            Document.updated_at.desc(),
            DocumentSegment.order_index.asc(),
            DocumentSegment.id.asc(),
        )
        .all()
    )


def count_pending_study_documents(
    db: Session,
    *,
    user_id: int,
    collection_id: Optional[str] = None,
) -> int:
    """Count study documents whose body search is still incomplete in this scope."""
    filters = [
        Document.user_id == user_id,
        Document.zone == "study",
        or_(
            Document.segment_status.is_(None),
            Document.segment_status != "completed",
            Document.indexing_status.is_(None),
            Document.indexing_status != "completed",
        ),
    ]
    if collection_id:
        filters.append(Document.collection_id == collection_id)
    return db.query(Document).filter(*filters).count()
