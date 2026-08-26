"""backend contracts 5: cover/thumbnail + note anchor + task evidence + notifications/reminders/profile_graph

Revision ID: 20260827_backend_contracts_5
Revises: 20260826_note_tip_fields
Create Date: 2026-08-27 00:00:00.000000

Issue #5.X：前端已有、缺正式契约。本迁移集中补齐 schema：

- documents.cover_url / thumbnail_url：资料真实封面/缩略图
- user_notes 加 anchor：page_number / char_start / char_end / source_ref_type / source_ref_id
  tip 跨端锚点 + 回源（Tina 对话 / 刷题 / 资料阅读）
- daily_tasks.evidence_json：完成时记录来源（session_id/document_id/question_ids/before/after/completed_at）

新建三张表：
- notifications：服务端通知（顶栏入口 isNotificationsApiPublished）
- reminders：提醒 CRUD（顶栏入口 /reminders 本地 demo → 云端）
- profile_graphs + profile_inferences：画像任务与图谱（Profile 构建/图谱 isProfileApiPublished）

所有列/表操作检查存在性后再创建；down_revision 串接正确。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260827_backend_contracts_5"
down_revision = "20260826_note_tip_fields"
branch_labels = None
depends_on = None


def _column_names(inspector, table: str) -> set:
    return {c["name"] for c in inspector.get_columns(table)}


def _index_names(inspector, table: str) -> set:
    return {ix["name"] for ix in inspector.get_indexes(table)}


def _has_table(inspector, table: str) -> bool:
    return inspector.has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── documents 加 cover/thumbnail（可空，对已存在文档不强制）
    if _has_table(inspector, "documents"):
        cols = _column_names(inspector, "documents")
        if "cover_url" not in cols:
            op.add_column("documents", sa.Column("cover_url", sa.String(length=512), nullable=True))
        if "thumbnail_url" not in cols:
            op.add_column("documents", sa.Column("thumbnail_url", sa.String(length=512), nullable=True))

    # ── user_notes 加 tip 跨端锚点
    if _has_table(inspector, "user_notes"):
        cols = _column_names(inspector, "user_notes")
        if "page_number" not in cols:
            op.add_column("user_notes", sa.Column("page_number", sa.Integer(), nullable=True))
        if "char_start" not in cols:
            op.add_column("user_notes", sa.Column("char_start", sa.Integer(), nullable=True))
        if "char_end" not in cols:
            op.add_column("user_notes", sa.Column("char_end", sa.Integer(), nullable=True))
        if "source_ref_type" not in cols:
            op.add_column("user_notes", sa.Column("source_ref_type", sa.String(length=20), nullable=True))
        if "source_ref_id" not in cols:
            op.add_column("user_notes", sa.Column("source_ref_id", sa.String(length=64), nullable=True))

    # ── daily_tasks 加 evidence（完成时记录因果证据）
    if _has_table(inspector, "daily_tasks"):
        cols = _column_names(inspector, "daily_tasks")
        if "evidence_json" not in cols:
            op.add_column("daily_tasks", sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # ── notifications
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

    # ── reminders
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

    # ── profile_graphs（画像图谱：基于 book/tag/user）
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

    # ── profile_inferences（画像推断任务：start/status/result）
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

    if _has_table(inspector, "profile_inferences"):
        op.drop_table("profile_inferences")
    if _has_table(inspector, "profile_graphs"):
        op.drop_table("profile_graphs")
    if _has_table(inspector, "reminders"):
        op.drop_table("reminders")
    if _has_table(inspector, "notifications"):
        op.drop_table("notifications")

    if _has_table(inspector, "daily_tasks"):
        cols = _column_names(inspector, "daily_tasks")
        if "evidence_json" in cols:
            op.drop_column("daily_tasks", "evidence_json")

    if _has_table(inspector, "user_notes"):
        for col in ("page_number", "char_start", "char_end", "source_ref_type", "source_ref_id"):
            if col in _column_names(inspector, "user_notes"):
                op.drop_column("user_notes", col)

    if _has_table(inspector, "documents"):
        for col in ("thumbnail_url", "cover_url"):
            if col in _column_names(inspector, "documents"):
                op.drop_column("documents", col)