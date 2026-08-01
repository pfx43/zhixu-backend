"""add onboarding_state

Revision ID: xxxx_onboarding
Revises: REPLACE_WITH_DOWN_REVISION
Create Date: 2026-07-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260730_onboarding"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "onboarding_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("guide_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("current_step", sa.String(length=32), nullable=True),
        sa.Column("steps", sa.JSON(), nullable=True),
        sa.Column("channel_answer", sa.JSON(), nullable=True),
        sa.Column("profile_answer", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_onboarding_state_user_id"), "onboarding_state", ["user_id"], unique=False)
    op.create_index(op.f("ix_onboarding_state_status"), "onboarding_state", ["status"], unique=False)

def downgrade():
    op.drop_index(op.f("ix_onboarding_state_status"), table_name="onboarding_state")
    op.drop_index(op.f("ix_onboarding_state_user_id"), table_name="onboarding_state")
    op.drop_constraint("uq_onboarding_user", "onboarding_state", type_="unique")
    op.drop_table("onboarding_state")
