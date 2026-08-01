from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class DocumentStatsOut(BaseModel):
    total: int = 0
    indexed: int = 0
    processing: int = 0
    failed: int = 0
    study_zone: int = 0
    with_questions: int = 0


class QuestionStatsOut(BaseModel):
    total: int = 0
    answered: int = 0
    correct: int = 0
    wrong: int = 0
    unknown: int = 0
    accuracy_rate: Optional[int] = None


class DocumentProgressOut(BaseModel):
    document_id: str
    document_name: str
    question_total: int = 0
    answered_count: int = 0
    correct_count: int = 0
    wrong_count: int = 0
    unknown_count: int = 0
    accuracy_rate: Optional[int] = None


class RecentSessionOut(BaseModel):
    id: str
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    status: str
    total_questions: int = 0
    answered_count: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class RecentAnswerOut(BaseModel):
    question_id: str
    stem: str
    status: str
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    answered_at: Optional[datetime] = None


class LearningStatsOut(BaseModel):
    documents: DocumentStatsOut
    questions: QuestionStatsOut
    document_progress: List[DocumentProgressOut] = []
    recent_sessions: List[RecentSessionOut] = []
    recent_answers: List[RecentAnswerOut] = []


class TagStatsOut(BaseModel):
    tag: str
    question_type: str = "all"
    correct_count: int = 0
    wrong_count: int = 0
    unknown_count: int = 0
    total_attempts: int = 0
    accuracy_rate: Optional[int] = None


class TagStatsListOut(BaseModel):
    by_tag: List[TagStatsOut] = []
    by_question_type: List[TagStatsOut] = []
