"""
刷题会话 API — 创建、答题、判分、错题汇总
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.schemas.quiz import (
    AnswerResult,
    AnswerSubmit,
    QuizResultsOut,
    QuizSessionCreate,
    QuizSessionOut,
)
from app.services.quiz import quiz_service

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
def submit_answer(
    session_id: str,
    payload: AnswerSubmit,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """提交单题答案；status=unknown 表示「我不会」。"""
    result = quiz_service.submit_answer(
        db=db,
        user_id=current_user["user_id"],
        session_id=session_id,
        question_id=payload.question_id,
        user_answer=payload.user_answer,
        status_hint=payload.status,
        time_spent_seconds=payload.time_spent_seconds,
    )
    db.commit()
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
