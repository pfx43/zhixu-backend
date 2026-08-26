"""今日任务 API（Issue #19 + #5.X）。

- GET  /api/v1/tasks/today    → 展示当天任务（TodayTaskBoard 接入点）
- POST /api/v1/tasks/today/ensure → 当天没有未完成任务则按缺口生成；
  有则直接返回（不重复派）

返回按 Issue #5.X ``TodayTasksOut``：
- ``primary``：今天最该做的那件（TodayTaskBoard 主推）
- ``candidates``：其余待办（最多 2 件；与 primary 加起来 ≤3 件）
- ``tasks``：兼容旧字段（全部当天任务，便于现有前端直接读）
- ``completed_tasks``：#5.X 完成回执（与 #19 共用，含 idempotency_key / evidence）

不做「勾选完成」接口；完成只能由检查器挂在成功路径后面判定。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.schemas.task import DailyTaskOut, TodayTasksOut
from app.services.tasks import task_service

router = APIRouter(tags=["今日任务"])


def _task_to_out(t) -> DailyTaskOut:
    out = DailyTaskOut.model_validate(t)
    # Issue #5.X：reason 截断给卡片用；href 按 task_type 生成（任务跳转预勾选
    # ?from=tina 由前端在 task.payload 携带时附加）
    out.reason_short = (out.reason or "")[:80]
    out.href = _href_for(t)
    return out


def _href_for(t) -> str:
    """按 task_type 生成前端默认跳转路径；payload 里有 href 则由调用方覆盖。"""
    ttype = t.task_type
    if ttype == task_service.TYPE_UPLOAD:
        return "/library"
    if ttype == task_service.TYPE_GENERATE:
        doc_id = (t.payload or {}).get("document_id")
        pages = (t.payload or {}).get("page_numbers") or []
        qp = []
        if doc_id:
            qp.append(f"doc_id={doc_id}")
        if pages:
            qp.append(f"pages={','.join(map(str, pages))}")
        suffix = ("?" + "&".join(qp)) if qp else ""
        return f"/generate{suffix}"
    if ttype == task_service.TYPE_PRACTICE:
        return "/practice"
    return "/"


def _today_out(db: Session, user_id: int) -> TodayTasksOut:
    tasks = task_service.list_today(db, user_id)
    task_outs = [_task_to_out(t) for t in tasks]
    pending = [t for t in task_outs if t.status == "pending"]
    primary = pending[0] if pending else None
    candidates = pending[1:3]
    return TodayTasksOut(
        date=task_service.today_local(),
        primary=primary,
        candidates=candidates,
        tasks=task_outs,
        completed_tasks=[],
    )


@router.get("/today", response_model=TodayTasksOut)
def get_today_tasks(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """展示当天任务（TodayTaskBoard 接入点）。"""
    return _today_out(db, current_user["user_id"])


@router.post("/today/ensure", response_model=TodayTasksOut)
def ensure_today_tasks(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """确保当天有任务：没有未完成的则按缺口生成（没书→上传；有书没题→出题；
    有题→刷题）。有未完成的先展示，不重复派。

    缺口生成最多 3 件（upload / generate / practice 各 ≤1 件）以满足
    ``TodayTaskBoard`` 一主两候选的展示需求。
    """
    user_id = current_user["user_id"]
    task_service.ensure_today_tasks(db, user_id)
    return _today_out(db, user_id)