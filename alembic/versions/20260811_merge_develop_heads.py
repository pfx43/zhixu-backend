"""合并 develop 的三个迁移头（question_fallbacks / note_attachments / usage_tables）

Revision ID: 20260811_merge_develop_heads
Revises: 20260804_question_fallbacks, 20260805_note_attachments, 20260807_add_usage_tables
Create Date: 2026-08-11 00:00:00.000000

纯收敛节点：无 DDL。保证从任何已部署 revision 状态 upgrade 到 head 时，
alembic 会回溯补跑缺失的父链（例如旧链已部署到 20260807_add_usage_tables
的库会自动补跑 20260804_question_fallbacks / 20260805_note_attachments）。
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_merge_develop_heads"
down_revision = (
    "20260804_question_fallbacks",
    "20260805_note_attachments",
    "20260807_add_usage_tables",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
