from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_active_user
from app.models import User, Goal, GoalEvidenceEvent
from app.schemas import (
    MeProfileOut,
    MeProfileUpdate,
    GoalOut,
    GoalActiveUpdate,
)


router = APIRouter(tags=["目标与个人资料"])


# ── /api/v1/goals/{goal_id}/evidence（Issue #38 Evidence Impact）──

class EvidenceEventOut(BaseModel):
    """目标详情「证据变化」条目：独立契约，不复用 task evidence 冒充。"""

    id: str
    goal_id: int
    occurred_at: Optional[datetime] = None
    source: str
    node_id: Optional[str] = None
    node_label: Optional[str] = None
    before: Optional[dict] = None
    after: Optional[dict] = None
    scope: str = "goal"
    confirmation: str = "pending"

    model_config = ConfigDict(from_attributes=True)


# ── /api/v1/me/profile ──────────────────────────────────────────

@router.get("/me/profile", response_model=MeProfileOut)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """获取当前用户的称呼等个人资料"""
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return MeProfileOut(
        user_id=user.id,
        nickname=user.nickname,
    )


@router.put("/me/profile", response_model=MeProfileOut)
def update_my_profile(
    payload: MeProfileUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """更新当前用户的称呼（nickname）"""
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.nickname = payload.nickname.strip()
    try:
        db.commit()
        db.refresh(user)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"资料更新失败: {e}",
        )

    return MeProfileOut(
        user_id=user.id,
        nickname=user.nickname,
    )


# ── /api/v1/goals ────────────────────────────────────────────────

@router.get("/goals", response_model=List[GoalOut])
def list_my_goals(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """获取当前用户所有目标（按创建时间倒序）

    - 一人同时只能有一条 active
    - 首页/ Tina 只读取 status=active 的那一条
    """
    goals = (
        db.query(Goal)
        .filter(Goal.user_id == current_user["user_id"])
        .order_by(Goal.created_at.desc())
        .all()
    )
    return goals


@router.put("/goals/active", response_model=GoalOut)
def upsert_active_goal(
    payload: GoalActiveUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """设置或修改当前进行中的目标（一人一条 active）

    语义（OpenAPI 写死）：
    - 若当前用户已存在 status=active 的 goal → 更新该条的 text / attributes / valid_until
    - 若不存在 active goal → 新建一条 status=active
    - 历史 goals（paused / completed）保持不变，不会被自动改为 paused
    - 本接口不提供「用户宣布学会了」即 completed 入口；结业靠后续测量
    """
    user_id = current_user["user_id"]

    active = (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status == "active")
        .with_for_update()
        .one_or_none()
    )

    if active is not None:
        active.text = payload.text.strip()
        active.attributes = payload.attributes
        active.valid_until = payload.valid_until
        goal = active
    else:
        goal = Goal(
            user_id=user_id,
            text=payload.text.strip(),
            attributes=payload.attributes,
            valid_until=payload.valid_until,
            status="active",
        )
        db.add(goal)

    try:
        db.commit()
        db.refresh(goal)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"目标保存失败: {e}",
        )

    return goal


@router.get("/goals/{goal_id}/evidence", response_model=List[EvidenceEventOut])
def list_goal_evidence(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """按 goal_id 查询「证据变化」列表（时间正序）。

    只返回本人目标的证据；别人的 goal_id 一律 404（不泄露存在性）。
    每条含前后值：{ id, goal_id, occurred_at, source, node_id, node_label,
    before, after, scope, confirmation }。
    """
    goal = (
        db.query(Goal)
        .filter(Goal.id == goal_id, Goal.user_id == current_user["user_id"])
        .first()
    )
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")
    events = (
        db.query(GoalEvidenceEvent)
        .filter(GoalEvidenceEvent.goal_id == goal_id)
        .order_by(GoalEvidenceEvent.occurred_at.asc())
        .all()
    )
    return events


def record_goal_evidence(
    db: Session,
    *,
    user_id: int,
    goal_id: Optional[int],
    source: str,
    before: Optional[dict],
    after: Optional[dict],
    node_id: Optional[str] = None,
    node_label: Optional[str] = None,
    scope: str = "goal",
) -> Optional[GoalEvidenceEvent]:
    """写一条证据变化事件（无 active 目标时静默跳过，不影响主流程）。

    供检查器/上传/出题/交卷成功路径调用；失败只记日志不抛异常。
    """
    if not goal_id:
        return None
    try:
        event = GoalEvidenceEvent(
            user_id=user_id,
            goal_id=goal_id,
            source=source,
            node_id=node_id,
            node_label=node_label,
            before=before,
            after=after,
            scope=scope,
            confirmation="pending",
        )
        db.add(event)
        db.flush()
        return event
    except Exception as e:  # noqa: BLE001 — 证据记录不能影响主流程
        import logging

        logging.getLogger(__name__).warning(f"record_goal_evidence 失败: {e}")
        return None
