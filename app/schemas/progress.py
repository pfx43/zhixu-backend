"""进度 / 学习路径后端数据 Schema（纯聚合，不新增表）。"""
from typing import List, Optional

from pydantic import BaseModel


class ProgressOverviewOut(BaseModel):
    document_count: int = 0
    question_count: int = 0
    answered_count: int = 0
    correct_count: int = 0
    wrong_count: int = 0
    unknown_count: int = 0
    accuracy_rate: Optional[int] = None
    study_days: int = 0
    total_study_seconds: int = 0


class HeatmapDayOut(BaseModel):
    date: str
    count: int


class ProgressHeatmapOut(BaseModel):
    days: int
    items: List[HeatmapDayOut] = []


class TimelineItemOut(BaseModel):
    event_type: str
    occurred_at: str
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    question_id: Optional[str] = None
    status: Optional[str] = None


class ProgressTimelineOut(BaseModel):
    items: List[TimelineItemOut] = []


class ChapterProgressOut(BaseModel):
    order_index: int
    title: str
    page_start: int
    page_end: int
    question_count: int = 0
    answered_count: int = 0
    correct_count: int = 0
    wrong_count: int = 0
    unknown_count: int = 0
    accuracy_rate: Optional[int] = None


class CurrentChapterOut(BaseModel):
    """路径页用来标「你在第几章」，不含题量和对错。"""

    order_index: int
    title: str
    page_start: int
    page_end: int


class DocumentNextOut(BaseModel):
    """路径页顶部「下一步」。记分只在后端用来挑选，响应里不带回对错。"""

    kind: str = "chapter"
    title: str
    reason: str
    action: str
    order_index: Optional[int] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class DomainMaterialOut(BaseModel):
    """某一科下面挂着的资料。路径图跨这些书，不按单本切。"""

    document_id: str
    document_name: str
    has_toc: bool = False
    question_count: int = 0
    answered_count: int = 0


class DomainLearningPathOut(BaseModel):
    domain: str
    domain_label: str
    documents: List[DomainMaterialOut] = []


class DocumentLearningPathOut(BaseModel):
    document_id: str
    document_name: str
    has_toc: bool = False
    tcn_domain: Optional[str] = None
    tcn_domain_label: Optional[str] = None
    current_chapter: Optional[CurrentChapterOut] = None
    next: Optional[DocumentNextOut] = None
    chapters: List[ChapterProgressOut] = []
    uncategorized_question_count: int = 0
    uncategorized_answered_count: int = 0
    uncategorized_correct_count: int = 0
    uncategorized_wrong_count: int = 0
    uncategorized_unknown_count: int = 0


class TagProgressOut(BaseModel):
    tag: str
    question_count: int = 0
    answered_count: int = 0
    correct_count: int = 0
    wrong_count: int = 0
    unknown_count: int = 0
    accuracy_rate: Optional[int] = None


class LearningPathOut(BaseModel):
    documents: List[DocumentLearningPathOut] = []
    domains: List[DomainLearningPathOut] = []
    untracked: List[DomainMaterialOut] = []
    tags: List[TagProgressOut] = []