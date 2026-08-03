from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


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
    ocr_status: Optional[str] = None
    ocr_current_page: Optional[int] = None
    ocr_total_pages: Optional[int] = None
    dify_document_id: Optional[str] = None
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
