from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, func
from app.core.database import Base
from datetime import datetime


class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(String(500), nullable=False)
    attributes = Column(JSON, nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, server_default="active", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
