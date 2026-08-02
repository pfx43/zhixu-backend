"""Independent lexical search for current-user notes and knowledge documents."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.crud import search as search_crud
from app.schemas.search import SearchItemOut, SearchResponseOut, SearchScope

_TITLE_MATCH_PRIORITY = 0
_CONTENT_MATCH_PRIORITY = 1
_SNIPPET_LENGTH = 180


def _contains(value: Optional[str], query: str) -> bool:
    return query.casefold() in (value or "").casefold()


def _snippet(value: Optional[str], query: str) -> str:
    normalized = " ".join((value or "").split())
    if not normalized:
        return ""

    match_at = normalized.casefold().find(query.casefold())
    if match_at < 0:
        return normalized[:_SNIPPET_LENGTH]

    start = max(0, match_at - 48)
    end = min(len(normalized), match_at + len(query) + 96)
    prefix = "…" if start else ""
    suffix = "…" if end < len(normalized) else ""
    return f"{prefix}{normalized[start:end]}{suffix}"


def _sort_key(item: SearchItemOut):
    updated_at_timestamp = item.updated_at.timestamp() if item.updated_at else 0
    return (
        _TITLE_MATCH_PRIORITY if item.match_source == "title" else _CONTENT_MATCH_PRIORITY,
        -updated_at_timestamp,
        item.type,
        item.id,
    )


def search_knowledge(
    db: Session,
    *,
    user_id: int,
    query: str,
    scope: SearchScope,
    page: int,
    limit: int,
    collection_id: Optional[str] = None,
) -> SearchResponseOut:
    """Search only lexical fields; this endpoint never invokes embedding or LLM services."""
    items: List[SearchItemOut] = []

    if scope in ("all", "notes"):
        for note in search_crud.find_notes(
            db,
            user_id=user_id,
            query=query,
            collection_id=collection_id,
        ):
            title_matches = _contains(note.title, query)
            subtitle = _snippet(note.content_md, query)
            if not subtitle and title_matches:
                subtitle = "笔记标题命中"
            items.append(
                SearchItemOut(
                    id=note.id,
                    type="note",
                    title=note.title,
                    subtitle=subtitle,
                    updated_at=note.updated_at,
                    collection_id=note.collection_id,
                    match_source="title" if title_matches else "content",
                )
            )

    pending_document_count = 0
    if scope in ("all", "documents"):
        pending_document_count = search_crud.count_pending_study_documents(
            db,
            user_id=user_id,
            collection_id=collection_id,
        )

        title_documents = search_crud.find_documents_by_title(
            db,
            user_id=user_id,
            query=query,
            collection_id=collection_id,
        )
        document_ids_with_title_match = {document.id for document in title_documents}
        for document in title_documents:
            items.append(
                SearchItemOut(
                    id=document.id,
                    type="document",
                    title=document.display_name,
                    subtitle=f"资料标题命中：{document.display_name}",
                    updated_at=document.updated_at,
                    collection_id=document.collection_id,
                    match_source="title",
                    indexing_status=document.indexing_status,
                )
            )

        for document, segment in search_crud.find_completed_document_segments(
            db,
            user_id=user_id,
            query=query,
            collection_id=collection_id,
        ):
            if document.id in document_ids_with_title_match:
                continue
            document_ids_with_title_match.add(document.id)
            items.append(
                SearchItemOut(
                    id=document.id,
                    type="document",
                    title=document.display_name,
                    subtitle=_snippet(segment.content, query),
                    updated_at=document.updated_at,
                    collection_id=document.collection_id,
                    match_source="content",
                    indexing_status=document.indexing_status,
                )
            )

    items.sort(key=_sort_key)
    total = len(items)
    start = (page - 1) * limit
    return SearchResponseOut(
        query=query,
        items=items[start : start + limit],
        total=total,
        page=page,
        limit=limit,
        partial=pending_document_count > 0,
        pending_document_count=pending_document_count,
    )
