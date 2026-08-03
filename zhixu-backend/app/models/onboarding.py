from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, UniqueConstraint, JSON
from app.core.database import Base


class OnboardingState(Base):
    __tablename__ = "onboarding_state"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, unique=True)
    guide_version = Column(Integer, nullable=False, server_default="1")
    revision = Column(Integer, nullable=False, server_default="0")
    status = Column(String(32), nullable=False, server_default="pending")  # pending/in_progress/completed/skipped
    current_step = Column(String(32), nullable=True)  # channel/upload/profile/tags/help
    steps = Column(JSON, nullable=True)
    channel_answer = Column(JSON, nullable=True)
    profile_answer = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", name="uq_onboarding_user"),)
