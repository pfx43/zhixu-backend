from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.api.deps import get_db, get_current_active_user
from app.models import PlanTier as PlanModel, User
import app.crud as crud
from app.schemas import PlanTier, PlanInfo, UpgradeRequest, UserWithPlan

router = APIRouter(tags=["plans"])

@router.get("/", response_model=List[PlanTier])
def get_all_plans(db: Session = Depends(get_db)):
    """获取所有可用套餐列表"""
    plans = crud.get_all_plans(db)
    return plans

@router.get("/my-plan")
def get_my_plan_info(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    获取当前用户套餐及升级选项
    Path: /plans/my-plan
    """
    # Fetch fresh user data from DB to ensure plan details are up to date
    db_user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    user_plan = db.query(PlanModel).filter(PlanModel.level == db_user.plan_level).first()
    
    # Get potential upgrades (plans with higher level)
    upgrades = db.query(PlanModel).filter(PlanModel.level > db_user.plan_level).all()
    
    return {
        "current_plan": {
            "level": db_user.plan_level,
            "name": user_plan.name if user_plan else "Unknown",
            "api_limit_daily": db_user.api_limit_daily,
            "token_limit_monthly": db_user.token_limit_monthly,
            "expires_at": db_user.expires_at
        },
        "available_upgrades": upgrades
    }
