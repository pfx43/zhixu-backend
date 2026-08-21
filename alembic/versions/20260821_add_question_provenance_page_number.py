"""question_provenance 增加 page_number（题目来源页码）

Revision ID: 20260821_question_provenance_page_number
Revises: 20260811_merge_develop_heads
Create Date: 2026-08-21 00:00:00.000000

按页出题 / 提取落库时必须写入页码（issue #17）。旧数据允许 NULL，
新写入的题目会带 page_number。页列表据此返回每页 question_count，
今日任务检查器据此判断「这些页上已经有题」。
"""

from alembic import op
import sqlalchemy as sa


revision = "20260821_question_page_number"
down_revision = "20260811_merge_develop_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("question_provenance")}

    if "page_number" not in columns:
        op.add_column(
            "question_provenance",
            sa.Column("page_number", sa.Integer(), nullable=True),
        )

    indexes = {ix["name"] for ix in inspector.get_indexes("question_provenance")}
    if "ix_question_provenance_doc_page" not in indexes:
        op.create_index(
            "ix_question_provenance_doc_page",
            "question_provenance",
            ["document_id", "page_number"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indexes = {ix["name"] for ix in inspector.get_indexes("question_provenance")}
    if "ix_question_provenance_doc_page" in indexes:
        op.drop_index("ix_question_provenance_doc_page", table_name="question_provenance")

    columns = {c["name"] for c in inspector.get_columns("question_provenance")}
    if "page_number" in columns:
        op.drop_column("question_provenance", "page_number")
