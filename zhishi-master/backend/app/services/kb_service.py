"""
知识库业务编排 — 分区、上传、global_documents 去重
"""
import hashlib
import json
import logging
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.crud import kb as kb_crud
from app.core.config import (
    DIFY_MAX_UPLOAD_SIZE,
    DOCUMENT_PIPELINE_ASYNC,
    IMAGE_OCR_ASYNC,
    is_local_rag,
)
from app.core.database import SessionLocal
from app.core.job_runner import run_in_background
from app.models import Document, KbCollection
from app.schemas.kb import (
    CollectionCreate,
    CollectionListOut,
    CollectionOut,
    CollectionUpdate,
    DocumentListOut,
    DocumentOut,
    UploadResponse,
)
from app.services.dify_kb import DifyKB
from app.services.file_parser import (
    IMAGE_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    is_scanned_pdf,
    parse_file_detailed,
)
from app.services.ocr_progress import get_ocr_progress, set_ocr_progress
from app.services.ocr_service import extract_text_from_image
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

# 旧版去重记录（仅 content 预览 fallback）
_HASH_STORE = Path(__file__).resolve().parent.parent.parent / "upload_hashes.json"


def _compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _format_size(bytes_val: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def _get_kb(dataset_id: str) -> DifyKB:
    if is_local_rag():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前使用本地向量 RAG，无需 Dify 知识库",
        )
    if not dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="您的知识库尚未创建，请先完成注册",
        )
    return DifyKB(dataset_id)


def _resolve_dataset_id(collection: KbCollection, user_dataset_id: Optional[str]) -> str:
    return collection.dataset_id or user_dataset_id or ""


def _ensure_collections(
    db: Session, user_id: int, user_dataset_id: Optional[str]
) -> None:
    if not kb_crud.list_collections(db, user_id):
        kb_crud.seed_default_collections(db, user_id, user_dataset_id)
        db.commit()


def _resolve_collection(
    db: Session,
    user_id: int,
    collection_id: Optional[str],
    user_dataset_id: Optional[str],
) -> KbCollection:
    _ensure_collections(db, user_id, user_dataset_id)
    if collection_id:
        coll = kb_crud.get_collection(db, user_id, collection_id)
        if not coll:
            raise HTTPException(status_code=404, detail="知识库分区不存在")
        return coll
    coll = kb_crud.get_default_study_collection(db, user_id)
    if not coll:
        raise HTTPException(status_code=500, detail="默认学习区未初始化")
    return coll


def _guess_mime(suffix: str) -> Optional[str]:
    mapping = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    return mapping.get(suffix)


def _maybe_trigger_segment(db: Session, document: Document) -> None:
    """学习区文档上传后分段（及本地 RAG 索引）。"""
    if document.zone != "study":
        return
    from app.services.segment_service import segment_document

    try:
        segment_document(document.id, db)
        db.commit()
    except Exception:
        logger.exception("segment hook failed: document_id=%s", document.id)
        db.rollback()


def _finish_indexing_status(db: Session, doc: Document) -> None:
    """根据分段结果更新 indexing_status（非 study 区直接完成）。"""
    if (
        is_local_rag()
        and doc.zone != "study"
        and doc.indexing_status == "processing"
    ):
        doc.indexing_status = "completed"
        db.commit()
    elif doc.segment_status == "failed":
        doc.indexing_status = "failed"
        db.commit()


def _ensure_document_parsed(db: Session, doc: Document) -> bool:
    """解析文档文本并写入 global 缓存。成功返回 True。"""
    if doc.parsed_cache_key:
        return True
    global_doc = doc.global_document
    if global_doc and global_doc.parsed_text_path:
        doc.parsed_cache_key = global_doc.parsed_text_path
        db.commit()
        return True
    if not global_doc or not global_doc.storage_path:
        if doc.zone == "study":
            doc.segment_status = "failed"
        doc.indexing_status = "failed"
        db.commit()
        return False

    parse_outcome = parse_file_detailed(
        global_doc.storage_path,
        original_filename=global_doc.original_filename or doc.display_name,
    )
    if parse_outcome.text:
        parsed_text_path = storage_service.save_global_parsed_content(
            doc.content_hash,
            parse_outcome.text,
            page_texts=parse_outcome.page_texts,
            original_filename=global_doc.original_filename or doc.display_name,
            ocr_used=parse_outcome.ocr_used,
        )
        global_doc.parsed_text_path = parsed_text_path
        doc.parsed_cache_key = parsed_text_path
        db.commit()
        return True

    err = parse_outcome.error or "无法提取文档文本"
    logger.warning(
        "pipeline parse failed: document_id=%s, error=%s", doc.id, err
    )
    if doc.zone == "study":
        doc.segment_status = "failed"
    doc.indexing_status = "failed"
    db.commit()
    return False


