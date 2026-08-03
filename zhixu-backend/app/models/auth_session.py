from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash = Column(String(64), primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)
