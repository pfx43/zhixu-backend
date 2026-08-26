import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class UserNote(Base):
    __tablename__ = "user_notes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    collection_id = Column(String(36), ForeignKey("kb_collections.id"), nullable=True)
    # Issue #18 tip：关联哪本资料（可空，软引用；应用层校验归属）
    document_id = Column(String(36), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    content_md = Column(Text, nullable=False)
    note_type = Column(String(20), nullable=False, default="manual")
    # Issue #18 tip：用户给短卡片打的类型（难词/易错点…），JSONB 数组。
    # 与题目/文档的知识点 tag 分命名空间，按当前用户隔离；没有也可以收。
    tags = Column(JSONB, nullable=True)
    # Issue #18 tip：来源（tina / quiz / kb），列表可按来源筛选
    source = Column(String(20), nullable=True)
    # 稳定的乐观锁令牌，刻意独立于展示时间，避免受数据库精度和时区表示影响。
    revision = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # 软删除与回收站
    deleted_at = Column(DateTime, nullable=True)
    deleted_by_revision = Column(Integer, nullable=True)


class NoteAttachment(Base):
    """笔记附件（图片 / 音频）"""

    __tablename__ = "note_attachments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id = Column(String(36), ForeignKey("user_notes.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    media_type = Column(String(20), nullable=False)  # "image" | "audio"
    mime_type = Column(String(100), nullable=False)  # "image/png", "audio/mp4"
    file_size = Column(Integer, nullable=False)  # bytes
    checksum = Column(String(64), nullable=False)  # SHA-256
    storage_path = Column(String(512), nullable=False)  # 相对路径
    original_filename = Column(String(255), nullable=False)
    width = Column(Integer, nullable=True)  # 图片宽度
    height = Column(Integer, nullable=True)  # 图片高度
    duration_seconds = Column(Integer, nullable=True)  # 音频时长
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    # NULL 表示尚未挂载到任何笔记版本（孤儿 / 上传后未保存）
    note_revision = Column(Integer, nullable=True)
