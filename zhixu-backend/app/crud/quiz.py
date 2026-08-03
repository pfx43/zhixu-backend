from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import GlobalQuestion, QuizAnswer, QuizSession, QuizSessionQuestion


def create_session(
    db: Session,
    *,
    user_id: int,
    document_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    title: Optional[str] = None,
) -> QuizSession:
    row = QuizSession(
        user_id=user_id,
        document_id=document_id,
        collection_id=collection_id,
        title=title,
        status="active",
    )
    db.add(row)
    db.flush()
    return row


def add_session_questions(
    db: Session, session_id: str, question_ids: List[str]
) -> List[QuizSessionQuestion]:
    rows: List[QuizSessionQuestion] = []
    for idx, qid in enumerate(question_ids):
        row = QuizSessionQuestion(
            session_id=session_id,
            question_id=qid,
            order_index=idx,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def get_session(
    db: Session, session_id: str, user_id: int
) -> Optional[QuizSession]:
    return (
        db.query(QuizSession)
        .filter(QuizSession.id == session_id, QuizSession.user_id == user_id)
        .first()
    )


def list_session_questions(
    db: Session, session_id: str
) -> List[Tuple[QuizSessionQuestion, GlobalQuestion]]:
    return (
        db.query(QuizSessionQuestion, GlobalQuestion)
        .join(GlobalQuestion, QuizSessionQuestion.question_id == GlobalQuestion.id)
        .filter(QuizSessionQuestion.session_id == session_id)
        .order_by(QuizSessionQuestion.order_index.asc())
        .all()
    )


def get_session_question(
    db: Session, session_id: str, question_id: str
) -> Optional[QuizSessionQuestion]:
    return (
        db.query(QuizSessionQuestion)
        .filter(
            QuizSessionQuestion.session_id == session_id,
            QuizSessionQuestion.question_id == question_id,
        )
        .first()
    )


def get_answer(
    db: Session, session_id: str, question_id: str
) -> Optional[QuizAnswer]:
    return (
        db.query(QuizAnswer)
        .filter(
            QuizAnswer.session_id == session_id,
            QuizAnswer.question_id == question_id,
        )
        .first()
    )


def upsert_answer(
    db: Session,
    *,
    session_id: str,
    question_id: str,
    user_id: int,
    user_answer: Optional[str],
    status: str,
    time_spent_seconds: Optional[int] = None,
) -> QuizAnswer:
    existing = get_answer(db, session_id, question_id)
    if existing:
        existing.user_answer = user_answer
        existing.status = status
        existing.answered_at = datetime.now(timezone.utc)
        existing.time_spent_seconds = time_spent_seconds
        db.flush()
        return existing

    row = QuizAnswer(
        session_id=session_id,
        question_id=question_id,
        user_id=user_id,
        user_answer=user_answer,
        status=status,
        time_spent_seconds=time_spent_seconds,
    )
    db.add(row)
    db.flush()
    return row


def list_answers_for_session(db: Session, session_id: str) -> List[QuizAnswer]:
    return (
        db.query(QuizAnswer)
        .filter(QuizAnswer.session_id == session_id)
        .order_by(QuizAnswer.answered_at.asc())
        .all()
    )


def count_answers(db: Session, session_id: str) -> int:
    return (
        db.query(QuizAnswer)
        .filter(QuizAnswer.session_id == session_id)
        .count()
    )


def complete_session(db: Session, session: QuizSession) -> QuizSession:
    session.status = "completed"
    session.finished_at = datetime.now(timezone.utc)
    db.flush()
    return session


def count_session_questions(db: Session, session_id: str) -> int:
    return (
        db.query(QuizSessionQuestion)
        .filter(QuizSessionQuestion.session_id == session_id)
        .count()
    )


def list_recent_sessions(
    db: Session, user_id: int, limit: int = 5
) -> List[QuizSession]:
    return (
        db.query(QuizSession)
        .filter(QuizSession.user_id == user_id)
        .order_by(QuizSession.started_at.desc())
        .limit(limit)
        .all()
    )


def list_recent_answers(
    db: Session, user_id: int, limit: int = 10
) -> List[Tuple[QuizAnswer, GlobalQuestion, QuizSession]]:
    return (
        db.query(QuizAnswer, GlobalQuestion, QuizSession)
        .join(GlobalQuestion, QuizAnswer.question_id == GlobalQuestion.id)
        .join(QuizSession, QuizAnswer.session_id == QuizSession.id)
        .filter(QuizAnswer.user_id == user_id)
        .order_by(QuizAnswer.answered_at.desc())
        .limit(limit)
        .all()
    )


def get_user_answer_stats_for_questions(
    db: Session, user_id: int, question_ids: List[str]
) -> Dict[str, Tuple[Optional[str], int]]:
    """Return question_id -> (latest_status, attempt_count) for the user."""
    if not question_ids:
        return {}

    attempt_rows = (
        db.query(QuizAnswer.question_id, func.count(QuizAnswer.id))
        .filter(
            QuizAnswer.user_id == user_id,
            QuizAnswer.question_id.in_(question_ids),
        )
        .group_by(QuizAnswer.question_id)
        .all()
    )
    attempt_map = {qid: int(cnt) for qid, cnt in attempt_rows}

    latest_subq = (
        db.query(
            QuizAnswer.question_id.label("question_id"),
            func.max(QuizAnswer.answered_at).label("max_answered_at"),
        )
        .filter(
            QuizAnswer.user_id == user_id,
            QuizAnswer.question_id.in_(question_ids),
        )
        .group_by(QuizAnswer.question_id)
        .subquery()
    )
    latest_rows = (
        db.query(QuizAnswer.question_id, QuizAnswer.status)
        .join(
            latest_subq,
            (QuizAnswer.question_id == latest_subq.c.question_id)
            & (QuizAnswer.answered_at == latest_subq.c.max_answered_at),
        )
        .filter(QuizAnswer.user_id == user_id)
        .all()
    )
    latest_map = {qid: status for qid, status in latest_rows}

    return {
        qid: (latest_map.get(qid), attempt_map.get(qid, 0))
        for qid in question_ids
    }
