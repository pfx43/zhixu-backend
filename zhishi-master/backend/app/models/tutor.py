import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class TutorSession(Base):
    __tablename__ = "tutor_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question_id = Column(String(36), ForeignKey("global_questions.id"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    segment_id = Column(String(36), ForeignKey("document_segments.id"), nullable=False)
    quiz_answer_id = Column(String(36), ForeignKey("quiz_answers.id"), nullable=True)
    chat_session_id = Column(String(64), nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="tutor_sessions")
    question = relationship("GlobalQuestion", back_populates="tutor_sessions")
