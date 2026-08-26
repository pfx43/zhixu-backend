"""add daily_tasks table

Revision ID: 20260826_daily_tasks
Revises: 20260824_goals
Create Date: 2026-08-26 00:00:00.000000

Issue #19 今日任务表：用户、目标、哪一天、标题、理由、类型、payload、
完成规则、状态；user_id 删号级联；goal_id 删除置空。
"""
from alembic import op
import sqlalchemy as sa


revision = "20260826_daily_tasks"
down_revision = "20260824_goals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("daily_tasks"):
        return

    op.create_table(
        "daily_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "goal_id",
            sa.Integer(),
            sa.ForeignKey("goals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("task_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("completion_rule", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_daily_tasks_user_id"), "daily_tasks", ["user_id"], unique=False)
    op.create_index(op.f("ix_daily_tasks_goal_id"), "daily_tasks", ["goal_id"], unique=False)
    op.create_index(op.f("ix_daily_tasks_task_date"), "daily_tasks", ["task_date"], unique=False)
    op.create_index(op.f("ix_daily_tasks_task_type"), "daily_tasks", ["task_type"], unique=False)
    op.create_index(op.f("ix_daily_tasks_status"), "daily_tasks", ["status"], unique=False)
    op.create_index(
        "ix_daily_tasks_user_date",
        "daily_tasks",
        ["user_id", "task_date"],
        unique=False,
    )
    op.create_index(
        "ix_daily_tasks_user_status",
        "daily_tasks",
        ["user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("daily_tasks"):
        return

    indexes = {ix["name"] for ix in inspector.get_indexes("daily_tasks")}
    for name in (
        "ix_daily_tasks_user_date",
        "ix_daily_tasks_user_status",
        "ix_daily_tasks_user_id",
        "ix_daily_tasks_goal_id",
        "ix_daily_tasks_task_date",
        "ix_daily_tasks_task_type",
        "ix_daily_tasks_status",
    ):
        if name in indexes:
            op.drop_index(name, table_name="daily_tasks")

    op.drop_table("daily_tasks")
