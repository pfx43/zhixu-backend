from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class SegmentOut(BaseModel):
    id: str
    document_id: str
    order_index: int
    title: Optional[str] = None
    content: str
    char_start: int
    char_end: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SegmentListOut(BaseModel):
    document_id: str
    segment_status: str
    segments: List[SegmentOut]
    total: int
