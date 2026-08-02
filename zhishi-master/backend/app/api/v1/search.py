"""Independent current-user knowledge search endpoint."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.schemas.search import SearchResponseOut, SearchScope
from app.services import search_service

router = APIRouter(tags=["知识搜索"])


@router.get("", response_model=SearchResponseOut)
def search_knowledge(
    q: str = Query(..., min_length=1, description="要进行词法检索的关键词"),
    scope: SearchScope = Query("all", description="检索范围"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    collection_id: Optional[str] = Query(None, description="可选的知识库分区 ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Search notes and documents without using an LLM or embedding fallback."""
    query = q.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="q 不能为空白字符串",
        )
    return search_service.search_knowledge(
        db,
        user_id=current_user["user_id"],
        query=query,
        scope=scope,
        page=page,
        limit=limit,
        collection_id=collection_id,
    )