def _run_document_pipeline(
    document_id: str,
    content_hash: str,
    *,
    ocr_mode: bool = False,
    image_ocr_mode: bool = False,
    storage_path: Optional[str] = None,
    original_filename: Optional[str] = None,
    total_pages: int = 0,
) -> None:
    """
    后台线程：OCR（可选）→ 解析 → 分段 → 索引。
    与扫描 PDF / 图片异步 OCR 共用同一入口。
    """
    from app.services.pdf_ocr_service import parse_pdf_with_ocr_fallback

    def on_page_progress(current: int, total: int) -> None:
        set_ocr_progress(
            document_id,
            content_hash,
            "processing",
            current_page=current,
            total_pages=total,
        )

    if ocr_mode or image_ocr_mode:
        set_ocr_progress(
            document_id,
            content_hash,
            "processing",
            current_page=0,
            total_pages=total_pages or 1,
        )

    db = SessionLocal()
    try:
        doc = kb_crud.get_document_by_id_internal(db, document_id)
        if not doc:
            return

        if image_ocr_mode and storage_path:
            ocr_text = extract_text_from_image(storage_path)
            if ocr_text is None or not ocr_text.strip():
                err = "OCR 识别失败，请确认图片包含文字"
                set_ocr_progress(
                    document_id,
                    content_hash,
                    "failed",
                    current_page=0,
                    total_pages=1,
                    error=err,
                )
                doc.indexing_status = "failed"
                if doc.zone == "study":
                    doc.segment_status = "failed"
                db.commit()
                return

            parsed_text_path = storage_service.save_global_parsed(
                content_hash, ocr_text
            )
            global_doc = doc.global_document
            if global_doc:
                global_doc.parsed_text_path = parsed_text_path
            doc.parsed_cache_key = parsed_text_path
            db.commit()

            set_ocr_progress(
                document_id,
                content_hash,
                "completed",
                current_page=1,
                total_pages=1,
            )
        elif ocr_mode and storage_path:
            outcome = parse_pdf_with_ocr_fallback(
                storage_path,
                original_filename=original_filename,
                on_page_progress=on_page_progress,
            )
            if not outcome.text:
                err = outcome.error or "OCR 未识别到文字"
                set_ocr_progress(
                    document_id,
                    content_hash,
                    "failed",
                    current_page=0,
                    total_pages=total_pages,
                    error=err,
                )
                if doc.zone == "study":
                    doc.segment_status = "failed"
                doc.indexing_status = "failed"
                db.commit()
                return

            parsed_text_path = storage_service.save_global_parsed_content(
                content_hash,
                outcome.text,
                page_texts=outcome.page_texts,
                original_filename=original_filename or doc.display_name,
                ocr_used=True,
            )
            global_doc = doc.global_document
            if global_doc:
                global_doc.parsed_text_path = parsed_text_path
            doc.parsed_cache_key = parsed_text_path
            db.commit()

            set_ocr_progress(
                document_id,
                content_hash,
                "completed",
                current_page=total_pages,
                total_pages=total_pages,
            )
        elif not _ensure_document_parsed(db, doc):
            return

        _maybe_trigger_segment(db, doc)
        db.refresh(doc)
        _finish_indexing_status(db, doc)
    except Exception:
        logger.exception("document pipeline failed: document_id=%s", document_id)
        if ocr_mode:
            set_ocr_progress(
                document_id,
                content_hash,
                "failed",
                current_page=0,
                total_pages=total_pages or 0,
                error="OCR 处理异常",
            )
        try:
            doc = kb_crud.get_document_by_id_internal(db, document_id)
            if doc:
                doc.indexing_status = "failed"
                if doc.zone == "study":
                    doc.segment_status = "failed"
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def _start_document_pipeline(
    document: Document,
    *,
    ocr_mode: bool = False,
    image_ocr_mode: bool = False,
    storage_path: Optional[str] = None,
    original_filename: Optional[str] = None,
    total_pages: int = 0,
) -> None:
    run_in_background(
        lambda: _run_document_pipeline(
            document.id,
            document.content_hash,
            ocr_mode=ocr_mode,
            image_ocr_mode=image_ocr_mode,
            storage_path=storage_path,
            original_filename=original_filename,
            total_pages=total_pages,
        ),
        name="doc-pipeline",
    )


def _run_async_pdf_ocr(
    document_id: str,
    content_hash: str,
    storage_path: str,
    original_filename: str,
    total_pages: int,
) -> None:
    """兼容旧调用：委托统一 document pipeline（OCR 模式）。"""
    _run_document_pipeline(
        document_id,
        content_hash,
        ocr_mode=True,
        storage_path=storage_path,
        original_filename=original_filename,
        total_pages=total_pages,
    )


def _ocr_fields_for_doc(doc: Document) -> dict:
    progress = get_ocr_progress(document_id=doc.id, content_hash=doc.content_hash)
    if not progress:
        return {}
    return {
        "ocr_status": progress["status"],
        "ocr_current_page": progress.get("current_page", 0),
        "ocr_total_pages": progress.get("total_pages", 0),
    }


def _start_async_pdf_ocr(
    document: Document,
    storage_path: str,
    original_filename: str,
    total_pages: int,
) -> None:
    _start_document_pipeline(
        document,
        ocr_mode=True,
        storage_path=storage_path,
        original_filename=original_filename,
        total_pages=total_pages,
    )


def _start_async_image_ocr(
    document: Document,
    storage_path: str,
) -> None:
    _start_document_pipeline(
        document,
        image_ocr_mode=True,
        storage_path=storage_path,
        total_pages=1,
    )


def _should_defer_pdf_ocr(
    file_path: str, suffix: str, has_parsed_text: bool
) -> tuple[bool, int]:
    if suffix != ".pdf" or has_parsed_text or not is_local_rag():
        return False, 0
    return is_scanned_pdf(file_path)


def _load_hash_store_fallback() -> dict:
    if not _HASH_STORE.exists():
        return {}
    try:
        with open(_HASH_STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _is_dify_file_too_large(http_status: int, detail: str) -> bool:
    if http_status == 413:
        return True
    if http_status != 400:
        return False
    lower = detail.lower()
    size_keywords = (
        "file size",
        "file too large",
        "too large",
        "size limit",
        "exceeds",
        "maximum",
        "max size",
        "upload limit",
        "文件过大",
        "大小",
        "超出",
        "限制",
        "mb",
        "limit",
    )
    return any(kw in lower for kw in size_keywords)


def _raise_dify_upload_error(result: dict) -> None:
    detail = result.get("error") or "文件上传到知识库失败"
    http_status = result.get("http_status", 502)
    if _is_dify_file_too_large(http_status, detail):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Dify 知识库服务拒绝接收该文件（{detail}）。"
                f"这是 Dify Cloud 侧的单文件大小限制，本地未限制上传大小。"
                f"请压缩或拆分 PDF 后重试。"
            ),
        )
    if http_status in (400, 415, 422):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"知识库无法处理该文件: {detail}",
        )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"文件上传到知识库失败: {detail}",
    )


def _dify_upload_target(
    *,
    is_image: bool,
    safe_filename: str,
    raw_storage_path: str,
    parsed_text_path: Optional[str],
) -> tuple[str, str]:
    if is_image and parsed_text_path:
        return parsed_text_path, f"{Path(safe_filename).stem}_ocr.txt"
    return raw_storage_path, safe_filename


def _check_dify_upload_size(file_path: str) -> None:
    if not DIFY_MAX_UPLOAD_SIZE:
        return
    size = Path(file_path).stat().st_size
    if size > DIFY_MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=(
                f"文件过大 ({_format_size(size)})，"
                f"知识库单文件限制不超过 {_format_size(DIFY_MAX_UPLOAD_SIZE)}。"
                f"请压缩或拆分后重试。"
            ),
        )


