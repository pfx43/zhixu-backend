"""笔记系统路由"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.crud import note as note_crud


class NoteCreate(BaseModel):
    title: str
    content_md: str = ""
    collection_id: str | None = None
    note_type: str = "manual"


class NoteUpdate(BaseModel):
    expected_revision: int = Field(
        ge=1,
        description="客户端读取到的笔记 revision；用于乐观并发控制。",
    )
    title: str | None = None
    content_md: str | None = None
    collection_id: str | None = None
    note_type: str | None = None


class NoteDelete(BaseModel):
    expected_revision: int = Field(
        ge=1,
        description="客户端读取到的笔记 revision；用于乐观并发控制。",
    )


class NoteRestore(BaseModel):
    expected_revision: int = Field(
        ge=1,
        description="回收站中记录的 revision；用于乐观并发控制。",
    )


class NoteResponse(BaseModel):
    id: str
    title: str
    content_md: str
    note_type: str
    collection_id: str | None = None
    revision: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NoteTrashResponse(BaseModel):
    id: str
    title: str
    note_type: str
    revision: int
    deleted_at: datetime | None = None
    deleted_by_revision: int | None = None


class NoteRevisionConflictDetail(BaseModel):
    code: Literal["note_revision_conflict"]
    detail: str
    current_revision: int


class NoteRevisionConflictResponse(BaseModel):
    detail: NoteRevisionConflictDetail


router = APIRouter(tags=["笔记系统"])


def _note_response(r):
    return {
        "id": r.id,
        "title": r.title,
        "content_md": r.content_md,
        "note_type": r.note_type,
        "collection_id": r.collection_id,
        "revision": r.revision,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _trash_response(r):
    return {
        "id": r.id,
        "title": r.title,
        "note_type": r.note_type,
        "revision": r.revision,
        "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
        "deleted_by_revision": r.deleted_by_revision,
    }


@router.get("", response_model=list[NoteResponse])
def list_notes(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=200),
    note_type: str = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """列出当前用户的笔记（默认排除已删除）"""
    rows = note_crud.list_notes(
        db, current_user["user_id"], note_type=note_type, limit=limit
    )
    return [_note_response(r) for r in rows]


# ── 静态路由必须在动态路由之前注册 ──────────────────────────

@router.get("/trash/items", response_model=list[NoteTrashResponse])
def list_trash(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """列出当前用户回收站中的已删除笔记"""
    rows = note_crud.list_trash(
        db, current_user["user_id"], page=page, limit=limit
    )
    return [_trash_response(r) for r in rows]


@router.get("/{note_id}", response_model=NoteResponse)
def get_note(
    note_id: str,
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """获取单条笔记详情"""
    row = note_crud.get_note_by_id(
        db, current_user["user_id"], note_id, include_deleted=include_deleted
    )
    if not row:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return _note_response(row)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=NoteResponse)
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


@router.post(
    "/{note_id}/restore",
    response_model=NoteResponse,
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "客户端基于的笔记版本已过期。",
            "model": NoteRevisionConflictResponse,
        }
    },
)
def restore_note(
    note_id: str,
    payload: NoteRestore,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """从回收站恢复笔记（基于 revision 乐观锁）"""
    result = note_crud.restore_note(
        db,
        current_user["user_id"],
        note_id,
        expected_revision=payload.expected_revision,
    )
    if not result.success:
        if result.current_revision is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "note_revision_conflict",
                    "detail": "笔记已被更新，请使用最新版本重试",
                    "current_revision": result.current_revision,
                },
            )
        raise HTTPException(status_code=404, detail="笔记不存在或不在回收站中")
    db.commit()
    return _note_response(result.note)


@router.patch(
    "/{note_id}",
    response_model=NoteResponse,
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "客户端基于的笔记版本已过期。",
            "model": NoteRevisionConflictResponse,
        }
    },
)
def update_note(
    note_id: str,
    payload: NoteUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """更新笔记"""
    result = note_crud.update_note(
        db,
        current_user["user_id"],
        note_id,
        expected_revision=payload.expected_revision,
        title=payload.title,
        content_md=payload.content_md,
        collection_id=payload.collection_id,
        note_type=payload.note_type,
    )
    if result.note is None:
        if result.current_revision is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "note_revision_conflict",
                    "detail": "笔记已被更新，请使用最新版本重试",
                    "current_revision": result.current_revision,
                },
            )
        raise HTTPException(status_code=404, detail="笔记不存在")
    response = _note_response(result.note)
    db.commit()
    return response


@router.delete(
    "/{note_id}",
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "客户端基于的笔记版本已过期。",
            "model": NoteRevisionConflictResponse,
        }
    },
)
def delete_note(
    note_id: str,
    payload: NoteDelete,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """软删除笔记（基于 revision 乐观锁）"""
    result = note_crud.delete_note(
        db,
        current_user["user_id"],
        note_id,
        expected_revision=payload.expected_revision,
    )
    if not result.success:
        if result.current_revision is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "note_revision_conflict",
                    "detail": "笔记已被更新，请使用最新版本重试",
                    "current_revision": result.current_revision,
                },
            )
        raise HTTPException(status_code=404, detail="笔记不存在")
    db.commit()
    return {
        "message": "笔记已移入回收站",
        "revision": result.current_revision,
    }
