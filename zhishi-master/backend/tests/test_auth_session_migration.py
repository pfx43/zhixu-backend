import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    inspect,
    text,
)

from app.core.database import Base
import app.models  # noqa: F401


BACKEND_ROOT = Path(__file__).resolve().parent.parent


def run_alembic_upgrade(database_url: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from alembic import command; "
                "from alembic.config import Config; "
                "command.upgrade(Config('alembic.ini'), 'head')"
            ),
        ],
        cwd=str(BACKEND_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_alembic_upgrade_creates_auth_sessions_table(tmp_path):
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    result = run_alembic_upgrade(database_url)

    assert result.returncode == 0, result.stdout + result.stderr
    inspector = inspect(create_engine(database_url))
    assert "auth_sessions" in inspector.get_table_names()
    assert {column["name"] for column in inspector.get_columns("auth_sessions")} == {
        "token_hash",
        "user_id",
        "expires_at",
        "created_at",
    }


def test_alembic_upgrade_adopts_existing_create_all_database(tmp_path):
    database_path = tmp_path / "existing.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            table
            for name, table in Base.metadata.tables.items()
            if name != "auth_sessions"
        ],
    )

    assert "onboarding_state" in inspect(engine).get_table_names()
    assert "auth_sessions" not in inspect(engine).get_table_names()

    result = run_alembic_upgrade(database_url)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "auth_sessions" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert revision == "20260802_note_revision"


def test_alembic_upgrade_adds_non_null_initial_revision_to_legacy_notes(tmp_path):
    """既有 SQLite 笔记原地获得可用的乐观锁基线。"""
    database_path = tmp_path / "legacy-notes.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    legacy_metadata = MetaData()
    users = Table("users", legacy_metadata, Column("id", Integer, primary_key=True))
    notes = Table(
        "user_notes",
        legacy_metadata,
        Column("id", String(36), primary_key=True),
        Column("user_id", Integer, nullable=False),
        Column("collection_id", String(36)),
        Column("title", String(255), nullable=False),
        Column("content_md", Text, nullable=False),
        Column("note_type", String(20), nullable=False),
    )
    legacy_metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(users.insert().values(id=1))
        connection.execute(
            notes.insert().values(
                id="legacy-note",
                user_id=1,
                title="历史笔记",
                content_md="历史内容",
                note_type="manual",
            )
        )

    result = run_alembic_upgrade(database_url)

    assert result.returncode == 0, result.stdout + result.stderr
    columns = {
        column["name"]: column
        for column in inspect(create_engine(database_url)).get_columns("user_notes")
    }
    assert columns["revision"]["nullable"] is False
    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT revision FROM user_notes WHERE id = 'legacy-note'")
        ).scalar_one()
    assert revision == 1
