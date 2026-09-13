"""qgen_job_pages 增加 questions_created / questions_reused

Revision ID: 20260912_qgen_page_counts
Revises: 20260831_tcn_domains
Create Date: 2026-09-12 00:00:00.000000

SSE 出题改为入队给独立出题服务后，主进程靠轮询 QgenJobPage 进度向前端推送
page_complete / done，需要每页新建/复用题数。旧行默认 0。
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_qgen_page_counts"
down_revision = "20260831_tcn_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("qgen_job_pages"):
        return

    columns = {c["name"] for c in inspector.get_columns("qgen_job_pages")}

    if "questions_created" not in columns:
        op.add_column(
            "qgen_job_pages",
            sa.Column(
                "questions_created",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    if "questions_reused" not in columns:
        op.add_column(
            "qgen_job_pages",
            sa.Column(
                "questions_reused",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("qgen_job_pages"):
        return

    columns = {c["name"] for c in inspector.get_columns("qgen_job_pages")}
    if "questions_reused" in columns:
        op.drop_column("qgen_job_pages", "questions_reused")
    if "questions_created" in columns:
        op.drop_column("qgen_job_pages", "questions_created")
