"""notifications / reminders / profile_graphs + tip 回源父会话（#28 #36 #37 #39）

Revision ID: 20260828_notif_remind_profile
Revises: 20260827_goal_evidence
Create Date: 2026-08-28 00:00:00.000000

- 新建 notifications / reminders / profile_graphs / profile_inferences 四张表
- user_notes 增加 source_session_id（#39 回源契约的父会话字段；
  划选锚点 page_number/char_start/char_end/source_ref_type/source_ref_id
  已由 #29 的 20260827_cover_and_note_anchor 提供，这里不再重复）
所有操作带存在性检查，幂等可重放。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260828_notif_remind_profile"
down_revision = "20260827_goal_evidence"
branch_labels = None
depends_on = None


def _column_names(inspector, table: str) -> set:
    return {c["name"] for c in inspector.get_columns(table)}


def _has_table(inspector, table: str) -> bool:
    return inspector.has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── user_notes：回源父会话（#39；锚点列由 #29 迁移提供） ──
    if _has_table(inspector, "user_notes"):
        cols = _column_names(inspector, "user_notes")
        if "source_session_id" not in cols:
            op.add_column(
                "user_notes",
                sa.Column("source_session_id", sa.String(length=64), nullable=True),
            )

    # ── notifications ──
    if not _has_table(inspector, "notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
        op.create_index(op.f("ix_notifications_user_read"), "notifications", ["user_id", "read_at"], unique=False)

    # ── reminders ──
    if not _has_table(inspector, "reminders"):
        op.create_table(
            "reminders",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("trigger_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("repeat_rule", sa.String(length=32), nullable=True),
            sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(op.f("ix_reminders_user_id"), "reminders", ["user_id"], unique=False)
        op.create_index(op.f("ix_reminders_user_trigger"), "reminders", ["user_id", "trigger_at"], unique=False)

    # ── profile_graphs（画像图谱：基于 user/goal/document/tag） ──
    if not _has_table(inspector, "profile_graphs"):
        op.create_table(
            "profile_graphs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("version", sa.Integer(), server_default="1", nullable=False),
            sa.Column("graph_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(op.f("ix_profile_graphs_user_id"), "profile_graphs", ["user_id"], unique=False)

    # ── profile_inferences（画像推断任务：start/status/result，执行器见 #37） ──
    if not _has_table(inspector, "profile_inferences"):
        op.create_table(
            "profile_inferences",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("graph_id", sa.String(length=36), sa.ForeignKey("profile_graphs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
            sa.Column("trigger", sa.String(length=32), server_default="manual", nullable=False),
            sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(op.f("ix_profile_inferences_user_id"), "profile_inferences", ["user_id"], unique=False)
        op.create_index(op.f("ix_profile_inferences_status"), "profile_inferences", ["status"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in ("profile_inferences", "profile_graphs", "reminders", "notifications"):
        if _has_table(inspector, table):
            op.drop_table(table)

    if _has_table(inspector, "user_notes"):
        cols = _column_names(inspector, "user_notes")
        # 只回收本迁移新增的 source_session_id；锚点列属 #29 迁移，不在此降级
        if "source_session_id" in cols:
            op.drop_column("user_notes", "source_session_id")
