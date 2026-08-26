"""进度 / 学习路径 API（纯聚合，不新增表、不依赖 TCN）。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.schemas.progress import (
    LearningPathOut,
    ProgressHeatmapOut,
    ProgressOverviewOut,
    ProgressTimelineOut,
)
from app.services.training import progress_service

router = APIRouter(tags=["进度与学习路径"])


@router.get("/overview", response_model=ProgressOverviewOut)
def get_progress_overview(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """学习进度总览：文档/题目/答题/正确率/学习天数/累计时长。"""
    return progress_service.get_progress_overview(db, current_user["user_id"])


@router.get("/heatmap", response_model=ProgressHeatmapOut)
def get_progress_heatmap(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """按日答题次数热力图（默认最近 90 天）。"""
    return progress_service.get_progress_heatmap(db, current_user["user_id"], days)


@router.get("/timeline", response_model=ProgressTimelineOut)
def get_progress_timeline(
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """学习事件时间线（上传 / 出题 / 答题，按时间倒序）。"""
    return progress_service.get_progress_timeline(db, current_user["user_id"], limit)