"""出题作业表 qgen_jobs / qgen_job_pages

Revision ID: 20260829_qgen_jobs
Revises: 20260827_goal_evidence
Create Date: 2026-08-29 23:20:00.000000

主程序入队页快照；出题服务 claim 后按页 complete 交题。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260829_qgen_jobs"
down_revision = "20260827_goal_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("qgen_jobs"):
        return

    op.create_table(
        "qgen_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False, server_default="generate"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("goal_text", sa.Text(), nullable=True),
        sa.Column("tag_hint", sa.Text(), nullable=True),
        sa.Column("tcn_domain", sa.String(64), nullable=True),
        sa.Column("questions_per_page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_qgen_jobs_user_id", "qgen_jobs", ["user_id"])
    op.create_index("ix_qgen_jobs_document_id", "qgen_jobs", ["document_id"])
    op.create_index("ix_qgen_jobs_status_created", "qgen_jobs", ["status", "created_at"])
    op.create_index("ix_qgen_jobs_user_status", "qgen_jobs", ["user_id", "status"])

    op.create_table(
        "qgen_job_pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("qgen_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("near_pages_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "allowed_page_numbers_json",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("segment_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("questions_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("usage_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint("job_id", "page_number", name="uq_qgen_job_pages_job_page"),
    )
    op.create_index("ix_qgen_job_pages_job_id", "qgen_job_pages", ["job_id"])
    op.create_index(
        "ix_qgen_job_pages_job_status", "qgen_job_pages", ["job_id", "status"]
    )


def downgrade() -> None:
    op.drop_table("qgen_job_pages")
    op.drop_table("qgen_jobs")
