from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DocumentPageOut(BaseModel):
    page_number: int
    title: str
    preview: str
    char_start: int
    char_end: int
    content_length: int
    has_builtin_questions: bool = False
    is_key_page: bool = False
    segment_id: Optional[str] = None
    preview_mode: str = "markdown"
    file_type: Optional[str] = None
    # 该页当前用户已入库的题目数（按页出题/提取后 > 0）
    question_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class DocumentPageListOut(BaseModel):
    document_id: str
    document_name: str
    total_pages: int
    has_page_markers: bool
    preview_mode: str = "markdown"
    file_type: Optional[str] = None
    has_raw_file: bool = False
    pages: List[DocumentPageOut]


class DocumentPageDetailOut(DocumentPageOut):
    content: str


class PageGenerateRequest(BaseModel):
    document_id: str
    page_numbers: List[int] = Field(..., min_length=1)
    # 省略 = Agent 按内容自定 1～3 道；传入 1–3 则固定道数
    questions_per_page: Optional[int] = Field(default=None, ge=1, le=3)


class PageExtractRequest(BaseModel):
    document_id: str
    page_numbers: List[int] = Field(..., min_length=1)
