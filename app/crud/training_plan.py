import json
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.training_plan import TrainingPlan


def create_training_plan(
    db: Session,
    *,
    user_id: int,
    quiz_session_id: str,
    agent_session_id: str,
    question_ids: List[str],
    weak_tags: List[str],
    rationale: Optional[str] = None,
    report_id: Optional[str] = None,
) -> TrainingPlan:
    row = TrainingPlan(
        user_id=user_id,
        quiz_session_id=quiz_session_id,
        agent_session_id=agent_session_id,
        question_ids_json=json.dumps(question_ids, ensure_ascii=False),
        weak_tags_json=json.dumps(weak_tags, ensure_ascii=False),
        rationale=rationale,
        report_id=report_id,
    )
    db.add(row)
    db.flush()
    return row


def get_by_agent_session(
    db: Session, user_id: int, agent_session_id: str
) -> Optional[TrainingPlan]:
    return (
        db.query(TrainingPlan)
        .filter(
            TrainingPlan.user_id == user_id,
            TrainingPlan.agent_session_id == agent_session_id,
        )
        .first()
    )


def get_by_quiz_session(
    db: Session, user_id: int, quiz_session_id: str
) -> Optional[TrainingPlan]:
    return (
        db.query(TrainingPlan)
        .filter(
            TrainingPlan.user_id == user_id,
            TrainingPlan.quiz_session_id == quiz_session_id,
        )
        .first()
    )


def get_active_by_report(
    db: Session, user_id: int, report_id: str
) -> Optional[TrainingPlan]:
    from app.models.quiz_session import QuizSession

    return (
        db.query(TrainingPlan)
        .join(QuizSession, TrainingPlan.quiz_session_id == QuizSession.id)
        .filter(
            TrainingPlan.user_id == user_id,
            TrainingPlan.report_id == report_id,
            QuizSession.status == "active",
        )
        .order_by(TrainingPlan.created_at.desc())
        .first()
    )
