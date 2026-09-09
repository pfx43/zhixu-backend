from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.task import TaskCompletedOut


class QuestionOption(BaseModel):
    """题目选项（Issue #35 可机读结构）。

    - 选择/判断/填空/排序：key + text
    - match：每项额外带 side = "left" | "right"（Web 不再按下标切半）
    """

    key: str
    text: str
    side: Optional[str] = None  # 仅 match 题型使用

    model_config = ConfigDict(extra="allow")


class ClassifyOptions(BaseModel):
    """classify 题型的 options 结构：items[] + categories[] 两段。

    - items: 待分类条目
    - categories: 类别列表
    - user_answer 形如 {"itemId": "categoryId"}
    """

    items: List[dict] = []
    categories: List[dict] = []

    model_config = ConfigDict(extra="allow")


class ProvenanceOut(BaseModel):
    id: str
    document_id: Optional[str] = None
    segment_id: Optional[str] = None
    page_number: Optional[int] = None
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
    job_id: Optional[str] = None
    # 检查器挂载：payload 页已有题 → 今日出题任务自动完成（空则不弹窗）
    completed_tasks: List[TaskCompletedOut] = []
