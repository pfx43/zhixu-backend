"""画像图谱 + 推断任务（Issue #5.X）。

前端 Profile 构建/图谱被 ``isProfileApiPublished=false`` 挡住；
本表 + 接口上线后由前端发布。

- profile_graphs：每个用户一张画像图谱（JSON 结构，节点是书/章/tag/能力点）
- profile_inferences：画像推断任务（手动 / 自动触发；status: pending/running/
  done/failed；result 写回 graph 或单独存）
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class ProfileGraph(Base):
    __tablename__ = "profile_graphs"
    __table_args__ = (Index("ix_profile_graphs_user_id", "user_id"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # 每个用户一张图谱；多版本时通过 version 区分
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    version = Column(Integer, server_default="1", nullable=False)
    # JSON 结构（节点 + 边 + 属性）；本 PR 仅做存储与读取，具体内容由推断任务决定
    graph_json = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ProfileInference(Base):
    __tablename__ = "profile_inferences"
    __table_args__ = (
        Index("ix_profile_inferences_user_id", "user_id"),
        Index("ix_profile_inferences_status", "status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # 关联图谱（图谱被删时置空）
    graph_id = Column(
        String(36), ForeignKey("profile_graphs.id", ondelete="SET NULL"), nullable=True
    )
    status = Column(String(20), server_default="pending", nullable=False)
    # manual / scheduled / on_event（谁触发的）
    trigger = Column(String(32), server_default="manual", nullable=False)
    result_json = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )