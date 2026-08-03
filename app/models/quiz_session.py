import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    collection_id = Column(String(36), ForeignKey("kb_collections.id"), nullable=True)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=True)
    title = Column(String(200), nullable=True)
    status = Column(String(20), default="active")
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="quiz_sessions")
    session_questions = relationship("QuizSessionQuestion", back_populates="session")
    answers = relationship("QuizAnswer", back_populates="session")


class QuizSessionQuestion(Base):
    __tablename__ = "quiz_session_questions"
    __table_args__ = (
        UniqueConstraint("session_id", "order_index", name="uq_quiz_session_questions_session_order"),
    )

    session_id = Column(String(36), ForeignKey("quiz_sessions.id"), primary_key=True)
    question_id = Column(String(36), ForeignKey("global_questions.id"), primary_key=True)
    order_index = Column(Integer, nullable=False)

    session = relationship("QuizSession", back_populates="session_questions")
    question = relationship("GlobalQuestion", back_populates="session_questions")


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_quiz_answers_session_question"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("quiz_sessions.id"), nullable=False, index=True)
    question_id = Column(String(36), ForeignKey("global_questions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_answer = Column(Text, nullable=True)
    status = Column(String(20), nullable=False)
    answered_at = Column(DateTime, default=datetime.utcnow)
    time_spent_seconds = Column(Integer, nullable=True)

    session = relationship("QuizSession", back_populates="answers")
    question = relationship("GlobalQuestion", back_populates="quiz_answers")
    user = relationship("User", back_populates="quiz_answers")
