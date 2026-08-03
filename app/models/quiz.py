import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class GlobalQuestion(Base):
    __tablename__ = "global_questions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    content_hash = Column(String(64), unique=True, nullable=False)
    stem = Column(Text, nullable=False)
    question_type = Column(String(20), nullable=False)
    options = Column(Text, nullable=True)
    answer = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)
    source_type = Column(String(20), nullable=False)
    difficulty = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    provenance = relationship("QuestionProvenance", back_populates="question")
    user_refs = relationship("UserQuestionRef", back_populates="question")
    session_questions = relationship("QuizSessionQuestion", back_populates="question")
    quiz_answers = relationship("QuizAnswer", back_populates="question")
    tutor_sessions = relationship("TutorSession", back_populates="question")


class QuestionProvenance(Base):
    __tablename__ = "question_provenance"
    __table_args__ = (
        Index("ix_question_provenance_question", "question_id"),
        Index("ix_question_provenance_segment", "segment_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question_id = Column(String(36), ForeignKey("global_questions.id"), nullable=False, index=True)
    global_document_id = Column(String(36), ForeignKey("global_documents.id"), nullable=True)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=True)
    segment_id = Column(String(36), ForeignKey("document_segments.id"), nullable=True)
    excerpt = Column(Text, nullable=True)

    question = relationship("GlobalQuestion", back_populates="provenance")
    global_document = relationship("GlobalDocument", back_populates="question_provenance")
    segment = relationship("DocumentSegment", back_populates="question_provenance")


class UserQuestionRef(Base):
    __tablename__ = "user_question_refs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "question_id", "document_id", name="uq_user_question_refs_user_q_doc"
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question_id = Column(String(36), ForeignKey("global_questions.id"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    segment_id = Column(String(36), ForeignKey("document_segments.id"), nullable=True)
    collection_id = Column(String(36), ForeignKey("kb_collections.id"), nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="question_refs")
    question = relationship("GlobalQuestion", back_populates="user_refs")
