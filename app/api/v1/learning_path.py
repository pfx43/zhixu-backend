"""学习路径 API — 书→章进度 + tag 知识点进度（纯聚合，不依赖 TCN）。"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.schemas.progress import LearningPathOut
from app.services.training import progress_service

router = APIRouter(tags=["学习路径"])


@router.get("", response_model=LearningPathOut)
def get_learning_path(
    goal_id: Optional[int] = Query(
        None, description="目标 id；传入时按目标过滤（当前未实现，返回 501）"
    ),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """学习路径：每本书按章（目录）聚合题目进度 + tag 知识点进度。

    - 不传 goal_id：返回当前用户全部学习区（study）文档。
    - 传 goal_id 且不属于当前用户：404。
    - 传 goal_id 且属于当前用户：501——按目标过滤暂未实现，不会返回全书冒充过滤成功。
    """
    return progress_service.get_learning_path(
        db, current_user["user_id"], goal_id=goal_id
    )
