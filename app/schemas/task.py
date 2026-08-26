"""今日任务 + 完成回执 schema（Issue #19 + #5.X）。

- ``TaskCompletedOut``：上传/出题/交卷响应里的 ``completed_tasks`` 项；本期按
  组长口径扩展为**完成回执**：含 idempotency_key（防双发弹窗）、source_action、
  before/after_status、evidence（来源证据）。前端弹层 + 详情复用同一份。
- ``DailyTaskOut``：任务完整结构，加 ``href``（前端跳转 + 任务跳转预勾选
  ``?from=tina``）与 ``reason_short``（卡片用）。
- ``TodayTasksOut``：GET/POST /tasks/today 的响应；含 ``primary``（一主）
  + ``candidates``（两候选）字段以解 TodayTaskBoard 的一主两候选展示。
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TaskCompletedOut(BaseModel):
    """完成回执（= Issue #5.X CompletionReceipt）。

    ``idempotency_key`` 用于前端去重弹窗；``source_action`` 指明本次完成
    来自哪个学习动作；``evidence`` 字段保留证据（document_id/session_id/
    question_ids/page_numbers 等），用于 Evidence Impact 详情展示。
    """

    id: int
    title: str
    idempotency_key: str
    completed_at: datetime
    source_action: str  # upload | generate_questions | answer_submitted
    before_status: str
    after_status: str
    evidence: Optional[Dict[str, Any]] = None


class DailyTaskOut(BaseModel):
    id: int
    goal_id: Optional[int] = None
    task_date: date
    title: str
    reason: Optional[str] = None
    # 卡片展示用的精简理由（reason 截断 80 字）
    reason_short: Optional[str] = None
    task_type: str
    payload: Optional[Dict[str, Any]] = None
    completion_rule: Optional[Dict[str, Any]] = None
    status: str
    # 前端跳转路径（按 task_type 生成：upload→资料库、generate→出题页?from=tina、
    # practice→刷题页?session=...）；调用方也可在 payload 里覆盖 href
    href: Optional[str] = None
    # Evidence Impact（Issue #5.X）：完成时的证据；本期未完成判定的任务为 null
    evidence: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TodayTasksOut(BaseModel):
    date: date
    # 一主（前端 TodayTaskBoard 主推那一件）：当天最该做的那件
    primary: Optional[DailyTaskOut] = None
    # 两候选：当天其它未完成任务（最多 2 件；与 primary 加起来 ≤3 件）
    candidates: List[DailyTaskOut] = []
    # 兼容旧字段：仍返回全部当天任务，便于现有前端直接读
    tasks: List[DailyTaskOut] = []
    completed_tasks: List[TaskCompletedOut] = []