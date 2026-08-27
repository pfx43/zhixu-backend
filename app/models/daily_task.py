"""今日任务模型（Issue #19）。

用户不能勾选完成；由检查器挂在「上传 / 按页出题 / 交卷」成功路径后自动判定。
字段与 Goal（#15）风格对齐；user_id 删号级联（ondelete=CASCADE）。
"""
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    func,
)

from app.core.database import Base


class DailyTask(Base):
    __tablename__ = "daily_tasks"
    __table_args__ = (
        Index("ix_daily_tasks_user_date", "user_id", "task_date"),
        Index("ix_daily_tasks_user_status", "user_id", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 属于哪个用户；删号时级联删除
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 推进哪条目标（可空：没目标也能派任务）；目标被删时置空
    goal_id = Column(
        Integer,
        ForeignKey("goals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 哪一天（本地日期）
    task_date = Column(Date, nullable=False, index=True)
    # 标题 / 理由（Tina 第三期写人话；本期程序生成）
    title = Column(String(255), nullable=False)
    reason = Column(String(1000), nullable=True)
    # 任务类型：upload | generate_questions | practice
    task_type = Column(String(32), nullable=False, index=True)
    # 任务上下文：书 id、页码、道数等（页码只来自目录 / 解析页，禁止模型手填）
    payload = Column(JSON, nullable=True)
    # 怎样算完成（程序定，模型不发明规则）
    completion_rule = Column(JSON, nullable=True)
    # 状态：pending | completed（无勾选完成接口，只能由检查器翻转）
    status = Column(String(20), nullable=False, server_default="pending", index=True)
    # 完成证据（Issue #31/#38：检查器翻转时写入；注意目标详情「证据变化」用
    # goal_evidence_events，不复用本字段冒充）
    evidence_json = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