def _duplicate_response(
    existing: Document, dataset_id: str, file_name: str
) -> UploadResponse:
    ocr_fields = _ocr_fields_for_doc(existing)
    status = "duplicate"
    if ocr_fields.get("ocr_status") == "processing":
        status = "indexing"
    return UploadResponse(
        message="该文件已上传过，无需重复上传",
        batch_id=existing.dify_batch_id or existing.id,
        document_id=existing.dify_document_id or existing.id,
        id=existing.id,
        file_name=file_name,
        dataset_id=dataset_id,
        collection_id=existing.collection_id,
        status=status,
        segment_status=existing.segment_status,
        **ocr_fields,
    )


def list_collections(db: Session, user_id: int, user_dataset_id: Optional[str]) -> CollectionListOut:
    _ensure_collections(db, user_id, user_dataset_id)
    rows = kb_crud.list_collections(db, user_id)
    return CollectionListOut(
        collections=[CollectionOut.model_validate(c) for c in rows],
        total=len(rows),
    )


def create_collection(
    db: Session,
    user_id: int,
    payload: CollectionCreate,
    user_dataset_id: Optional[str],
) -> CollectionOut:
    _ensure_collections(db, user_id, user_dataset_id)
    existing_names = {c.name for c in kb_crud.list_collections(db, user_id)}
    if payload.name in existing_names:
        raise HTTPException(status_code=400, detail="分区名称已存在")
    coll = kb_crud.create_collection(
        db,
        user_id=user_id,
        name=payload.name,
        zone=payload.zone,
        description=payload.description,
    )
    db.commit()
    db.refresh(coll)
    return CollectionOut.model_validate(coll)


def delete_collection(
    db: Session,
    user_id: int,
    collection_id: str,
) -> dict:
    """删除知识库分区（不允许删除默认分区）"""
    collection = kb_crud.get_collection(db, user_id, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="知识库分区不存在")
    if collection.is_default:
        raise HTTPException(status_code=400, detail="不能删除默认分区")
    kb_crud.delete_collection(db, user_id, collection_id)
    db.commit()
    return {"message": "分区已删除", "collection_id": collection_id}


def update_collection(
    db: Session,
    user_id: int,
    collection_id: str,
    payload: CollectionUpdate,
) -> CollectionOut:
    coll = kb_crud.get_collection(db, user_id, collection_id)
    if not coll:
        raise HTTPException(status_code=404, detail="知识库分区不存在")
    if payload.name and payload.name != coll.name:
        existing_names = {
            c.name for c in kb_crud.list_collections(db, user_id) if c.id != collection_id
        }
        if payload.name in existing_names:
            raise HTTPException(status_code=400, detail="分区名称已存在")
    kb_crud.update_collection(db, coll, name=payload.name, description=payload.description)
    db.commit()
    db.refresh(coll)
    return CollectionOut.model_validate(coll)


