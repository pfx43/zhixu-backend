"""学习报告 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.schemas.report import LearningReportGenerateOut, ReportListOut, ReportOut
from app.services import report_service

router = APIRouter(tags=["学习报告"])


@router.post("/generate", response_model=LearningReportGenerateOut)
def generate_learning_report(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """基于 tag 统计与刷题数据生成 LLM 学习报告，并自动保存到生活区笔记。"""
    result = report_service.generate_learning_report(db, current_user["user_id"])
    db.commit()
    return result


@router.get("", response_model=ReportListOut)
def list_reports(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """列出历史学习报告。"""
    return report_service.list_reports(db, current_user["user_id"])


@router.get("/latest", response_model=ReportOut)
def get_latest_report(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """获取最新一份学习报告。"""
    return report_service.get_latest_report(db, current_user["user_id"])


@router.get("/{report_id}", response_model=ReportOut)
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """获取指定学习报告。"""
    return report_service.get_report_by_id(db, current_user["user_id"], report_id)
