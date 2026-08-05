"""新增笔记附件表

Revision ID: 20260805_note_attachments
Revises: 20260805_note_soft_delete
Create Date: 2026-08-05 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_note_attachments"
down_revision = "20260805_note_soft_delete"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("note_attachments"):
        return

    op.create_table(
        "note_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("note_id", sa.String(36), sa.ForeignKey("user_notes.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.Column("note_revision", sa.Integer(), nullable=True),
    )

    for idx_name, idx_cols in [
        ("ix_note_attachments_note_revision", ["note_id", "note_revision"]),
        ("ix_note_attachments_checksum", ["checksum"]),
    ]:
        existing = {i["name"] for i in inspector.get_indexes("note_attachments")}
        if idx_name not in existing:
            op.create_index(idx_name, "note_attachments", idx_cols)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("note_attachments"):
        return

    with op.batch_alter_table("note_attachments") as batch_op:
        for fk in inspector.get_foreign_keys("note_attachments"):
            batch_op.drop_constraint(fk["name"], type_="foreignkey")

    op.drop_table("note_attachments")