def upload_document(
    db: Session,
    user_id: int,
    user_dataset_id: Optional[str],
    filename: str,
    content_bytes: bytes,
    collection_id: Optional[str] = None,
    max_upload_size: int = 0,
    use_oss: bool = False,
) -> UploadResponse:
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {suffix}，支持的格式: {', '.join(SUPPORTED_EXTENSIONS.keys())}",
        )

    if not use_oss and max_upload_size and len(content_bytes) > max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=(
                f"文件过大 ({_format_size(len(content_bytes))})，"
                f"演示环境限制单个文件不超过 {_format_size(max_upload_size)}"
            ),
        )

    collection = _resolve_collection(db, user_id, collection_id, user_dataset_id)
    dataset_id = _resolve_dataset_id(collection, user_dataset_id)
    kb = None if is_local_rag() else _get_kb(dataset_id)

    safe_filename = Path(filename).name
    file_hash = _compute_sha256(content_bytes)
    existing = kb_crud.get_document_by_user_hash(db, user_id, file_hash)
    if existing:
        logger.info("文件重复上传: user_id=%s, hash=%s...", user_id, file_hash[:16])
        return _duplicate_response(existing, dataset_id, safe_filename)

    is_image = suffix in IMAGE_EXTENSIONS
    ocr_processed = False
    last_parse_error: Optional[str] = None
    defer_pdf_ocr = False
    defer_image_ocr = False
    ocr_total_pages = 0
    global_doc = kb_crud.get_global_document_by_hash(db, file_hash)
    upload_path: str
    display_name = safe_filename
    parsed_text_path: Optional[str] = None
    parsed_cache_key: Optional[str] = None
    raw_storage_path: Optional[str] = None

    if global_doc:
        upload_path = global_doc.storage_path
        parsed_text_path = global_doc.parsed_text_path
        raw_storage_path = global_doc.storage_path
        if not safe_filename and global_doc.original_filename:
            safe_filename = global_doc.original_filename
        logger.info("命中全局去重: hash=%s, path=%s", file_hash[:16], upload_path)
        if not parsed_text_path and raw_storage_path:
            if is_image and IMAGE_OCR_ASYNC:
                defer_image_ocr = True
            else:
                defer_pdf_ocr, ocr_total_pages = _should_defer_pdf_ocr(
                    raw_storage_path, suffix, has_parsed_text=False
                )
    else:
        raw_storage_path = storage_service.save_global_file(
            file_hash, content_bytes, suffix
        )
        upload_path = raw_storage_path

        if is_image:
            if IMAGE_OCR_ASYNC:
                defer_image_ocr = True
                logger.info("图片异步 OCR: hash=%s", file_hash[:16])
            else:
                ocr_text = extract_text_from_image(raw_storage_path)
                if ocr_text is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="OCR 识别失败，请确认图片包含文字；本地模式需安装 paddleocr",
                    )
                if not ocr_text.strip():
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="图片中未检测到文字",
                    )
                parsed_text_path = storage_service.save_global_parsed(file_hash, ocr_text)
                display_name = f"{Path(safe_filename).stem}_ocr.txt"
                upload_path = parsed_text_path
                ocr_processed = True
        else:
            defer_pdf_ocr, ocr_total_pages = _should_defer_pdf_ocr(
                raw_storage_path, suffix, has_parsed_text=False
            )
            if defer_pdf_ocr:
                logger.info(
                    "扫描 PDF 异步 OCR: hash=%s, pages=%d",
                    file_hash[:16],
                    ocr_total_pages,
                )
            elif DOCUMENT_PIPELINE_ASYNC:
                logger.info(
                    "异步文档 pipeline: hash=%s, 解析/分段延后",
                    file_hash[:16],
                )
            else:
                parse_outcome = parse_file_detailed(
                    raw_storage_path, original_filename=safe_filename
                )
                parsed_content = parse_outcome.text
                if parse_outcome.ocr_used:
                    ocr_processed = True
                if parsed_content:
                    parsed_text_path = storage_service.save_global_parsed_content(
                        file_hash,
                        parsed_content,
                        page_texts=parse_outcome.page_texts,
                        original_filename=safe_filename,
                        ocr_used=parse_outcome.ocr_used,
                    )
                elif parse_outcome.error:
                    last_parse_error = parse_outcome.error
                    logger.warning(
                        "上传时文本解析失败: hash=%s, error=%s",
                        file_hash[:16],
                        parse_outcome.error,
                    )

        global_doc = kb_crud.create_global_document(
            db,
            content_hash=file_hash,
            original_filename=safe_filename,
            file_size=len(content_bytes),
            storage_path=raw_storage_path,
            mime_type=_guess_mime(suffix),
            parsed_text_path=parsed_text_path,
        )

    if parsed_text_path:
        parsed_cache_key = parsed_text_path
    elif global_doc and global_doc.parsed_text_path:
        parsed_cache_key = global_doc.parsed_text_path

    if is_image and global_doc and global_doc.parsed_text_path:
        upload_path = global_doc.parsed_text_path
        display_name = f"{Path(safe_filename).stem}_ocr.txt"

    dify_doc_id: Optional[str] = None
    dify_batch_id: Optional[str] = None
    indexing_status = "processing"

    if is_local_rag():
        # 本地 RAG：仅存盘 + 分段 + Chroma 索引，不调用 Dify
        pass
    else:
        dify_path, dify_filename = _dify_upload_target(
            is_image=is_image,
            safe_filename=safe_filename,
            raw_storage_path=raw_storage_path or upload_path,
            parsed_text_path=parsed_text_path,
        )
        _check_dify_upload_size(dify_path)

        result = kb.add_document(dify_path, upload_filename=dify_filename)
        if "error" in result:
            _raise_dify_upload_error(result)
        dify_doc_id = result["document_id"]
        dify_batch_id = result["batch_id"]

    document = kb_crud.create_document(
        db,
        user_id=user_id,
        collection_id=collection.id,
        zone=collection.zone,
        display_name=display_name,
        content_hash=file_hash,
        global_document_id=global_doc.id if global_doc else None,
        dify_document_id=dify_doc_id,
        dify_batch_id=dify_batch_id,
        parsed_cache_key=parsed_cache_key,
        indexing_status=indexing_status,
    )
    db.commit()
    db.refresh(document)

    if defer_pdf_ocr and raw_storage_path:
        in_progress = get_ocr_progress(content_hash=file_hash)
        if in_progress and in_progress.get("status") == "processing":
            set_ocr_progress(
                document.id,
                file_hash,
                "processing",
                current_page=in_progress.get("current_page", 0),
                total_pages=in_progress.get("total_pages", ocr_total_pages),
            )
        else:
            _start_async_pdf_ocr(
                document,
                raw_storage_path,
                safe_filename,
                ocr_total_pages,
            )
    elif defer_image_ocr and raw_storage_path:
        set_ocr_progress(document.id, file_hash, "processing", current_page=0, total_pages=1)
        _start_async_image_ocr(document, raw_storage_path)
    elif DOCUMENT_PIPELINE_ASYNC and not is_image:
        _start_document_pipeline(document)
    else:
        _maybe_trigger_segment(db, document)
        _finish_indexing_status(db, document)
    db.refresh(document)

    resp_doc_id = document.dify_document_id or document.id
    resp_batch_id = document.dify_batch_id or document.id
    ocr_fields = _ocr_fields_for_doc(document)
    if document.segment_status == "failed":
        resp_status = "error"
    elif document.indexing_status == "completed":
        resp_status = "completed"
    elif defer_pdf_ocr or defer_image_ocr or ocr_fields.get("ocr_status") == "processing":
        resp_status = "indexing"
    else:
        resp_status = "indexing"

    message = "文件已上传"
    parse_warning: Optional[str] = None
    if document.segment_status == "failed":
        message += "，分段失败：无法提取文档文本"
        parse_warning = last_parse_error or (
            "PDF 无嵌入文本层（可能是扫描版），请安装 paddleocr 或上传可复制文字的 PDF"
        )
    elif defer_pdf_ocr or defer_image_ocr or ocr_fields.get("ocr_status") == "processing":
        message += "，正在 OCR 识别"
    elif resp_status == "completed":
        message += "，索引完成"
    else:
        message += "，正在索引中"
    if ocr_processed:
        message += "（已通过 OCR 识别文字）"

    return UploadResponse(
        message=message,
        batch_id=resp_batch_id,
        document_id=resp_doc_id,
        id=document.id,
        file_name=display_name,
        dataset_id=dataset_id or None,
        collection_id=collection.id,
        status=resp_status,
        segment_status=document.segment_status,
        parse_warning=parse_warning,
        ocr_processed=ocr_processed or bool(defer_pdf_ocr) or bool(defer_image_ocr),
        **ocr_fields,
    )


