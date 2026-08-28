"""goal_evidence_events 表（Issue #38 Evidence Impact 独立契约）

Revision ID: 20260827_goal_evidence
Revises: 20260827_cover_and_note_anchor
Create Date: 2026-08-27 20:50:00.000000

目标详情「证据变化」页的数据源：不复用 daily_tasks.evidence_json 冒充。
记录目标维度的前后值变化（source / node / before / after / scope / confirmation），
user_id 删号级联；goal_id 删除级联。
"""
from alembic import op
import sqlalchemy as sa


revision = "20260827_goal_evidence"
down_revision = "20260827_cover_and_note_anchor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # daily_tasks.evidence_json（Issue #31：完成时落证据；幂等可重复执行）
    daily_cols = {c["name"] for c in inspector.get_columns("daily_tasks")} if inspector.has_table("daily_tasks") else set()
    if "evidence_json" not in daily_cols:
        op.add_column("daily_tasks", sa.Column("evidence_json", sa.JSON(), nullable=True))

    if inspector.has_table("goal_evidence_events"):
        return

    op.create_table(
        "goal_evidence_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "goal_id",
            sa.Integer(),
            sa.ForeignKey("goals.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("node_id", sa.String(100), nullable=True),
        sa.Column("node_label", sa.String(255), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("scope", sa.String(120), nullable=False, server_default="goal"),
        sa.Column(
            "confirmation", sa.String(20), nullable=False, server_default="pending"
        ),
    )
    op.create_index(
        "ix_goal_evidence_goal_time",
        "goal_evidence_events",
        ["goal_id", "occurred_at"],
    )
    op.create_index("ix_goal_evidence_user", "goal_evidence_events", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("goal_evidence_events"):
        op.drop_table("goal_evidence_events")
    daily_cols = {c["name"] for c in inspector.get_columns("daily_tasks")} if inspector.has_table("daily_tasks") else set()
    if "evidence_json" in daily_cols:
        op.drop_column("daily_tasks", "evidence_json")
