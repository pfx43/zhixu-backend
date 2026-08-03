import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class TrainingPlan(Base):
    __tablename__ = "training_plans"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    quiz_session_id = Column(String(36), ForeignKey("quiz_sessions.id"), nullable=False, index=True)
    agent_session_id = Column(String(36), nullable=False, unique=True, index=True)
    question_ids_json = Column(Text, nullable=False, default="[]")
    weak_tags_json = Column(Text, nullable=False, default="[]")
    rationale = Column(Text, nullable=True)
    report_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
