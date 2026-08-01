from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TutorSessionCreate(BaseModel):
    question_id: str
    quiz_session_id: Optional[str] = None
    quiz_answer_id: Optional[str] = None


class TutorMessageCreate(BaseModel):
    content: str = Field(..., min_length=1)
    stream: bool = False


class TutorMessage(BaseModel):
    role: str
    content: str
    created_at: Optional[str] = None


class SegmentContextOut(BaseModel):
    segment_id: str
    title: Optional[str] = None
    snippet: str


class TutorSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str
    document_id: str
    segment_id: str
    quiz_answer_id: Optional[str] = None
    status: str
    question_stem: str
    segment_context: SegmentContextOut
    messages: List[TutorMessage] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TutorReplyOut(BaseModel):
    role: str = "assistant"
    content: str
    created_at: str
