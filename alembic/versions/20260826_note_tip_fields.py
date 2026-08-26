"""add note tip fields

Revision ID: 20260826_note_tip_fields
Revises: 20260826_daily_tasks
Create Date: 2026-08-26 00:00:00.000000

Issue #18 tip：不另起表，走 user_notes（note_type=tip）。
新增三列：
- tags：用户给短卡片打的类型（难词/易错点…），JSONB 数组，可按 @> 语义筛选；
  与题目/文档知识点 tag（global_questions.tags 等）分命名空间，不混用。
- document_id：关联哪本资料（可空，软引用，归属由应用层校验）。
- source：来源（tina / quiz / kb），列表可按来源筛选。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260826_note_tip_fields"
down_revision = "20260826_daily_tasks"
branch_labels = None
depends_on = None


def _column_names(inspector, table: str) -> set:
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("user_notes"):
        return
    columns = _column_names(inspector, "user_notes")

    if "tags" not in columns:
        op.add_column(
            "user_notes",
            sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    if "document_id" not in columns:
        op.add_column(
            "user_notes",
            sa.Column("document_id", sa.String(length=36), nullable=True),
        )
        indexes = {ix["name"] for ix in inspector.get_indexes("user_notes")}
        if "ix_user_notes_document_id" not in indexes:
            op.create_index(
                op.f("ix_user_notes_document_id"),
                "user_notes",
                ["document_id"],
                unique=False,
            )
    if "source" not in columns:
        op.add_column(
            "user_notes",
            sa.Column("source", sa.String(length=20), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("user_notes"):
        return
    columns = _column_names(inspector, "user_notes")

    if "document_id" in columns:
        indexes = {ix["name"] for ix in inspector.get_indexes("user_notes")}
        if "ix_user_notes_document_id" in indexes:
            op.drop_index(op.f("ix_user_notes_document_id"), table_name="user_notes")
        op.drop_column("user_notes", "document_id")
    if "source" in columns:
        op.drop_column("user_notes", "source")
    if "tags" in columns:
        op.drop_column("user_notes", "tags")
