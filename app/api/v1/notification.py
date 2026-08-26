"""通知 / 提醒 / 画像 API（Issue #5.X）。

三个 feature 之前被前端 ``is*ApiPublished=false`` 挡掉；本 PR 上线后由前端
取消开关、接管对应 demo store / 顶栏入口。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.crud import notification as notif_crud
from app.crud import reminder as rem_crud
from app.crud import profile_graph as profile_crud
from app.models import Notification, ProfileGraph, ProfileInference, Reminder


# ── Schemas ────────────────────────────────────────────────


class NotificationOut(BaseModel):
    id: str
    kind: str
    title: str
    body: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UnreadCountOut(BaseModel):
    unread: int


class ReminderCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    body: Optional[str] = None
    trigger_at: datetime
    repeat_rule: Optional[str] = None  # none / daily / weekly / monthly
    enabled: bool = True


class ReminderUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    trigger_at: Optional[datetime] = None
    repeat_rule: Optional[str] = None
    enabled: Optional[bool] = None


class ReminderOut(BaseModel):
    id: str
    title: str
    body: Optional[str] = None
    trigger_at: datetime
    repeat_rule: Optional[str] = None
    enabled: bool
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ProfileGraphOut(BaseModel):
    id: str
    version: int
    graph: Optional[Dict[str, Any]] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class InferenceStartOut(BaseModel):
    id: str
    status: str
    trigger: str


class InferenceOut(BaseModel):
    id: str
    status: str
    trigger: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Notifications ──────────────────────────────────────────


notif_router = APIRouter(tags=["通知"])


@notif_router.get("", response_model=List[NotificationOut])
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """通知列表（当前用户，新的在前）"""
    return notif_crud.list_notifications(db, current_user["user_id"], limit=limit)


@notif_router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    return {"unread": notif_crud.count_unread(db, current_user["user_id"])}


@notif_router.post("/{notification_id}/read", status_code=status.HTTP_200_OK)
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    ok = notif_crud.mark_notification_read(db, current_user["user_id"], notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="通知不存在")
    db.commit()
    return {"id": notification_id, "read": True}


# ── Reminders ──────────────────────────────────────────────


reminder_router = APIRouter(tags=["提醒"])


@reminder_router.get("", response_model=List[ReminderOut])
def list_reminders(
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    return rem_crud.list_reminders(db, current_user["user_id"], limit=limit)


@reminder_router.post("", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
def create_reminder(
    payload: ReminderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    r = rem_crud.create_reminder(
        db,
        user_id=current_user["user_id"],
        title=payload.title,
        body=payload.body,
        trigger_at=payload.trigger_at,
        repeat_rule=payload.repeat_rule,
        enabled=payload.enabled,
    )
    db.commit()
    return r


@reminder_router.patch("/{reminder_id}", response_model=ReminderOut)
def update_reminder(
    reminder_id: str,
    payload: ReminderUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    r = rem_crud.update_reminder(
        db,
        current_user["user_id"],
        reminder_id,
        title=payload.title,
        body=payload.body,
        trigger_at=payload.trigger_at,
        repeat_rule=payload.repeat_rule,
        enabled=payload.enabled,
    )
    if not r:
        raise HTTPException(status_code=404, detail="提醒不存在")
    db.commit()
    return r


@reminder_router.delete("/{reminder_id}", status_code=status.HTTP_200_OK)
def delete_reminder(
    reminder_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    ok = rem_crud.delete_reminder(db, current_user["user_id"], reminder_id)
    if not ok:
        raise HTTPException(status_code=404, detail="提醒不存在")
    db.commit()
    return {"id": reminder_id, "deleted": True}


# ── Profile Graph / Inference ──────────────────────────────


profile_router = APIRouter(tags=["画像"])


@profile_router.get("/graph", response_model=ProfileGraphOut)
def get_profile_graph(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    g = profile_crud.get_or_create_graph(db, current_user["user_id"])
    db.commit()
    return ProfileGraphOut(
        id=g.id,
        version=g.version,
        graph=g.graph_json or None,
        updated_at=g.updated_at,
    )


@profile_router.post(
    "/inferences", response_model=InferenceStartOut, status_code=status.HTTP_201_CREATED
)
def start_inference(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """启动一次画像推断任务（手动）。具体推断工作由调度/事件处理触发
    （本 PR 不做）；后端先把任务写库并返回 inference_id，前端轮询结果。
    """
    g = profile_crud.get_or_create_graph(db, current_user["user_id"])
    row = profile_crud.start_inference(
        db, user_id=current_user["user_id"], graph_id=g.id, trigger="manual"
    )
    db.commit()
    return InferenceStartOut(id=row.id, status=row.status, trigger=row.trigger)


@profile_router.get("/inferences/{inference_id}", response_model=InferenceOut)
def get_inference(
    inference_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    row = profile_crud.get_inference(db, current_user["user_id"], inference_id)
    if not row:
        raise HTTPException(status_code=404, detail="推断任务不存在")
    return InferenceOut(
        id=row.id,
        status=row.status,
        trigger=row.trigger,
        result=row.result_json,
        error=row.error,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
    )