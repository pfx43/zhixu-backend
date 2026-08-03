import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class KbCollection(Base):
    __tablename__ = "kb_collections"
    __table_args__ = (
        Index("ix_kb_collections_user_zone", "user_id", "zone"),
        UniqueConstraint("user_id", "name", name="uq_kb_collections_user_name"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    zone = Column(String(20), nullable=False)
    description = Column(String(500), nullable=True)
    dataset_id = Column(String(255), nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="kb_collections")
    documents = relationship("Document", back_populates="collection")


class GlobalDocument(Base):
    __tablename__ = "global_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    content_hash = Column(String(64), unique=True, nullable=False)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=False)
    storage_path = Column(String(512), nullable=False)
    parsed_text_path = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("Document", back_populates="global_document")
    question_provenance = relationship("QuestionProvenance", back_populates="global_document")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_documents_user_content_hash"),
        Index("ix_documents_user_collection", "user_id", "collection_id"),
        Index("ix_documents_global_document", "global_document_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    collection_id = Column(String(36), ForeignKey("kb_collections.id"), nullable=False)
    global_document_id = Column(String(36), ForeignKey("global_documents.id"), nullable=True)
    dify_document_id = Column(String(255), nullable=True, index=True)
    dify_batch_id = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=False)
    zone = Column(String(20), nullable=False)
    tags = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=False)
    parsed_cache_key = Column(String(255), nullable=True)
    indexing_status = Column(String(20), default="pending")
    segment_status = Column(String(20), default="not_started")
    question_gen_status = Column(String(20), default="not_started")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="documents")
    collection = relationship("KbCollection", back_populates="documents")
    global_document = relationship("GlobalDocument", back_populates="documents")
    segments = relationship("DocumentSegment", back_populates="document")


class DocumentSegment(Base):
    __tablename__ = "document_segments"
    __table_args__ = (
        UniqueConstraint("document_id", "order_index", name="uq_document_segments_doc_order"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    order_index = Column(Integer, nullable=False)
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    char_start = Column(Integer, nullable=False)
    char_end = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="segments")
    question_provenance = relationship("QuestionProvenance", back_populates="segment")
