"""目标证据变化事件（Issue #38 Evidence Impact 独立契约）。

不复用 daily_tasks.evidence_json 冒充证据变化；本表记录「目标维度」的前后值变化，
供目标详情「证据变化」页消费：
    { id, goal_id, occurred_at, source, node_id, node_label,
      before, after, scope, confirmation }
"""
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    func,
)

from app.core.database import Base


class GoalEvidenceEvent(Base):
    __tablename__ = "goal_evidence_events"
    __table_args__ = (
        Index("ix_goal_evidence_goal_time", "goal_id", "occurred_at"),
        Index("ix_goal_evidence_user", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(__import__("uuid").uuid4()))
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    goal_id = Column(
        Integer,
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    occurred_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # upload | generate_questions | answer_submitted | profile | ...
    source = Column(String(50), nullable=False)
    # 判断/画像节点（可空）
    node_id = Column(String(100), nullable=True)
    node_label = Column(String(255), nullable=True)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    # 影响范围，如 "goal" / "mastery:<doc_id>" / "task"
    scope = Column(String(120), nullable=False, server_default="goal")
    # pending | confirmed | rejected
    confirmation = Column(String(20), nullable=False, server_default="pending")
