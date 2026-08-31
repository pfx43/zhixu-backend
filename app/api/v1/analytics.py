from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.crud import kb as kb_crud
from app.schemas.analytics import LearningStatsOut, TagStatsListOut
from app.schemas.report import LearningReportGenerateOut
from app.services.training import analytics_service, report_service

router = APIRouter(tags=["学习分析"])


@router.get("/stats", response_model=LearningStatsOut)
def get_learning_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """汇总文档、题库与刷题进度，供学习分析页展示。"""
    return analytics_service.get_learning_stats(db, current_user["user_id"])


@router.get("/tag-stats", response_model=TagStatsListOut)
def get_tag_stats(
    document_id: Optional[str] = Query(None, description="只统计这本书；不传则全用户"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """按 tag 与题型聚合错题统计。传 document_id 时只看当前用户这本书。"""
    resolved_id = None
    if document_id:
        doc = kb_crud.get_document_by_id_or_dify(
            db, current_user["user_id"], document_id.strip()
        )
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        resolved_id = doc.id
    return analytics_service.get_tag_stats(
        db, current_user["user_id"], document_id=resolved_id
    )


@router.post("/learning-report", response_model=LearningReportGenerateOut)
async def generate_learning_report(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """生成 LLM 学习报告并保存到笔记（别名路由）。"""
    result = await report_service.generate_learning_report(db, current_user["user_id"])
    db.commit()
    return result

