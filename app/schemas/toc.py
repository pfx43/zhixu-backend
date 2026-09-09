from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class TocOut(BaseModel):
    id: str
    title: str
    page_start: int
    page_end: int

    model_config = ConfigDict(from_attributes=True)


class TocListOut(BaseModel):
    document_id: str
    toc: List[TocOut]
    total: int
    tcn_domain: Optional[str] = None
    tcn_domain_label: Optional[str] = None