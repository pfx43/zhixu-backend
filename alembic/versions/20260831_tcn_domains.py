"""tcn_domains 封闭学科名单 + documents.tcn_domain

Revision ID: 20260831_tcn_domains
Revises: 20260830_user_storage
Create Date: 2026-08-31 09:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260831_tcn_domains"
down_revision = "20260830_user_storage"
branch_labels = None
depends_on = None

_SEED = (
    ("higher_math", "高等数学"),
    ("math", "数学"),
    ("physics", "物理"),
    ("discrete_math", "离散数学"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("tcn_domains"):
        op.create_table(
            "tcn_domains",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("label", sa.String(100), nullable=False),
        )

    domains = sa.table(
        "tcn_domains",
        sa.column("id", sa.String),
        sa.column("label", sa.String),
    )
    existing = {
        row[0]
        for row in bind.execute(sa.text("SELECT id FROM tcn_domains")).fetchall()
    }
    for domain_id, label in _SEED:
        if domain_id not in existing:
            bind.execute(domains.insert().values(id=domain_id, label=label))

    if inspector.has_table("documents"):
        doc_cols = {c["name"] for c in inspector.get_columns("documents")}
    else:
        doc_cols = set()
    if inspector.has_table("documents") and "tcn_domain" not in doc_cols:
        op.add_column(
            "documents",
            sa.Column("tcn_domain", sa.String(64), nullable=True),
        )
        op.create_foreign_key(
            "fk_documents_tcn_domain",
            "documents",
            "tcn_domains",
            ["tcn_domain"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    doc_cols = (
        {c["name"] for c in inspector.get_columns("documents")}
        if inspector.has_table("documents")
        else set()
    )
    if "tcn_domain" in doc_cols:
        op.drop_constraint("fk_documents_tcn_domain", "documents", type_="foreignkey")
        op.drop_column("documents", "tcn_domain")
    if inspector.has_table("tcn_domains"):
        op.drop_table("tcn_domains")
