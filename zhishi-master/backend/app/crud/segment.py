from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Document, DocumentSegment


def get_document_by_id(db: Session, document_id: str) -> Optional[Document]:
    return db.query(Document).filter(Document.id == document_id).first()


def delete_segments_for_document(db: Session, document_id: str) -> int:
    """重复分段时先删旧记录，保证幂等重跑。"""
    deleted = (
        db.query(DocumentSegment)
        .filter(DocumentSegment.document_id == document_id)
        .delete(synchronize_session=False)
    )
    db.flush()
    return deleted


def bulk_create_segments(
    db: Session,
    document_id: str,
    segments: List[dict],
) -> List[DocumentSegment]:
    rows: List[DocumentSegment] = []
    for item in segments:
        row = DocumentSegment(
            document_id=document_id,
            order_index=item["order_index"],
            title=item.get("title"),
            content=item["content"],
            char_start=item["char_start"],
            char_end=item["char_end"],
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def list_segments_for_document(
    db: Session, document_id: str
) -> List[DocumentSegment]:
    return (
        db.query(DocumentSegment)
        .filter(DocumentSegment.document_id == document_id)
        .order_by(DocumentSegment.order_index.asc())
        .all()
    )