def document_status_payload(doc: Document, batch_id: str) -> dict:
    """本地 RAG 文档状态（含 OCR 进度）。"""
    ocr_fields = _ocr_fields_for_doc(doc)
    if doc.segment_status == "failed":
        ocr_err = ocr_fields.get("ocr_status") == "failed"
        err_msg = (
            "PDF OCR 识别失败，请确认已安装 paddleocr"
            if ocr_err
            else (
                "文档文本提取失败，可能是扫描版 PDF，"
                "请上传可复制文字的 PDF 或使用 OCR"
            )
        )
        progress = get_ocr_progress(document_id=doc.id, content_hash=doc.content_hash)
        if progress and progress.get("error"):
            err_msg = progress["error"]
        return {
            "batch_id": batch_id,
            "status": "error",
            "segment_status": doc.segment_status,
            "error_message": err_msg,
            "document_id": doc.id,
            **ocr_fields,
        }

    status = doc.indexing_status
    if ocr_fields.get("ocr_status") == "processing":
        status = "processing"

    return {
        "batch_id": batch_id,
        "status": status,
        "segment_status": doc.segment_status,
        "document_id": doc.id,
        **ocr_fields,
    }


def list_documents(
    db: Session,
    user_id: int,
    user_dataset_id: Optional[str],
    page: int = 1,
    limit: int = 20,
    collection_id: Optional[str] = None,
) -> DocumentListOut:
    if collection_id:
        coll = kb_crud.get_collection(db, user_id, collection_id)
        if not coll:
            raise HTTPException(status_code=404, detail="知识库分区不存在")
        dataset_id = _resolve_dataset_id(coll, user_dataset_id)
    else:
        dataset_id = user_dataset_id

    docs, total = kb_crud.list_documents(db, user_id, collection_id, page, limit)

    # 无分区过滤且 DB 无记录时，回退 Dify 列表（兼容旧上传数据）
    if total == 0 and not collection_id and dataset_id and not is_local_rag():
        kb = _get_kb(dataset_id)
        result = kb.list_documents(page=page, limit=limit)
        dify_docs = []
        for doc in result.get("data", []):
            dify_docs.append(
                DocumentOut(
                    id=doc.get("id"),
                    name=doc.get("name", ""),
                    collection_id="",
                    zone="study",
                    file_type=doc.get("file_type"),
                    file_size=doc.get("file_size"),
                    indexing_status=doc.get("indexing_status", "unknown"),
                    dify_document_id=doc.get("id"),
                    created_at=doc.get("created_at"),
                    updated_at=doc.get("updated_at"),
                )
            )
        return DocumentListOut(
            documents=dify_docs,
            total=result.get("total", len(dify_docs)),
            page=page,
            limit=limit,
            dataset_id=dataset_id,
            collection_id=collection_id,
        )

    out_docs = []
    for doc in docs:
        file_size = None
        file_type = None
        if doc.global_document:
            file_size = doc.global_document.file_size
            file_type = doc.global_document.mime_type
        out_docs.append(
            DocumentOut(
                id=doc.dify_document_id or doc.id,
                name=doc.display_name,
                collection_id=doc.collection_id,
                zone=doc.zone,
                file_type=file_type,
                file_size=file_size,
                indexing_status=doc.indexing_status,
                segment_status=doc.segment_status,
                question_gen_status=doc.question_gen_status,
                dify_document_id=doc.dify_document_id,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
                **_ocr_fields_for_doc(doc),
            )
        )

    return DocumentListOut(
        documents=out_docs,
        total=total,
        page=page,
        limit=limit,
        dataset_id=dataset_id,
        collection_id=collection_id,
    )


