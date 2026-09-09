"""
刷题会话 API — 创建、答题、判分、错题汇总
"""
import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.crud import quiz as quiz_crud
from app.schemas.quiz import (
    AnswerResult,
    AnswerSubmit,
    QuizResultsOut,
    QuizSessionCreate,
    QuizSessionOut,
)
from app.services.quiz import quiz_service
from app.services.tasks import task_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["刷题"])


@router.post(
    "/sessions",
    response_model=QuizSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: QuizSessionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """从 document_id / collection_id / question_ids 创建刷题会话。"""
    result = quiz_service.create_quiz_session(
        db=db, user_id=current_user["user_id"], payload=payload
    )
    db.commit()
    return result


@router.get("/sessions/{session_id}", response_model=QuizSessionOut)
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """获取会话题序与答题进度（不含标准答案）。"""
    return quiz_service.get_quiz_session(
        db=db, user_id=current_user["user_id"], session_id=session_id
    )


@router.post("/sessions/{session_id}/answers", response_model=AnswerResult)
async def submit_answer(
    session_id: str,
    payload: AnswerSubmit,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """提交单题答案；status=unknown 表示「我不会」。"""
    result = await quiz_service.submit_answer(
        db=db,
        user_id=current_user["user_id"],
        session_id=session_id,
        question_id=payload.question_id,
        user_answer=payload.user_answer,
        status_hint=payload.status,
        time_spent_seconds=payload.time_spent_seconds,
    )
    db.commit()
    try:
        from app.services.tcn.quiz_hook import schedule_quiz_predict

        session = quiz_crud.get_session(db, session_id, current_user["user_id"])
        schedule_quiz_predict(
            db,
            user_hash=current_user.get("user_hash"),
            document_id=session.document_id if session else None,
            question_id=payload.question_id,
            result_status=result.status,
            session_id=session_id,
        )
    except Exception:
        logger.warning("调度 TCN predict 失败，交卷不受影响", exc_info=True)
    # 检查器：任务范围内交够约定道数（含「不会」）→ 今日刷题任务自动完成
    result.completed_tasks = task_service.run_completion_checks(
        db,
        current_user["user_id"],
        "answer_submitted",
        {"session_id": session_id},
    )
    return result


@router.get("/sessions/{session_id}/results", response_model=QuizResultsOut)
def get_results(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """汇总错题与 unknown 题目，含 provenance 原文定位。"""
    return quiz_service.get_session_results(
        db=db, user_id=current_user["user_id"], session_id=session_id
    )
