from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class TagOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    document_id: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TagListOut(BaseModel):
    tags: List[TagOut]
    total: int
