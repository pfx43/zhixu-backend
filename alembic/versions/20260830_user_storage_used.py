"""users.storage_used_bytes — 每用户资料占用

Revision ID: 20260830_user_storage
Revises: 20260829_qgen_jobs
Create Date: 2026-08-30 18:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260830_user_storage"
down_revision = "20260829_qgen_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "storage_used_bytes" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "storage_used_bytes",
                sa.BigInteger(),
                nullable=False,
                server_default="0",
            ),
        )

    op.execute(
        """
        UPDATE users SET storage_used_bytes = (
            COALESCE((
                SELECT COALESCE(SUM(g.file_size), 0)
                FROM documents d
                JOIN global_documents g ON d.global_document_id = g.id
                WHERE d.user_id = users.id
            ), 0)
            +
            COALESCE((
                SELECT COALESCE(SUM(sz), 0)
                FROM (
                    SELECT MAX(a.file_size) AS sz
                    FROM note_attachments a
                    WHERE a.user_id = users.id
                    GROUP BY a.storage_path
                ) note_sizes
            ), 0)
        )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "storage_used_bytes" in columns:
        op.drop_column("users", "storage_used_bytes")
