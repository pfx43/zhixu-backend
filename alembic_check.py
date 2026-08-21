import sqlalchemy as sa

import app.core.config as cfg
import app.core.database as db

engine = db.engine
print("DATABASE_URL=", cfg.SQLALCHEMY_DATABASE_URL)
with engine.connect() as conn:
    result = conn.execute(
        sa.text(
            "SELECT tablename FROM pg_catalog.pg_tables "
            "WHERE schemaname = 'public' ORDER BY tablename"
        )
    )
    tables = [row[0] for row in result]
    print("TABLES =", tables)
    if "alembic_version" in tables:
        ver = conn.execute(sa.text("SELECT version_num FROM alembic_version")).fetchall()
        print("ALEMBIC_VERSION =", ver)
    else:
        print("ALEMBIC_VERSION table missing")
