"""今日任务相关 schema（Issue #19 + #30/#31 生产契约修订）。

- `DailyTaskOut`：任务完整结构（GET /tasks/today 列表项），含 href / reason_short / evidence
- `TaskCompletedOut`：完成回执（CompletionReceipt）：idempotency_key / source_action /
  before_status / after_status / evidence，动作响应与 today 快照共用同一形状
- `TodayTasksOut`：GET/POST /tasks/today 的响应，一主两候选
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class TaskCompletedOut(BaseModel):
    """完成回执：前端弹窗「该任务已经完成！」并消费证据。"""

    id: int
    title: str
    idempotency_key: Optional[str] = None
    source_action: Optional[str] = None
    before_status: Optional[str] = None
    after_status: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None


class DailyTaskOut(BaseModel):
    id: int
    goal_id: Optional[int] = None
    task_date: date
    title: str
    reason: Optional[str] = None
    # 面向卡片的一句话理由（reason 截断），客户端直接展示
    reason_short: Optional[str] = None
    task_type: str
    payload: Optional[dict] = None
    completion_rule: Optional[dict] = None
    status: str
    # 按 task_type 生成的跳转链接（/library /generate /practice）
    href: Optional[str] = None
    # 完成证据（daily_tasks.evidence_json）；未完成为 null
    evidence: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TodayTasksOut(BaseModel):
    date: date
    # 一主两候选：第一条 pending；没有 pending 明确为 null（key 不省略）
    primary: Optional[DailyTaskOut] = None
    candidates: List[DailyTaskOut] = []
    # 当天全部任务（兼容旧字段，pending 在前）
    tasks: List[DailyTaskOut] = []
    # 当天完成回执（刷新后弹窗证据仍在）
    completed_tasks: List[TaskCompletedOut] = []
