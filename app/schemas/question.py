from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuestionOption(BaseModel):
    key: str
    text: str


class ProvenanceOut(BaseModel):
    id: str
    document_id: Optional[str] = None
    segment_id: Optional[str] = None
    excerpt: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class QuestionOut(BaseModel):
    id: str
    stem: str
    question_type: str
    options: Optional[List[QuestionOption]] = None
    answer: str
    explanation: Optional[str] = None
    tags: Optional[List[str]] = None
    source_type: str
    document_id: Optional[str] = None
    collection_id: Optional[str] = None
    created_at: Optional[datetime] = None
    user_answer_status: Optional[str] = None
    attempt_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class QuestionDetailOut(QuestionOut):
    provenance: List[ProvenanceOut] = []


class QuestionListOut(BaseModel):
    questions: List[QuestionOut]
    total: int
    document_id: Optional[str] = None
    collection_id: Optional[str] = None
    answered_count: int = 0
    correct_count: int = 0
    wrong_count: int = 0
    unknown_count: int = 0


class QuestionBulkDeleteRequest(BaseModel):
    document_id: Optional[str] = None
    collection_id: Optional[str] = None
    question_ids: Optional[List[str]] = Field(None, min_length=1)


class QuestionDeleteResponse(BaseModel):
    deleted_count: int
    document_id: Optional[str] = None
    collection_id: Optional[str] = None


class QuestionGenerateRequest(BaseModel):
    document_id: Optional[str] = None
    segment_ids: Optional[List[str]] = Field(None, min_length=1)

    @model_validator(mode="after")
    def require_target(self):
        if not self.document_id and not self.segment_ids:
            raise ValueError("document_id 与 segment_ids 至少提供一个")
        return self


class QuestionGenerateResponse(BaseModel):
    document_id: Optional[str] = None
    question_gen_status: str
    questions_created: int
    questions_reused: int
    total_questions: int


class PageQuestionResponse(BaseModel):
    document_id: str
    page_numbers: List[int]
    mode: str
    question_gen_status: Optional[str] = None
    questions_created: int
    questions_reused: int
    total_questions: int
