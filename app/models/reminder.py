"""提醒（Issue #5.X）。

前端 ``/reminders`` 之前走本地 demo store，本表 + CRUD 上线后由前端切到真实接口。
调度触发（到点提醒）由后台 worker 处理（本 PR 不做，只暴露 CRUD + 列表/查询）。
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func

from app.core.database import Base


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        Index("ix_reminders_user_id", "user_id"),
        Index("ix_reminders_user_trigger", "user_id", "trigger_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    # 触发时间（绝对时刻）；调度 worker 到了就把 reminder 触发
    trigger_at = Column(DateTime(timezone=True), nullable=False)
    # 可选：none / daily / weekly / monthly（具体语义由调度 worker 决定）
    repeat_rule = Column(String(32), nullable=True)
    enabled = Column(Boolean, server_default="true", nullable=False)
    # active / triggered / cancelled
    status = Column(String(20), server_default="active", nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )