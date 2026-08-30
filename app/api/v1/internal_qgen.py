"""出题服务回调主程序：claim / progress / complete / fail。不对浏览器开放。"""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_internal_key
from app.models.qgen import QgenJob
from app.services.quiz import qgen_job_service
from app.services.tasks import task_service

router = APIRouter()


class CompletePageBody(BaseModel):
    questions: List[dict] = Field(default_factory=list)
    usage: Optional[dict] = None


class FailPageBody(BaseModel):
    error: str = "出题失败"


@router.post("/claim")
def claim_job(
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    payload = qgen_job_service.claim_next_job(db)
    db.commit()
    if payload is None:
        return {"job": None}
    return {"job": payload}


@router.post("/jobs/{job_id}/pages/{page_number}/progress")
def page_progress(
    job_id: str,
    page_number: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    result = qgen_job_service.mark_page_progress(db, job_id, page_number)
    db.commit()
    return result


@router.post("/jobs/{job_id}/pages/{page_number}/complete")
def page_complete(
    job_id: str,
    page_number: int,
    payload: CompletePageBody,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    result = qgen_job_service.complete_page(
        db, job_id, page_number, payload.questions, usage=payload.usage
    )
    job = db.query(QgenJob).filter(QgenJob.id == job_id).first()
    if job is not None:
        result["completed_tasks"] = task_service.run_completion_checks(
            db, job.user_id, "questions_generated"
        )
    db.commit()
    return result


@router.post("/jobs/{job_id}/pages/{page_number}/fail")
def page_fail(
    job_id: str,
    page_number: int,
    payload: FailPageBody,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    result = qgen_job_service.fail_page(db, job_id, page_number, payload.error)
    db.commit()
    return result
