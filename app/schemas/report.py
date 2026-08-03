from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ReportOut(BaseModel):
    id: str
    title: str
    content_md: str
    collection_id: Optional[str] = None
    note_type: str = "report"
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReportListOut(BaseModel):
    reports: List[ReportOut]
    total: int


class LearningReportGenerateOut(BaseModel):
    report: ReportOut
    saved_to_notes: bool = True
