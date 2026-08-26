"""学习路径 API — 书→章进度 + tag 知识点进度（纯聚合，不依赖 TCN）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.schemas.progress import LearningPathOut
from app.services.training import progress_service

router = APIRouter(tags=["学习路径"])


@router.get("", response_model=LearningPathOut)
def get_learning_path(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """学习路径：每本书按章（目录）聚合题目进度 + tag 知识点进度。"""
    return progress_service.get_learning_path(db, current_user["user_id"])