def get_document_content(
    db: Session, user_id: int, doc_id: str
) -> dict:
    doc = kb_crud.get_document_by_id_or_dify(db, user_id, doc_id)
    if doc:
        content = None
        if doc.parsed_cache_key:
            content = storage_service.read_text_at_path(doc.parsed_cache_key)
        if not content and doc.global_document and doc.global_document.parsed_text_path:
            content = storage_service.read_text_at_path(doc.global_document.parsed_text_path)
        file_type = _infer_document_file_type(doc)
        preview_mode = "pdf" if file_type == "pdf" else "text"
        has_raw_file = _resolve_document_storage_path(doc) is not None
        if content:
            return {
                "doc_id": doc.dify_document_id or doc.id,
                "file_name": doc.display_name,
                "content": content,
                "file_type": file_type,
                "preview_mode": preview_mode,
                "has_raw_file": has_raw_file,
                "mock": False,
            }
        if has_raw_file and file_type == "pdf":
            return {
                "doc_id": doc.dify_document_id or doc.id,
                "file_name": doc.display_name,
                "content": "",
                "file_type": file_type,
                "preview_mode": "pdf",
                "has_raw_file": True,
                "mock": False,
            }

    # 旧 upload_hashes.json fallback
    store = _load_hash_store_fallback()
    for key, record in store.items():
        if record.get("document_id") == doc_id and key.startswith(f"{user_id}:"):
            file_name = record.get("file_name", "")
            file_hash = key.split(":", 1)[1]
            cache_filename = f"{Path(file_name).stem}_{file_hash[:16]}.txt"
            content = storage_service.get_parsed(user_id, cache_filename)
            if content:
                return {
                    "doc_id": doc_id,
                    "file_name": file_name,
                    "content": content,
                    "file_type": _file_type_from_name(file_name),
                    "preview_mode": "text",
                    "has_raw_file": False,
                    "mock": False,
                }

    return {
        "doc_id": doc_id,
        "content": (
            f"# 文档内容不可用\n\n"
            f"文档 ID: {doc_id}\n\n"
            f"该文档可能是在内容缓存功能上线前上传的，暂无实时预览。\n"
            f"您可以在对话中通过知识库检索查看文档内容。\n\n"
            f"> 提示：在对话中直接引用该文档，Tina 会自动从知识库中检索相关内容。"
        ),
        "file_type": "unknown",
        "preview_mode": "text",
        "has_raw_file": False,
        "mock": True,
    }


