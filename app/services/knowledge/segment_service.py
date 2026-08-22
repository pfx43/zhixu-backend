"""
文档分段服务 — 学习区文档按标题或定长窗口切分 document_segments
"""
import logging
import re
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud import kb as kb_crud
from app.crud import segment as segment_crud
from app.crud import toc as toc_crud
from app.models import Document
from app.schemas.segment import SegmentListOut, SegmentOut
from app.services.knowledge import doc_structure
from app.services.knowledge.file_parser import parse_file_detailed
from app.services.knowledge.storage_service import storage_service

logger = logging.getLogger(__name__)

WINDOW_SIZE = 1500
OVERLAP = 200
HEADING_PATTERN = re.compile(r"^#{1,2}\s+.+", re.MULTILINE)


def _resolve_parsed_path(document: Document) -> Optional[str]:
    if document.parsed_cache_key:
        return document.parsed_cache_key
    global_doc = document.global_document
    if global_doc and global_doc.parsed_text_path:
        return global_doc.parsed_text_path
    return None


def _load_document_text(document: Document) -> tuple[Optional[str], Optional[str]]:
    """返回 (text, error_message)。"""
    parsed_path = _resolve_parsed_path(document)
    if parsed_path:
        text = storage_service.read_text_at_path(parsed_path)
        if text:
            return text, None

    global_doc = document.global_document
    if global_doc and global_doc.storage_path:
        outcome = parse_file_detailed(
            global_doc.storage_path,
            original_filename=global_doc.original_filename,
        )
        return outcome.text, outcome.error

    return None, "文档无存储路径或解析缓存"


def _has_markdown_headings(text: str) -> bool:
    return HEADING_PATTERN.search(text) is not None


def _split_by_window(text: str) -> List[dict]:
    if not text:
        return []

    segments: List[dict] = []
    start = 0
    step = WINDOW_SIZE - OVERLAP
    while start < len(text):
        end = min(start + WINDOW_SIZE, len(text))
        segments.append(
            {
                "title": None,
                "content": text[start:end],
                "char_start": start,
                "char_end": end,
            }
        )
        if end >= len(text):
            break
        start += step
    return segments


def _split_by_headings(text: str) -> List[dict]:
    matches = list(HEADING_PATTERN.finditer(text))
    if not matches:
        return _split_by_window(text)

    segments: List[dict] = []

    if matches[0].start() > 0:
        pre_start = 0
        pre_end = matches[0].start()
        pre_content = text[pre_start:pre_end]
        if pre_content.strip():
            segments.append(
                {
                    "title": None,
                    "content": pre_content,
                    "char_start": pre_start,
                    "char_end": pre_end,
                }
            )

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end]
        title = re.sub(r"^#{1,2}\s+", "", match.group().strip())[:255]
        segments.append(
            {
                "title": title or None,
                "content": chunk,
                "char_start": start,
                "char_end": end,
            }
        )

    return segments


def split_text(text: str) -> List[dict]:
    """将全文切分为段，返回含 title/content/char_start/char_end 的字典列表。"""
    if _has_markdown_headings(text):
        raw = _split_by_headings(text)
    else:
        raw = _split_by_window(text)

    for idx, item in enumerate(raw):
        item["order_index"] = idx
    return raw


def _resolve_storage_path(document: Document) -> Optional[str]:
    global_doc = document.global_document
    if global_doc and global_doc.storage_path:
        return global_doc.storage_path
    return None


def _apply_structure(
    db: Session, document: Document, text: str, segments: List[dict]
) -> None:
    """给段写入 page_start/page_end，并写入章节目录（PDF 书签优先）。

    页码只来自文本页标记 / PDF 书签；无任何来源时页码留空、目录为空。
    """
    page_ranges = doc_structure.extract_page_ranges(text)
    for seg in segments:
        seg["page_start"], seg["page_end"] = doc_structure.map_segment_pages(
            seg["char_start"], seg["char_end"], page_ranges
        )

    toc_entries = doc_structure.extract_toc_from_pdf_bookmarks(
        _resolve_storage_path(document) or ""
    )
    if not toc_entries:
        toc_entries = doc_structure.extract_toc_from_headings(text, page_ranges)
    toc_crud.replace_toc_for_document(db, document.id, toc_entries)


