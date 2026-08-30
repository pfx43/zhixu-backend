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


class DocumentKnowledgeTagOut(BaseModel):
    name: str
    question_count: int = 0
    correct_count: int = 0
    wrong_count: int = 0
    unknown_count: int = 0


class DocumentKnowledgeTagListOut(BaseModel):
    document_id: str
    tags: List[DocumentKnowledgeTagOut] = []
    total: int = 0
