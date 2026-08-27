"""add document cover + note anchor fields

Revision ID: 20260827_cover_and_note_anchor
Revises: 20260826_note_tip_fields
Create Date: 2026-08-27 00:00:00.000000

#40 资料封面：
- global_documents 新增 cover_storage_path / thumbnail_storage_path（PDF 首页渲染图落盘路径）。
#29 tip 划选锚点：
- user_notes 新增 page_number / char_start / char_end / source_ref_id / source_ref_type。
"""
from alembic import op
import sqlalchemy as sa


revision = "20260827_cover_and_note_anchor"
down_revision = "20260826_note_tip_fields"
branch_labels = None
depends_on = None


def _column_names(inspector, table: str) -> set:
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # #40 封面列
    if inspector.has_table("global_documents"):
        columns = _column_names(inspector, "global_documents")
        if "cover_storage_path" not in columns:
            op.add_column(
                "global_documents",
                sa.Column("cover_storage_path", sa.String(length=512), nullable=True),
            )
        if "thumbnail_storage_path" not in columns:
            op.add_column(
                "global_documents",
                sa.Column("thumbnail_storage_path", sa.String(length=512), nullable=True),
            )

    # #29 tip 锚点字段
    if inspector.has_table("user_notes"):
        columns = _column_names(inspector, "user_notes")
        if "page_number" not in columns:
            op.add_column(
                "user_notes",
                sa.Column("page_number", sa.Integer(), nullable=True),
            )
        if "char_start" not in columns:
            op.add_column(
                "user_notes",
                sa.Column("char_start", sa.Integer(), nullable=True),
            )
        if "char_end" not in columns:
            op.add_column(
                "user_notes",
                sa.Column("char_end", sa.Integer(), nullable=True),
            )
        if "source_ref_id" not in columns:
            op.add_column(
                "user_notes",
                sa.Column("source_ref_id", sa.String(length=64), nullable=True),
            )
        if "source_ref_type" not in columns:
            op.add_column(
                "user_notes",
                sa.Column("source_ref_type", sa.String(length=20), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("global_documents"):
        columns = _column_names(inspector, "global_documents")
        if "thumbnail_storage_path" in columns:
            op.drop_column("global_documents", "thumbnail_storage_path")
        if "cover_storage_path" in columns:
            op.drop_column("global_documents", "cover_storage_path")

    if inspector.has_table("user_notes"):
        columns = _column_names(inspector, "user_notes")
        if "source_ref_type" in columns:
            op.drop_column("user_notes", "source_ref_type")
        if "source_ref_id" in columns:
            op.drop_column("user_notes", "source_ref_id")
        if "char_end" in columns:
            op.drop_column("user_notes", "char_end")
        if "char_start" in columns:
            op.drop_column("user_notes", "char_start")
        if "page_number" in columns:
            op.drop_column("user_notes", "page_number")