"""为用户笔记增加乐观锁 revision

Revision ID: 20260802_note_revision
Revises: 20260802_auth_sessions
Create Date: 2026-08-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_note_revision"
down_revision = "20260802_auth_sessions"
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
    if "revision" in column_names:
        return

    op.add_column(
        "user_notes",
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("user_notes"):
        return

    column_names = {
        column["name"] for column in inspector.get_columns("user_notes")
    }
    if "revision" not in column_names:
        return

    with op.batch_alter_table("user_notes") as batch_op:
        batch_op.drop_column("revision")
