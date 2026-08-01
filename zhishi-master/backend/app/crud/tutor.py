from typing import Optional

from sqlalchemy.orm import Session

from app.models import TutorSession


def create_session(
    db: Session,
    *,
    user_id: int,
    question_id: str,
    document_id: str,
    segment_id: str,
    chat_session_id: str,
    quiz_answer_id: Optional[str] = None,
) -> TutorSession:
    row = TutorSession(
        user_id=user_id,
        question_id=question_id,
        document_id=document_id,
        segment_id=segment_id,
        quiz_answer_id=quiz_answer_id,
        chat_session_id=chat_session_id,
        status="active",
    )
    db.add(row)
    db.flush()
    return row


def get_session(
    db: Session, session_id: str, user_id: int
) -> Optional[TutorSession]:
    return (
        db.query(TutorSession)
        .filter(TutorSession.id == session_id, TutorSession.user_id == user_id)
        .first()
    )
