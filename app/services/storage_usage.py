"""按用户汇总资料占用（逻辑体积，写入 users.storage_used_bytes）。"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Document, GlobalDocument, NoteAttachment, User


def compute_user_storage_bytes(db: Session, user_id: int) -> int:
    """资料原文件 + 笔记附件。笔记按 storage_path 去重，避免 checksum 复用算两次。"""
    doc_bytes = (
        db.query(func.coalesce(func.sum(GlobalDocument.file_size), 0))
        .select_from(Document)
        .join(GlobalDocument, Document.global_document_id == GlobalDocument.id)
        .filter(Document.user_id == user_id)
        .scalar()
    )
    note_sub = (
        db.query(func.max(NoteAttachment.file_size).label("sz"))
        .filter(NoteAttachment.user_id == user_id)
        .group_by(NoteAttachment.storage_path)
        .subquery()
    )
    note_bytes = db.query(func.coalesce(func.sum(note_sub.c.sz), 0)).scalar()
    return int(doc_bytes or 0) + int(note_bytes or 0)


def refresh_user_storage(db: Session, user_id: int) -> int:
    """重算并写回 users.storage_used_bytes，不 commit。"""
    total = compute_user_storage_bytes(db, user_id)
    user = db.query(User).filter(User.id == user_id).first()
    if user is not None:
        user.storage_used_bytes = total
    return total
