"""今日任务 API（Issue #19 + #30/#31 生产契约修订）。

- GET  /api/v1/tasks/today    → 展示当天任务（pending 在前，一主两候选）
- POST /api/v1/tasks/today/ensure → 当天没有未完成任务则按缺口生成；有则直接返回

不做「勾选完成」接口；完成只能由检查器挂在成功路径后面判定。

#30 契约：顶层 `{ date, primary, candidates, tasks, completed_tasks }`；
primary = 第一条 pending（空则 null），candidates = 其余 pending 中最多 2 条；
每条任务含 reason_short / href / evidence，key 不省略。
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.schemas.task import DailyTaskOut, TaskCompletedOut, TodayTasksOut
from app.services.tasks import task_service

router = APIRouter(tags=["今日任务"])

# 每类任务的跳转链接（Web 不用它跳转，但 DTO 保持完整避免客户端各写一套）
_HREF_BY_TYPE = {
    "upload": "/library",
    "generate_questions": "/generate",
    "practice": "/practice",
}


def _build_href(task_type: str, payload: dict) -> Optional[str]:
    base = _HREF_BY_TYPE.get(task_type)
    if not base:
        return None
    doc_id = (payload or {}).get("document_id")
    if task_type == "generate_questions" and doc_id:
        pages = (payload or {}).get("page_numbers") or []
        pages_param = ",".join(str(p) for p in pages)
        query = f"doc_id={doc_id}"
        if pages_param:
            query += f"&pages={pages_param}"
        return f"{base}?{query}"
    return base


def _reason_short(reason: Optional[str], limit: int = 40) -> Optional[str]:
    if not reason:
        return None
    reason = reason.strip()
    return reason if len(reason) <= limit else reason[: limit - 1] + "…"


def _task_out(t) -> DailyTaskOut:
    out = DailyTaskOut.model_validate(t)
    out.href = _build_href(t.task_type, t.payload)
    out.reason_short = _reason_short(t.reason)
    out.evidence = t.evidence_json if t.status == "completed" else None
    return out


def _today_out(db: Session, user_id: int) -> TodayTasksOut:
    tasks = task_service.list_today(db, user_id)
    outs = [_task_out(t) for t in tasks]
    pending = [o for o in outs if o.status == "pending"]
    completed_ids = {o.id for o in outs if o.status == "completed"}
    receipts = task_service.list_completed_receipts(db, user_id, task_service.today_local())
    receipts = [r for r in receipts if r["id"] in completed_ids]
    return TodayTasksOut(
        date=task_service.today_local(),
        primary=pending[0] if pending else None,
        candidates=pending[1:3],
        tasks=outs,
        completed_tasks=[TaskCompletedOut(**r) for r in receipts],
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
