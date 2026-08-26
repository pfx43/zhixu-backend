"""学习路径 API — 书→章进度 + tag 知识点进度（纯聚合，不依赖 TCN）。

Issue #5.X 目标范围 Path：``?goal_id=X`` 切到「本目标路径」。
"""
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
        None, description="Issue #5.X：目标范围内的路径（按目标过滤）"
    ),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """学习路径：每本书按章（目录）聚合题目进度 + tag 知识点进度。

    ``?goal_id=X`` 切到「当前目标范围内的路径」（Issue #5.X）。
    """
    return progress_service.get_learning_path(
        db, current_user["user_id"], goal_id=goal_id
    )