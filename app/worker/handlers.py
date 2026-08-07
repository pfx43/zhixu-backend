"""
Worker 任务处理器 — 每种任务类型的实际执行逻辑
"""
import json
import logging
import traceback
from typing import Any, Dict

from app.core.redis_queue import update_job_status

logger = logging.getLogger("worker.handlers")


def _resolve_local_path(storage_path: str) -> str:
    """
    将 storage_path 解析为本地文件路径。
    
    COS 模式下 storage_path 是 object_key，需先下载到临时文件；
    Local 模式下直接返回本地路径。
    """
    import tempfile
    from app.core.config import STORAGE_BACKEND
    
    if STORAGE_BACKEND != "cos":
        return storage_path
    
    from app.services.knowledge.storage_service import storage_service
    
    content = storage_service.read_file_at_path(storage_path)
    if content is None:
        raise FileNotFoundError(f"COS 对象不存在或无法读取: {storage_path}")
    
    # 保留原始文件扩展名以帮助解析器识别格式
    suffix = ""
    name = storage_path.rsplit("/", 1)[-1] if "/" in storage_path else storage_path
    if "." in name:
        suffix = "." + name.rsplit(".", 1)[-1]
    
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(content)
        tmp.flush()
        logger.info("COS 文件已下载到临时路径: %s -> %s (%d bytes)", storage_path, tmp.name, len(content))
        return tmp.name
    except Exception:
        tmp.close()
        import os
        os.unlink(tmp.name)
        raise


def _cleanup_temp_file(local_path: str) -> None:
    """清理 COS 模式下下载的临时文件"""
    import os
    from app.core.config import STORAGE_BACKEND
    
    if STORAGE_BACKEND != "cos":
        return
    
    try:
        os.unlink(local_path)
        logger.info("临时文件已清理: %s", local_path)
    except OSError:
        pass


def handle_ocr_job(job_id: str, user_id: int, payload: Dict[str, Any]):
    """
    处理 OCR 任务。
    
    payload:
        - document_id: 文档 ID
        - content_hash: 文件哈希
        - storage_path: 文件存储路径/键（COS 模式为 object_key）
        - original_filename: 原始文件名
    """
    doc_id = payload.get("document_id")
    content_hash = payload.get("content_hash")
    storage_path = payload.get("storage_path")
    original_filename = payload.get("original_filename", "")

    if not storage_path:
        update_job_status(job_id, "failed", error="缺少 storage_path")
        return

    local_path = None
    try:
        update_job_status(job_id, "processing", progress=10)
        logger.info("开始 OCR: doc_id=%s path=%s", doc_id, storage_path)

        local_path = _resolve_local_path(storage_path)
        
        from app.services.ocr.pdf_ocr_service import parse_pdf_with_ocr_fallback

        text = parse_pdf_with_ocr_fallback(
            file_path=local_path,
            original_filename=original_filename,
        )
        update_job_status(job_id, "processing", progress=80)

        # 保存解析结果
        from app.services.knowledge.storage_service import storage_service
        parsed_path = storage_service.save_global_parsed_content(
            content_hash, text or ""
        )
        update_job_status(job_id, "processing", progress=95)

        # 更新 DB
        from app.core.database import SessionLocal
        from app.models import Document
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc and doc.global_document:
                doc.global_document.parsed_text_path = parsed_path
                db.commit()
            update_job_status(
                job_id,
                "completed",
                progress=100,
                result=json.dumps({"parsed_path": parsed_path}),
            )
        except Exception as db_err:
            db.rollback()
            logger.error("OCR DB 更新失败: %s", db_err)
            update_job_status(
                job_id,
                "completed",
                progress=100,
                result=json.dumps({"parsed_path": parsed_path}),
            )
        finally:
            db.close()

        logger.info("OCR 完成: doc_id=%s", doc_id)

    except Exception as e:
        logger.error("OCR 处理失败: %s\n%s", e, traceback.format_exc())
        update_job_status(job_id, "failed", error=str(e))
    finally:
        if local_path:
            _cleanup_temp_file(local_path)


