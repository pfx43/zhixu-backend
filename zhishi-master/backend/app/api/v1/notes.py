"""笔记系统路由"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.crud import note as note_crud


class NoteCreate(BaseModel):
    title: str
    content_md: str = ""
    collection_id: str | None = None
    note_type: str = "manual"


class NoteUpdate(BaseModel):
    title: str | None = None
    content_md: str | None = None
    collection_id: str | None = None
    note_type: str | None = None


router = APIRouter(tags=["笔记系统"])


def _note_response(r):
    return {
        "id": r.id,
        "title": r.title,
        "content_md": r.content_md,
        "note_type": r.note_type,
        "collection_id": r.collection_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("")
def list_notes(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=200),
    note_type: str = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """列出当前用户的笔记"""
    rows = note_crud.list_notes(
        db, current_user["user_id"], note_type=note_type, limit=limit
    )
    return [_note_response(r) for r in rows]


@router.get("/{note_id}")
def get_note(
    note_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """获取单条笔记详情"""
    row = note_crud.get_note_by_id(db, current_user["user_id"], note_id)
    if not row:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return _note_response(row)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """创建笔记"""
    row = note_crud.create_note(
        db,
        user_id=current_user["user_id"],
        title=payload.title,
        content_md=payload.content_md,
        collection_id=payload.collection_id,
        note_type=payload.note_type,
    )
    db.commit()
    return _note_response(row)


@router.patch("/{note_id}")
def update_note(
    note_id: str,
    payload: NoteUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """更新笔记"""
    row = note_crud.update_note(
        db, current_user["user_id"], note_id,
        title=payload.title,
        content_md=payload.content_md,
        collection_id=payload.collection_id,
        note_type=payload.note_type,
    )
    if not row:
        raise HTTPException(status_code=404, detail="笔记不存在")
    db.commit()
    return _note_response(row)


@router.delete("/{note_id}")
def delete_note(
    note_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """删除笔记"""
    ok = note_crud.delete_note(db, current_user["user_id"], note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="笔记不存在")
    db.commit()
    return {"message": "笔记已删除"}