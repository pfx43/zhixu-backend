"""出题作业表 — 主程序入队与交卷入库；出题服务只读快照、不写题库。"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class QgenJob(Base):
    __tablename__ = "qgen_jobs"
    __table_args__ = (
        Index("ix_qgen_jobs_status_created", "status", "created_at"),
        Index("ix_qgen_jobs_user_status", "user_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    mode = Column(String(20), nullable=False, default="generate")
    status = Column(String(20), nullable=False, default="queued")
    goal_text = Column(Text, nullable=True)
    tag_hint = Column(Text, nullable=True)
    tcn_domain = Column(String(64), nullable=True)
    questions_per_page = Column(Integer, nullable=False, default=1)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    pages = relationship(
        "QgenJobPage",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="QgenJobPage.page_number",
    )


class QgenJobPage(Base):
    __tablename__ = "qgen_job_pages"
    __table_args__ = (
        UniqueConstraint("job_id", "page_number", name="uq_qgen_job_pages_job_page"),
        Index("ix_qgen_job_pages_job_status", "job_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(
        String(36),
        ForeignKey("qgen_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number = Column(Integer, nullable=False)
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    near_pages_json = Column(JSON, nullable=True)
    allowed_page_numbers_json = Column(JSON, nullable=True)
    segment_id = Column(String(36), nullable=True)
    status = Column(String(20), nullable=False, default="queued")
    questions_json = Column(JSON, nullable=True)
    usage_json = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    job = relationship("QgenJob", back_populates="pages")
