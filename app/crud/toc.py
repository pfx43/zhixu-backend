from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import DocumentToc


def replace_toc_for_document(
    db: Session, document_id: str, entries: List[dict]
) -> List[DocumentToc]:
    """删除旧目录并按 order_index 写入新目录（幂等）。"""
    db.query(DocumentToc).filter(DocumentToc.document_id == document_id).delete(
        synchronize_session=False
    )
    db.flush()

    rows: List[DocumentToc] = []
    for idx, entry in enumerate(entries):
        row = DocumentToc(
            document_id=document_id,
            order_index=idx,
            title=entry["title"],
            page_start=entry["page_start"],
            page_end=entry["page_end"],
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def list_toc_for_document(
    db: Session, document_id: str
) -> List[DocumentToc]:
    return (
        db.query(DocumentToc)
        .filter(DocumentToc.document_id == document_id)
        .order_by(DocumentToc.order_index.asc())
        .all()
    )


def get_toc_for_document(db: Session, document_id: str) -> Optional[DocumentToc]:
    return (
        db.query(DocumentToc)
        .filter(DocumentToc.document_id == document_id)
        .order_by(DocumentToc.order_index.asc())
        .first()
    )