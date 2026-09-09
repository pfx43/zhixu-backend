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
    goal_id: Optional[int] = Query(None, description="目标 id（仅做归属校验）"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """进度页仍读 documents（按书/章记分）。路径页读 domains：一科一张图，资料挂在科下面。

    有学科时下一步以该科 tcn-graph.next_nodes 为准，不绑某一本书。
    goal_id 传入时仅校验该目标属于当前用户；暂不做范围过滤。
    """
    return progress_service.get_learning_path(
        db, current_user["user_id"], goal_id=goal_id
    )
