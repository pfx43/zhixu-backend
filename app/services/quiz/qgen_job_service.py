"""出题作业：入队快照、抢单、按页 complete 入库。出题进程不写 global_questions。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.crud import kb as kb_crud
from app.models import Document, Goal
from app.models.qgen import QgenJob, QgenJobPage
from app.schemas.question import PageQuestionResponse
from app.services.knowledge.page_service import (
    build_near_page_context,
    get_pages_by_numbers,
)
from app.services.quiz.qgen_count import persist_questions_per_page
from app.services.quiz.question_normalize import normalize_question

logger = logging.getLogger(__name__)

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# 本进程正在跑的异步/SSE 出题（worker 入队不走这里，看 qgen_jobs）
_inflight_document_ids: set[str] = set()


def mark_document_generating(document_id: str) -> None:
    if document_id:
        _inflight_document_ids.add(document_id)


def unmark_document_generating(document_id: str) -> None:
    _inflight_document_ids.discard(document_id)


def is_document_generating(document_id: str) -> bool:
    return document_id in _inflight_document_ids


def active_job_document_ids(
    db: Session, user_id: int, document_ids: list[str]
) -> set[str]:
    if not document_ids:
        return set()
    rows = (
        db.query(QgenJob.document_id)
        .filter(
            QgenJob.user_id == user_id,
            QgenJob.document_id.in_(document_ids),
            QgenJob.status.in_((STATUS_QUEUED, STATUS_RUNNING)),
        )
        .all()
    )
    return {row[0] for row in rows}


def resolve_question_gen_status(
    document_id: str,
    stored: Optional[str],
    question_count: int,
    *,
    active_job_docs: Optional[set[str]] = None,
) -> str:
    """列表用的出题状态：进程挂掉后残留的 processing 不能一直显示「出题中」。"""
    if is_document_generating(document_id) or (
        active_job_docs is not None and document_id in active_job_docs
    ):
        return "processing"
    status = stored or "not_started"
    if status == "processing":
        return "completed" if question_count > 0 else "not_started"
    return status


def _active_goal_text(db: Session, user_id: int) -> Optional[str]:
    row = (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status == "active")
        .order_by(Goal.created_at.desc())
        .first()
    )
    return row.text if row else None


def _document_tcn_domain(document: Document) -> Optional[str]:
    value = getattr(document, "tcn_domain", None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _serialize_near_pages(near_pages: dict[int, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for num, page in near_pages.items():
        out[str(num)] = {
            "page_number": page.get("page_number", num),
            "title": page.get("title") or f"第 {num} 页",
            "content": page.get("content") or "",
            "segment_id": page.get("segment_id"),
        }
    return out


def job_to_worker_payload(job: QgenJob) -> dict[str, Any]:
    pages = []
    for page in job.pages:
        pages.append(
            {
                "page_number": page.page_number,
                "title": page.title,
                "content": page.content,
                "segment_id": page.segment_id,
                "status": page.status,
                "near_pages": page.near_pages_json or {},
                "allowed_page_numbers": page.allowed_page_numbers_json or [],
            }
        )
    return {
        "job_id": job.id,
        "user_id": job.user_id,
        "document_id": job.document_id,
        "mode": job.mode,
        "status": job.status,
        "goal_text": job.goal_text,
        "tag_hint": job.tag_hint,
        "tcn_domain": job.tcn_domain,
        "questions_per_page": job.questions_per_page,
        "pages": pages,
    }


def job_to_public(job: QgenJob, *, user_id: int) -> dict[str, Any]:
    if job.user_id != user_id:
        raise HTTPException(status_code=404, detail="出题任务不存在")
    return {
        "job_id": job.id,
        "document_id": job.document_id,
        "mode": job.mode,
        "status": job.status,
        "pages": [
            {
                "page_number": page.page_number,
                "status": page.status,
                "error": page.error,
            }
            for page in job.pages
        ],
    }


def enqueue_generate_from_pages(
    db: Session,
    user_id: int,
    document_id: str,
    page_numbers: list[int],
    questions_per_page: Optional[int] = None,
) -> PageQuestionResponse:
    from app.services.quiz import question_gen_service

    doc = kb_crud.get_document_by_id_or_dify(db, user_id, document_id)
    doc = question_gen_service._validate_document_for_page_ops(doc)
    pages = get_pages_by_numbers(db, doc, page_numbers)
    near_pages, allowed_range = build_near_page_context(db, doc, page_numbers)
    tag_hint = question_gen_service._format_tag_hint(
        question_gen_service._existing_tag_names(db, user_id, document_id=doc.id),
        _document_tcn_domain(doc),
    )

    job = QgenJob(
        user_id=user_id,
        document_id=doc.id,
        mode="generate",
        status=STATUS_QUEUED,
        goal_text=_active_goal_text(db, user_id),
        tag_hint=tag_hint,
        tcn_domain=_document_tcn_domain(doc),
        questions_per_page=persist_questions_per_page(questions_per_page),
    )
    db.add(job)
    db.flush()

    allowed_list = sorted(allowed_range)
    near_blob = _serialize_near_pages(near_pages)
    for page in pages:
        num = int(page["page_number"])
        db.add(
            QgenJobPage(
                job_id=job.id,
                page_number=num,
                title=page.get("title") or f"第 {num} 页",
                content=page.get("content") or "",
                near_pages_json=near_blob,
                allowed_page_numbers_json=allowed_list,
                segment_id=page.get("segment_id"),
                status=STATUS_QUEUED,
            )
        )

    doc.question_gen_status = "processing"
    db.flush()
    return PageQuestionResponse(
        document_id=doc.id,
        page_numbers=page_numbers,
        mode="generate",
        question_gen_status="processing",
        questions_created=0,
        questions_reused=0,
        total_questions=0,
        job_id=job.id,
    )


def claim_next_job(db: Session) -> Optional[dict[str, Any]]:
    running_user_ids = [
        row[0]
        for row in db.query(QgenJob.user_id)
        .filter(QgenJob.status == STATUS_RUNNING)
        .distinct()
        .all()
    ]
    query = db.query(QgenJob).filter(QgenJob.status == STATUS_QUEUED)
    if running_user_ids:
        query = query.filter(~QgenJob.user_id.in_(running_user_ids))
    job = (
        query.order_by(QgenJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        return None
    job.status = STATUS_RUNNING
    job.started_at = datetime.utcnow()
    db.flush()
    job = (
        db.query(QgenJob)
        .options(joinedload(QgenJob.pages))
        .filter(QgenJob.id == job.id)
        .one()
    )
    return job_to_worker_payload(job)


def _get_job_page(db: Session, job_id: str, page_number: int) -> tuple[QgenJob, QgenJobPage]:
    job = (
        db.query(QgenJob)
        .options(joinedload(QgenJob.pages))
        .filter(QgenJob.id == job_id)
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="出题任务不存在")
    page = next((p for p in job.pages if p.page_number == page_number), None)
    if page is None:
        raise HTTPException(status_code=404, detail=f"页码不在任务中: {page_number}")
    return job, page


def mark_page_progress(db: Session, job_id: str, page_number: int) -> dict[str, Any]:
    job, page = _get_job_page(db, job_id, page_number)
    if job.status == STATUS_QUEUED:
        job.status = STATUS_RUNNING
        job.started_at = job.started_at or datetime.utcnow()
    if page.status in (STATUS_COMPLETED, STATUS_FAILED):
        return job_to_worker_payload(job)
    page.status = STATUS_RUNNING
    db.flush()
    return job_to_worker_payload(job)


def _refresh_job_status(job: QgenJob) -> None:
    statuses = [p.status for p in job.pages]
    if any(s in (STATUS_QUEUED, STATUS_RUNNING) for s in statuses):
        job.status = STATUS_RUNNING
        job.finished_at = None
        return
    job.finished_at = datetime.utcnow()
    if any(s == STATUS_COMPLETED for s in statuses):
        job.status = STATUS_COMPLETED
    else:
        job.status = STATUS_FAILED


def complete_page(
    db: Session,
    job_id: str,
    page_number: int,
    questions: list[dict],
    usage: Optional[dict] = None,
) -> dict[str, Any]:
    from app.services.quiz.question_gen_service import _persist_question_from_page

    job, page = _get_job_page(db, job_id, page_number)
    if page.status == STATUS_COMPLETED:
        return {
            "job_id": job.id,
            "page_number": page_number,
            "status": page.status,
            "questions_created": 0,
            "questions_reused": 0,
            "total_questions": 0,
        }

    doc = kb_crud.get_document_by_id_internal(db, job.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    normalized: list[dict] = []
    domain = getattr(doc, "tcn_domain", None)
    for raw in questions:
        item = normalize_question(raw) if isinstance(raw, dict) else None
        if item:
            normalized.append(item)
    from app.qgen.tcn_tags import keep_questions_with_legal_tags

    normalized = keep_questions_with_legal_tags(normalized, domain)
    if not normalized:
        return fail_page(db, job_id, page_number, "无有效结构化题目")

    created = 0
    reused = 0
    page_dict = {
        "page_number": page.page_number,
        "title": page.title,
        "content": page.content,
        "segment_id": page.segment_id,
    }
    for qdata in normalized:
        was_created, was_reused = _persist_question_from_page(
            db,
            user_id=job.user_id,
            document=doc,
            page=page_dict,
            qdata=qdata,
            source_type="generated",
        )
        if was_created:
            created += 1
        if was_reused:
            reused += 1

    page.status = STATUS_COMPLETED
    page.questions_json = normalized
    page.usage_json = usage
    page.error = None
    _refresh_job_status(job)
    if job.status == STATUS_COMPLETED:
        doc.question_gen_status = "completed"
    db.flush()
    return {
        "job_id": job.id,
        "page_number": page_number,
        "status": page.status,
        "job_status": job.status,
        "questions_created": created,
        "questions_reused": reused,
        "total_questions": created + reused,
    }


def fail_page(
    db: Session, job_id: str, page_number: int, error: str
) -> dict[str, Any]:
    job, page = _get_job_page(db, job_id, page_number)
    page.status = STATUS_FAILED
    page.error = (error or "出题失败")[:500]
    _refresh_job_status(job)
    doc = kb_crud.get_document_by_id_internal(db, job.document_id)
    if doc is not None and job.status == STATUS_FAILED:
        doc.question_gen_status = "failed"
    db.flush()
    return {
        "job_id": job.id,
        "page_number": page_number,
        "status": page.status,
        "job_status": job.status,
        "error": page.error,
        "questions_created": 0,
        "questions_reused": 0,
        "total_questions": 0,
    }


def get_job_for_user(db: Session, user_id: int, job_id: str) -> dict[str, Any]:
    job = (
        db.query(QgenJob)
        .options(joinedload(QgenJob.pages))
        .filter(QgenJob.id == job_id)
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="出题任务不存在")
    return job_to_public(job, user_id=user_id)
