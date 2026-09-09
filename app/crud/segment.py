from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from app.models import Document, DocumentSegment


def get_document_by_id(db: Session, document_id: str) -> Optional[Document]:
    return db.query(Document).filter(Document.id == document_id).first()


async def aget_document_by_id(
    db: AsyncSession, document_id: str
) -> Optional[Document]:
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.global_document))
        .where(Document.id == document_id)
    )
    return result.scalar_one_or_none()


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
            page_start=item.get("page_start"),
            page_end=item.get("page_end"),
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


async def adelete_segments_for_document(db: AsyncSession, document_id: str) -> None:
    await db.execute(
        delete(DocumentSegment).where(DocumentSegment.document_id == document_id)
    )
    await db.flush()


async def abulk_create_segments(
    db: AsyncSession,
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
            page_start=item.get("page_start"),
            page_end=item.get("page_end"),
        )
        db.add(row)
        rows.append(row)
    await db.flush()
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
