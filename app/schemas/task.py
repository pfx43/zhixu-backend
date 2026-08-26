"""今日任务相关 schema（Issue #19）。

- `DailyTaskOut`：任务完整结构（GET /tasks/today 列表项）
- `TaskCompletedOut`：检查器返回的完成项（挂在上传 / 出题 / 交卷响应里）
- `TodayTasksOut`：GET/POST /tasks/today 的响应
"""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class TaskCompletedOut(BaseModel):
    """已完成的任务（前端用于弹窗「该任务已经完成！」）。"""

    id: int
    title: str


class DailyTaskOut(BaseModel):
    id: int
    goal_id: Optional[int] = None
    task_date: date
    title: str
    reason: Optional[str] = None
    task_type: str
    payload: Optional[dict] = None
    completion_rule: Optional[dict] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TodayTasksOut(BaseModel):
    date: date
    tasks: List[DailyTaskOut] = []
    completed_tasks: List[TaskCompletedOut] = []
