from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.task import TaskCompletedOut


class CollectionOut(BaseModel):
    id: str
    name: str
    zone: str
    description: Optional[str] = None
    dataset_id: Optional[str] = None
    is_default: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CollectionListOut(BaseModel):
    collections: List[CollectionOut]
    total: int


class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    zone: str = Field(..., pattern="^(study|life)$")
    description: Optional[str] = Field(None, max_length=500)


class CollectionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class TcnDomainOut(BaseModel):
    id: str
    label: str


class TcnDomainListOut(BaseModel):
    domains: List[TcnDomainOut]


class DocumentTcnDomainUpdate(BaseModel):
    tcn_domain: Optional[str] = None


class DocumentTcnDomainOut(BaseModel):
    document_id: str
    tcn_domain: Optional[str] = None
    tcn_domain_label: Optional[str] = None


class TcnGraphNodeOut(BaseModel):
    id: str
    name: str
    mastery: Optional[float] = None


class TcnGraphEdgeOut(BaseModel):
    source: str
    target: str
    weight: Optional[float] = None


class TcnGraphNextOut(BaseModel):
    """先修已够、自身偏低的前沿节点。前端用 name 刷题，不要把 id 当 tc_node_id 传。"""

    id: str
    name: str
    mastery: Optional[float] = None
    reason: str


class DomainTcnGraphOut(BaseModel):
    """一科的 TCN 图，不绑某一本书。掌握度是这个学生在这一科上的。"""

    domain: str
    domain_label: Optional[str] = None
    nodes: List[TcnGraphNodeOut] = []
    edges: List[TcnGraphEdgeOut] = []
    next_nodes: List[TcnGraphNextOut] = []


class DocumentTcnGraphOut(BaseModel):
    document_id: Optional[str] = None
    domain: Optional[str] = None
    domain_label: Optional[str] = None
    nodes: List[TcnGraphNodeOut] = []
    edges: List[TcnGraphEdgeOut] = []
    next_nodes: List[TcnGraphNextOut] = []


class DocumentOut(BaseModel):
    id: str
    name: str
    collection_id: str
    zone: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    indexing_status: str = "pending"
    segment_status: str = "not_started"
    question_gen_status: str = "not_started"
    question_count: int = 0
    ocr_status: Optional[str] = None
    ocr_current_page: Optional[int] = None
    ocr_total_pages: Optional[int] = None
    dify_document_id: Optional[str] = None
    # #40 封面 / 缩略图可访问 URL；无封面时为 None，前端兜底
    cover_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    tcn_domain: Optional[str] = None
    tcn_domain_label: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentListOut(BaseModel):
    documents: List[DocumentOut]
    total: int
    page: int
    limit: int
    dataset_id: Optional[str] = None
    collection_id: Optional[str] = None


class UploadResponse(BaseModel):
    message: str
    batch_id: Optional[str] = None
    document_id: Optional[str] = None
    id: Optional[str] = None
    file_name: str
    dataset_id: Optional[str] = None
    collection_id: Optional[str] = None
    status: str
    segment_status: str = "not_started"
    parse_warning: Optional[str] = None
    ocr_processed: bool = False
    ocr_status: Optional[str] = None
    ocr_current_page: Optional[int] = None
    ocr_total_pages: Optional[int] = None
    # 检查器挂载：本次成功路径完成后自动判定的今日任务（空则不弹窗）
    completed_tasks: List[TaskCompletedOut] = []
