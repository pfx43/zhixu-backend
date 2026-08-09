"""
关键词检索 — 纯词法匹配 document_segments，不依赖 Chroma 向量。

RAG_BACKEND=keyword 时，聊天/辅导的上下文检索改为直接对数据库中的
document_segments 做子串（ILIKE）匹配。命中结构（score/content/
document_id/segment_id/collection_id/title/char_start/char_end 等）
与本地向量检索保持一致，citation 链路无需改动即可复用。
"""
import logging
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Document, DocumentSegment

logger = logging.getLogger(__name__)

_TITLE_BONUS = 0.3


def _lexical_contains(column, query: str):
    """大小写不敏感的子串谓词（转义 % / _ / \\，兼容 SQLite/PostgreSQL）。"""
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike("%" + escaped + "%", escape="\\")


def _tokenize(query: str) -> List[str]:
    terms = [t.strip() for t in query.split() if t.strip()]
    return terms or ([query.strip()] if query.strip() else [])


def _term_score(content: str, segment_title: str, display_name: str, term: str) -> float:
    low = term.casefold()
    score = float((content or "").casefold().count(low))
    if segment_title and low in (segment_title or "").casefold():
        score += _TITLE_BONUS
    if display_name and low in (display_name or "").casefold():
        score += _TITLE_BONUS
    return score


def search(
    db: Session,
    query: str,
    *,
    user_id: int,
    collection_id: Optional[str] = None,
    top_k: int = 5,
) -> List[dict]:
    """关键词检索用户知识库分段。

    返回与 ``ChromaStore.search`` 一致的命中结构，仅做词法匹配，
    不调用 embedding / 向量存储。
    """
    if db is None or not query or not query.strip():
        return []

    terms = _tokenize(query.strip())
    if not terms:
        return []

    # 候选：content 命中任一 term，或文档标题命中整句/任一 term
    term_conditions = [_lexical_contains(DocumentSegment.content, t) for t in terms]
    filters = [
        Document.user_id == int(user_id),
        Document.zone == "study",
        Document.segment_status == "completed",
        Document.indexing_status == "completed",
        or_(*term_conditions),
    ]
    if collection_id:
        filters.append(Document.collection_id == collection_id)

    rows = (
        db.query(Document, DocumentSegment)
        .join(DocumentSegment, DocumentSegment.document_id == Document.id)
        .filter(*filters)
        .all()
    )

    scored: List[dict] = []
    for doc, seg in rows:
        score = sum(
            _term_score(seg.content, seg.title, doc.display_name, t) for t in terms
        )
        if score <= 0:
            continue
        scored.append(
            {
                "score": score,
                "content": seg.content,
                "document_id": doc.id,
                "segment_id": seg.id,
                "collection_id": doc.collection_id,
                "title": seg.title,
                "display_name": doc.display_name,
                "char_start": seg.char_start,
                "char_end": seg.char_end,
            }
        )

    scored.sort(key=lambda h: (-h["score"], h["document_id"], h["segment_id"]))
    hits = scored[:top_k]

    max_score = hits[0]["score"] if hits else 0.0
    for hit in hits:
        hit["score"] = (
            min(1.0, hit["score"] / max_score) if max_score > 0 else 0.0
        )

    return hits
