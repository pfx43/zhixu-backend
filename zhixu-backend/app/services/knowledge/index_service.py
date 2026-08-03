"""
文档分段索引 — 分段完成后写入 Chroma
"""
import logging

from sqlalchemy.orm import Session

from app.crud import segment as segment_crud
from app.models import Document
from app.services.knowledge.chroma_store import chroma_store

logger = logging.getLogger(__name__)


def index_document_segments(db: Session, document: Document) -> int:
    """将文档 segments 写入 Chroma，返回索引段数。"""
    segments = segment_crud.list_segments_for_document(db, document.id)
    if not segments:
        return 0

    count = chroma_store.upsert_segments(
        document_id=document.id,
        segments=segments,
        user_id=document.user_id,
        collection_id=document.collection_id,
        display_name=document.display_name,
    )
    document.indexing_status = "completed"
    db.flush()
    logger.info(
        "index_document_segments: document_id=%s indexed=%d",
        document.id,
        count,
    )
    return count


def delete_document_index(document_id: str) -> None:
    chroma_store.delete_by_document(document_id)
