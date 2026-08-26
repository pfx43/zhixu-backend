"""服务端通知（Issue #5.X）。

前端顶栏入口被 ``isNotificationsApiPublished=false`` 关掉；
本表 + 接口上线后由前端发布。

- notifications：服务端推送给用户的通知；读取走 API，不走 demo store
- 软读（read_at）；当前实现为「服务端写 + 客户端读 + mark read」，
  推送本身由服务端任务在合适时机写入（本 PR 不做推送调度）
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_user_read", "user_id", "read_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # 通知类别：task_completed / tip_saved / reminder_due / goal_progress …
    kind = Column(String(32), nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    payload_json = Column(JSONB, nullable=True)
    # NULL 表示未读；服务端写入时为 NULL，mark read 时填时间
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )