"""今日任务 API（Issue #19）。

- GET  /api/v1/tasks/today    → 展示当天任务（pending 在前）
- POST /api/v1/tasks/today/ensure → 当天没有未完成任务则按缺口生成；有则直接返回

不做「勾选完成」接口；完成只能由检查器挂在成功路径后面判定。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.schemas.task import DailyTaskOut, TodayTasksOut
from app.services.tasks import task_service

router = APIRouter(tags=["今日任务"])


def _today_out(db: Session, user_id: int) -> TodayTasksOut:
    tasks = task_service.list_today(db, user_id)
    return TodayTasksOut(
        date=task_service.today_local(),
        tasks=[DailyTaskOut.model_validate(t) for t in tasks],
    )


@router.get("/today", response_model=TodayTasksOut)
def get_today_tasks(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """展示当天任务（不生成；当天没有任务时返回空列表）。"""
    return _today_out(db, current_user["user_id"])


@router.post("/today/ensure", response_model=TodayTasksOut)
def ensure_today_tasks(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """确保当天有任务：没有未完成的则按缺口生成（没书→上传；有书没题→出题；有题→刷题）。

    有未完成的先展示，不重复派。
    """
    user_id = current_user["user_id"]
    task_service.ensure_today_tasks(db, user_id)
    return _today_out(db, user_id)
