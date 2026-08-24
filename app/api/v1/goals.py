from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_db, get_current_active_user
from app.models import User, Goal
from app.schemas import (
    MeProfileOut,
    MeProfileUpdate,
    GoalOut,
    GoalActiveUpdate,
)


router = APIRouter(tags=["目标与个人资料"])


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
