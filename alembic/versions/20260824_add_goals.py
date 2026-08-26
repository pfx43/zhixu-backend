"""add goals table

Revision ID: 20260824_goals
Revises: 20260821_question_page_number
Create Date: 2026-08-24 00:00:00.000000

Issue #15 Goal：长期目标表（一人一条 active）。
字段：user_id（CASCADE 级联删号）、text（那句话）、attributes（科目/资料类等 JSON）、
valid_until（有效期）、status（active/paused/completed）、时间戳。
"""

from alembic import op
import sqlalchemy as sa


revision = "20260824_goals"
down_revision = "20260822_segment_pages_toc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("goals"):
        return

    op.create_table(
        "goals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_goals_user_id"), "goals", ["user_id"], unique=False)
    op.create_index(op.f("ix_goals_status"), "goals", ["status"], unique=False)
    op.create_index(
        "ix_goals_user_status",
        "goals",
        ["user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("goals"):
        return

    indexes = {ix["name"] for ix in inspector.get_indexes("goals")}
    if "ix_goals_user_status" in indexes:
        op.drop_index("ix_goals_user_status", table_name="goals")
    if "ix_goals_status" in indexes:
        op.drop_index(op.f("ix_goals_status"), table_name="goals")
    if "ix_goals_user_id" in indexes:
        op.drop_index(op.f("ix_goals_user_id"), table_name="goals")

    op.drop_table("goals")