def _file_type_from_name(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".md"):
        return "md"
    if lower.endswith(".txt"):
        return "txt"
    if lower.endswith(".docx") or lower.endswith(".doc"):
        return "docx"
    return "text"


def _resolve_document_storage_path(doc: Document) -> Optional[str]:
    global_doc = doc.global_document
    if global_doc and global_doc.storage_path:
        path = Path(global_doc.storage_path)
        if path.is_file():
            return str(path)
    return None


def _infer_document_file_type(doc: Document) -> str:
    global_doc = doc.global_document
    if global_doc:
        if global_doc.mime_type == "application/pdf":
            return "pdf"
        if global_doc.original_filename:
            ft = _file_type_from_name(global_doc.original_filename)
            if ft != "text":
                return ft
        if global_doc.storage_path.lower().endswith(".pdf"):
            return "pdf"
    return _file_type_from_name(doc.display_name)


def serve_document_file(db: Session, user_id: int, doc_id: str) -> FileResponse:
    doc = kb_crud.get_document_by_id_or_dify(db, user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    storage_path = _resolve_document_storage_path(doc)
    if not storage_path:
        raise HTTPException(status_code=404, detail="原始文件不可用")

    media_type = None
    if doc.global_document and doc.global_document.mime_type:
        media_type = doc.global_document.mime_type
    if not media_type:
        media_type = mimetypes.guess_type(storage_path)[0] or "application/octet-stream"

    return FileResponse(
        storage_path,
        media_type=media_type,
        filename=doc.display_name,
    )


def delete_document(
    db: Session,
    user_id: int,
    user_dataset_id: Optional[str],
    doc_id: str,
) -> dict:
    doc = kb_crud.get_document_by_id_or_dify(db, user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    dataset_id = user_dataset_id
    if doc.collection_id:
        coll = kb_crud.get_collection(db, user_id, doc.collection_id)
        if coll:
            dataset_id = _resolve_dataset_id(coll, user_dataset_id)

    try:
        if doc.dify_document_id and dataset_id and not is_local_rag():
            kb = _get_kb(dataset_id)
            if not kb.delete_document(doc.dify_document_id):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="删除文档失败，请检查文档是否存在",
                )

        if is_local_rag():
            from app.services.index_service import delete_document_index

            delete_document_index(doc.id)

        content_hash = doc.content_hash
        global_doc = doc.global_document
        parsed_cache_key = doc.parsed_cache_key

        kb_crud.delete_related_for_document(db, doc.id)
        global_document_id = kb_crud.delete_document_row(db, doc)

        if parsed_cache_key and (
            not global_doc or parsed_cache_key != global_doc.parsed_text_path
        ):
            storage_service.delete_file_at_path(parsed_cache_key)

        if global_document_id and global_doc:
            remaining = kb_crud.count_documents_for_global(db, global_document_id)
            if remaining == 0:
                kb_crud.delete_provenance_for_global(db, global_document_id)
                storage_service.delete_file_at_path(global_doc.storage_path)
                if global_doc.parsed_text_path:
                    storage_service.delete_file_at_path(global_doc.parsed_text_path)
                kb_crud.delete_global_document(db, global_doc)
        elif global_document_id:
            remaining = kb_crud.count_documents_for_global(db, global_document_id)
            if remaining == 0:
                orphan = kb_crud.get_global_document_by_hash(db, content_hash)
                if orphan:
                    kb_crud.delete_provenance_for_global(db, orphan.id)
                    storage_service.delete_file_at_path(orphan.storage_path)
                    if orphan.parsed_text_path:
                        storage_service.delete_file_at_path(orphan.parsed_text_path)
                    kb_crud.delete_global_document(db, orphan)

        db.commit()
        return {"message": "文档已删除", "doc_id": doc_id}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception(
            "delete_document failed doc_id=%s user_id=%s", doc_id, user_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除文档失败，请稍后重试",
        )
