"""
聊天 citation — 将 RAG 检索命中映射到 document_segments
"""
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud import kb as kb_crud
from app.crud import segment as segment_crud
from app.models import DocumentSegment, KbCollection
from app.schemas.quiz import CitationOut


def resolve_chat_collection(
    db: Session,
    user_id: int,
    collection_id: Optional[str],
    user_dataset_id: Optional[str],
) -> Tuple[KbCollection, Optional[str]]:
    """解析聊天所用分区，返回 (collection, dataset_id)。"""
    if not kb_crud.list_collections(db, user_id):
        kb_crud.seed_default_collections(db, user_id, user_dataset_id)
        db.commit()

    if collection_id:
        coll = kb_crud.get_collection(db, user_id, collection_id)
        if not coll:
            raise HTTPException(status_code=404, detail="知识库分区不存在")
    else:
        coll = kb_crud.get_default_study_collection(db, user_id)
        if not coll:
            raise HTTPException(status_code=500, detail="默认学习区未初始化")

    dataset_id = coll.dataset_id or user_dataset_id
    return coll, dataset_id


def filter_hits_by_collection(
    db: Session,
    user_id: int,
    collection_id: Optional[str],
    hits: List[dict],
) -> List[dict]:
    """按分区过滤检索命中。"""
    if not collection_id:
        return hits

    filtered: List[dict] = []
    for hit in hits:
        if hit.get("collection_id"):
            if hit["collection_id"] == collection_id:
                filtered.append(hit)
            continue
        dify_doc_id = hit.get("dify_document_id")
        if not dify_doc_id:
            continue
        doc = kb_crud.get_document_by_id_or_dify(db, user_id, dify_doc_id)
        if doc and doc.collection_id == collection_id:
            filtered.append(hit)
    return filtered


def _overlap_score(snippet: str, segment_content: str) -> float:
    snippet = snippet.strip()
    if not snippet or not segment_content:
        return 0.0
    if snippet in segment_content:
        return 1.0
    probe = snippet[: min(80, len(snippet))]
    if probe and probe in segment_content:
        return len(probe) / len(snippet)
    return 0.0


def _match_segment(
    segments: List[DocumentSegment], snippet: str
) -> Optional[DocumentSegment]:
    if not segments or not snippet or not snippet.strip():
        return None

    snippet_clean = snippet.strip()
    for seg in segments:
        if snippet_clean in seg.content:
            return seg

    best: Optional[DocumentSegment] = None
    best_score = 0.0
    for seg in segments:
        score = _overlap_score(snippet_clean, seg.content)
        if score > best_score:
            best_score = score
            best = seg
    return best if best_score >= 0.3 else None


def build_citations_from_hits(
    db: Session,
    user_id: int,
    collection_id: Optional[str],
    hits: List[dict],
) -> List[CitationOut]:
    """从 RAG 命中构建 citations[]。"""
    citations: List[CitationOut] = []
    seen: set = set()

    for hit in hits:
        content = (hit.get("content") or "").strip()

        # 本地 RAG：metadata 已含 segment 信息，直接构建
        if hit.get("segment_id") and hit.get("document_id"):
            doc_id = hit["document_id"]
            if collection_id and hit.get("collection_id") != collection_id:
                continue
            dedupe_key = (doc_id, hit["segment_id"])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            title = hit.get("title") or hit.get("display_name")
            citations.append(
                CitationOut(
                    doc_id=doc_id,
                    segment_id=hit["segment_id"],
                    title=title,
                    char_start=hit.get("char_start"),
                    char_end=hit.get("char_end"),
                    snippet=content[:500] if content else None,
                )
            )
            continue

        dify_doc_id = hit.get("dify_document_id")
        if not content and not dify_doc_id:
            continue

        doc = None
        if dify_doc_id:
            doc = kb_crud.get_document_by_id_or_dify(db, user_id, dify_doc_id)
        if not doc:
            continue
        if collection_id and doc.collection_id != collection_id:
            continue

        segments = segment_crud.list_segments_for_document(db, doc.id)
        segment = _match_segment(segments, content) if segments else None

        dedupe_key = (doc.id, segment.id if segment else None)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        snippet = content[:500] if content else None
        citations.append(
            CitationOut(
                doc_id=doc.id,
                segment_id=segment.id if segment else None,
                title=(segment.title if segment else None) or doc.display_name,
                char_start=segment.char_start if segment else None,
                char_end=segment.char_end if segment else None,
                snippet=snippet,
            )
        )

    return citations