def recompute_document_structure(document_id: str, db: Session) -> int:
    """重算文档的段页码与目录（供旧书补页 / 幂等重跑）。

    不改动已有段的内容与切分结果，只回填 page_start/page_end 和 toc。
    返回被更新的段数；文档不存在或非 study 返回 0。
    """
    doc = segment_crud.get_document_by_id(db, document_id)
    if not doc:
        logger.warning("recompute_document_structure: document not found %s", document_id)
        return 0
    if doc.zone != "study":
        return 0

    text, parse_error = _load_document_text(doc)
    if text is None:
        logger.warning(
            "recompute_document_structure: 无法读取文本 %s: %s",
            document_id,
            parse_error,
        )
        return 0

    page_ranges = doc_structure.extract_page_ranges(text)
    segments = segment_crud.list_segments_for_document(db, document_id)
    updated = 0
    for seg in segments:
        page_start, page_end = doc_structure.map_segment_pages(
            seg.char_start, seg.char_end, page_ranges
        )
        if seg.page_start != page_start or seg.page_end != page_end:
            seg.page_start = page_start
            seg.page_end = page_end
            updated += 1

    toc_entries = doc_structure.extract_toc_from_pdf_bookmarks(
        _resolve_storage_path(doc) or ""
    )
    if not toc_entries:
        toc_entries = doc_structure.extract_toc_from_headings(text, page_ranges)
    toc_crud.replace_toc_for_document(db, document_id, toc_entries)
    db.flush()
    return updated


def segment_document(document_id: str, db: Session) -> int:
    """
    对指定文档执行分段。仅 zone=study 会写入 document_segments。
    重复调用会先删旧 segments 再写入新段。
    返回写入的段数；life 区或文档不存在时返回 0。
    """
    doc = segment_crud.get_document_by_id(db, document_id)
    if not doc:
        logger.warning("segment_document: document not found %s", document_id)
        return 0

    if doc.zone != "study":
        return 0

    doc.segment_status = "processing"
    db.flush()

    try:
        text, parse_error = _load_document_text(doc)
        if text is None:
            raise ValueError(parse_error or "无法获取文档文本")

        segment_dicts = split_text(text)
        _apply_structure(db, doc, text, segment_dicts)
        segment_crud.delete_segments_for_document(db, document_id)
        segment_crud.bulk_create_segments(db, document_id, segment_dicts)

        doc.segment_status = "completed"
        db.flush()
        logger.info(
            "segment_document completed: document_id=%s, segments=%d",
            document_id,
            len(segment_dicts),
        )

        from app.core.config import is_local_rag, is_keyword_rag
        if is_local_rag():
            if is_keyword_rag():
                # 关键词检索：不写 Chroma 向量，分段入库即完成索引
                doc.indexing_status = "completed"
                db.flush()
            else:
                from app.services.knowledge.index_service import index_document_segments

                try:
                    index_document_segments(db, doc)
                except Exception:
                    logger.exception(
                        "Chroma index failed: document_id=%s", document_id
                    )
                    doc.indexing_status = "failed"
                    db.flush()

        return len(segment_dicts)
    except Exception:
        logger.exception("segment_document failed: document_id=%s", document_id)
        doc.segment_status = "failed"
        db.flush()
        return 0


def list_document_segments(
    db: Session, user_id: int, doc_id: str
) -> SegmentListOut:
    doc = kb_crud.get_document_by_id_or_dify(db, user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    rows = segment_crud.list_segments_for_document(db, doc.id)
    return SegmentListOut(
        document_id=doc.id,
        segment_status=doc.segment_status,
        segments=[SegmentOut.model_validate(s) for s in rows],
        total=len(rows),
    )
