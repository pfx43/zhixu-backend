from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


SearchScope = Literal["all", "notes", "documents"]
SearchItemType = Literal["note", "document"]
SearchMatchSource = Literal["title", "content"]


class SearchItemOut(BaseModel):
    id: str
    type: SearchItemType
    title: str
    subtitle: str
    updated_at: Optional[datetime] = None
    collection_id: Optional[str] = None
    match_source: SearchMatchSource
    indexing_status: Optional[str] = None


class SearchResponseOut(BaseModel):
    query: str
    items: List[SearchItemOut]
    total: int
    page: int
    limit: int
    partial: bool
    pending_document_count: int
