"""添加 document_segments 页码列 + document_tocs 章节目录表

Revision ID: 20260822_segment_pages_toc
Revises: 20260821_question_page_number
Create Date: 2026-08-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260822_segment_pages_toc"
down_revision = "20260821_question_page_number"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── document_segments 页码列 ──
    seg_cols = {c["name"] for c in inspector.get_columns("document_segments")}
    if "page_start" not in seg_cols:
        op.add_column(
            "document_segments",
            sa.Column("page_start", sa.Integer(), nullable=True),
        )
    if "page_end" not in seg_cols:
        op.add_column(
            "document_segments",
            sa.Column("page_end", sa.Integer(), nullable=True),
        )

    # ── document_tocs ──
    if not inspector.has_table("document_tocs"):
        op.create_table(
            "document_tocs",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("document_id", sa.String(36), nullable=False),
            sa.Column("order_index", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("page_start", sa.Integer(), nullable=False),
            sa.Column("page_end", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "document_id", "order_index", name="uq_document_tocs_doc_order"
            ),
        )
        op.create_index(
            "ix_document_tocs_document", "document_tocs", ["document_id"]
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("document_tocs"):
        op.drop_index("ix_document_tocs_document", table_name="document_tocs")
        op.drop_table("document_tocs")

    seg_cols = {c["name"] for c in inspector.get_columns("document_segments")}
    if "page_start" in seg_cols:
        op.drop_column("document_segments", "page_start")
    if "page_end" in seg_cols:
        op.drop_column("document_segments", "page_end")