def handle_parse_job(job_id: str, user_id: int, payload: Dict[str, Any]):
    """
    处理文档解析 + 分段 + 索引任务。
    
    payload:
        - document_id: 文档 ID
        - content_hash: 文件哈希
        - storage_path: 文件存储路径/键（COS 模式为 object_key）
        - original_filename: 原始文件名
    """
    doc_id = payload.get("document_id")
    content_hash = payload.get("content_hash")
    storage_path = payload.get("storage_path")
    original_filename = payload.get("original_filename", "")

    if not storage_path:
        update_job_status(job_id, "failed", error="缺少 storage_path")
        return

    local_path = None
    try:
        update_job_status(job_id, "processing", progress=5)
        logger.info("开始解析: doc_id=%s path=%s", doc_id, storage_path)

        local_path = _resolve_local_path(storage_path)

        from app.services.knowledge.file_parser import parse_file_detailed

        parse_outcome = parse_file_detailed(
            local_path,
            original_filename=original_filename,
        )
        update_job_status(job_id, "processing", progress=30)

        # 保存解析文本
        from app.services.knowledge.storage_service import storage_service
        parsed_path = storage_service.save_global_parsed_content(
            content_hash,
            parse_outcome.text or "",
            original_filename=original_filename,
        )
        update_job_status(job_id, "processing", progress=50)

        # 更新 DB
        from app.core.database import SessionLocal
        from app.models import Document
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc and doc.global_document:
                doc.global_document.parsed_text_path = parsed_path
                db.commit()
        except Exception as db_err:
            db.rollback()
            logger.error("Parse DB 更新失败: %s", db_err)
        finally:
            db.close()

        update_job_status(job_id, "processing", progress=60)

        # 分段并索引
        from app.services.knowledge.segment_service import segment_document
        from app.services.knowledge.index_service import index_document_segments
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            segment_document(db, doc_id)
            update_job_status(job_id, "processing", progress=80)

            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                index_document_segments(db, doc)
            update_job_status(job_id, "processing", progress=95)
        except Exception as seg_err:
            db.rollback()
            logger.error("分段/索引失败: %s", seg_err)
        finally:
            db.close()

        update_job_status(
            job_id,
            "completed",
            progress=100,
            result=json.dumps({"parsed_path": parsed_path}),
        )
        logger.info("解析完成: doc_id=%s", doc_id)

    except Exception as e:
        logger.error("解析处理失败: %s\n%s", e, traceback.format_exc())
        update_job_status(job_id, "failed", error=str(e))
    finally:
        if local_path:
            _cleanup_temp_file(local_path)


def handle_index_job(job_id: str, user_id: int, payload: Dict[str, Any]):
    """
    处理文档向量索引写入任务（独立于 parse 流水线，可异步单独触发）。
    
    payload:
        - document_id: 文档 ID
    """
    doc_id = payload.get("document_id")

    if not doc_id:
        update_job_status(job_id, "failed", error="缺少 document_id")
        return

    try:
        update_job_status(job_id, "processing", progress=10)
        logger.info("开始索引: doc_id=%s user_id=%s", doc_id, user_id)

        from app.core.database import SessionLocal
        from app.models import Document
        from app.services.knowledge.index_service import index_document_segments

        db = SessionLocal()
        try:
            doc = db.query(Document).filter(
                Document.id == doc_id, Document.user_id == user_id
            ).first()
            if not doc:
                update_job_status(job_id, "failed", error="文档不存在或无权访问")
                return

            update_job_status(job_id, "processing", progress=30)
            count = index_document_segments(db, doc)
            update_job_status(
                job_id,
                "completed",
                progress=100,
                result=json.dumps({"indexed_segments": count}),
            )
            logger.info("索引完成: doc_id=%s count=%d", doc_id, count)
        finally:
            db.close()

    except Exception as e:
        logger.error("索引处理失败: %s\n%s", e, traceback.format_exc())
        update_job_status(job_id, "failed", error=str(e))


def handle_question_gen_job(job_id: str, user_id: int, payload: Dict[str, Any]):
    """
    处理批量出题任务。
    
    payload:
        - document_id: 文档 ID
        - count: 出题数量
    """
    doc_id = payload.get("document_id")
    count = payload.get("count", 10)

    if not doc_id:
        update_job_status(job_id, "failed", error="缺少 document_id")
        return

    try:
        update_job_status(job_id, "processing", progress=5)
        logger.info("开始出题: doc_id=%s count=%d", doc_id, count)

        from app.core.database import SessionLocal
        from app.models import Document
        from app.services.quiz.question_gen_service import generate_questions_for_document

        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user_id).first()
            if not doc:
                update_job_status(job_id, "failed", error="文档不存在或无权访问")
                return

            questions = generate_questions_for_document(
                db, doc, count, progress_callback=lambda p: update_job_status(job_id, "processing", progress=5 + int(p * 0.9))
            )
            update_job_status(
                job_id,
                "completed",
                progress=100,
                result=json.dumps({"question_count": len(questions)}),
            )
        finally:
            db.close()

        logger.info("出题完成: doc_id=%s count=%d", doc_id, count)

    except Exception as e:
        logger.error("出题处理失败: %s\n%s", e, traceback.format_exc())
        update_job_status(job_id, "failed", error=str(e))