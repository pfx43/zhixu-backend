"""添加用量表 usage_daily / usage_token

Revision ID: 20260807_add_usage_tables
Revises: 20260805_add_note_soft_delete
Create Date: 2026-08-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_add_usage_tables"
down_revision = "20260805_add_note_soft_delete"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── usage_daily ──
    if not inspector.has_table("usage_daily"):
        op.create_table(
            "usage_daily",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("api_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.PrimaryKeyConstraint("user_id", "date"),
        )
        op.create_index(
            "idx_usage_daily_user_date",
            "usage_daily",
            ["user_id", "date"],
        )

    # ── usage_token ──
    if not inspector.has_table("usage_token"):
        op.create_table(
            "usage_token",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("yyyymm", sa.String(6), nullable=False),
            sa.Column("prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("completion_tokens", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default="0"),
            sa.PrimaryKeyConstraint("user_id", "yyyymm"),
        )
        op.create_index(
            "idx_usage_token_user_yyyymm",
            "usage_token",
            ["user_id", "yyyymm"],
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("usage_daily"):
        op.drop_index("idx_usage_daily_user_date", table_name="usage_daily")
        op.drop_table("usage_daily")

    if inspector.has_table("usage_token"):
        op.drop_index("idx_usage_token_user_yyyymm", table_name="usage_token")
        op.drop_table("usage_token")
