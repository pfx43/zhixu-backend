from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.question import QuestionOption


class CitationOut(BaseModel):
    doc_id: Optional[str] = None
    segment_id: Optional[str] = None
    title: Optional[str] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    snippet: Optional[str] = None


class QuizSessionCreate(BaseModel):
    document_id: Optional[str] = None
    collection_id: Optional[str] = None
    question_ids: Optional[List[str]] = Field(None, min_length=1)
    title: Optional[str] = None

    @model_validator(mode="after")
    def require_target(self):
        if not self.document_id and not self.collection_id and not self.question_ids:
            raise ValueError("document_id、collection_id、question_ids 至少提供一个")
        return self


class QuizSessionQuestionOut(BaseModel):
    question_id: str
    order_index: int
    stem: str
    question_type: str
    options: Optional[List[QuestionOption]] = None


class QuizSessionOut(BaseModel):
    id: str
    title: Optional[str] = None
    status: str
    document_id: Optional[str] = None
    collection_id: Optional[str] = None
    total_questions: int
    answered_count: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    questions: List[QuizSessionQuestionOut] = []


class AnswerSubmit(BaseModel):
    question_id: str
    user_answer: Optional[str] = None
    status: Optional[str] = None
    time_spent_seconds: Optional[int] = None


class AnswerResult(BaseModel):
    question_id: str
    status: str
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None
    citation: Optional[CitationOut] = None
    answered_count: int
    total_questions: int
    session_status: str


class QuizReviewItemOut(BaseModel):
    question_id: str
    stem: str
    user_answer: Optional[str] = None
    status: str
    correct_answer: str
    explanation: Optional[str] = None
    citation: Optional[CitationOut] = None


class QuizResultsOut(BaseModel):
    session_id: str
    status: str
    total_questions: int
    correct_count: int
    wrong_count: int
    unknown_count: int
    items: List[QuizReviewItemOut] = []
