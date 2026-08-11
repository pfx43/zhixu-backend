"""为用户笔记增加软删除字段

Revision ID: 20260805_note_soft_delete
Revises: 20260802_note_revision
Create Date: 2026-08-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_note_soft_delete"
down_revision = "20260802_note_revision"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("user_notes"):
        return

    column_names = {
        column["name"] for column in inspector.get_columns("user_notes")
    }

    if "deleted_at" not in column_names:
        op.add_column(
            "user_notes",
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )

    if "deleted_by_revision" not in column_names:
        op.add_column(
            "user_notes",
            sa.Column("deleted_by_revision", sa.Integer(), nullable=True),
        )

    # 为回收站查询创建复合索引
    index_names = {idx["name"] for idx in inspector.get_indexes("user_notes")}
    if "ix_user_notes_user_deleted" not in index_names:
        op.create_index(
            "ix_user_notes_user_deleted",
            "user_notes",
            ["user_id", "deleted_at"],
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("user_notes"):
        return

    index_names = {idx["name"] for idx in inspector.get_indexes("user_notes")}
    if "ix_user_notes_user_deleted" in index_names:
        op.drop_index("ix_user_notes_user_deleted", table_name="user_notes")

    column_names = {
        column["name"] for column in inspector.get_columns("user_notes")
    }

    with op.batch_alter_table("user_notes") as batch_op:
        if "deleted_by_revision" in column_names:
            batch_op.drop_column("deleted_by_revision")
        if "deleted_at" in column_names:
            batch_op.drop_column("deleted_at")