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
    inspect,
    text,
)

from app.core.database import Base
import app.models  # noqa: F401
from pgutil import empty_test_engine, test_database_url as postgres_url


BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _create_all_except(engine, excluded: set[str]) -> None:
    Base.metadata.create_all(
        bind=engine,
        tables=[
            table
            for name, table in Base.metadata.tables.items()
            if name not in excluded
        ],
    )


def run_alembic_stamp(database_url: str, revision: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from alembic import command; "
                "from alembic.config import Config; "
                f"command.stamp(Config('alembic.ini'), {revision!r})"
            ),
        ],
        cwd=str(BACKEND_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def run_alembic_upgrade(database_url: str, revision: str = "head") -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from alembic import command; "
                "from alembic.config import Config; "
                f"command.upgrade(Config('alembic.ini'), {revision!r})"
            ),
        ],
        cwd=str(BACKEND_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_alembic_upgrade_creates_auth_sessions_table():
    database_url = postgres_url()
    engine = empty_test_engine()
    try:
        _create_all_except(engine, {"auth_sessions"})
        result = run_alembic_upgrade(database_url)
        assert result.returncode == 0, result.stdout + result.stderr
        inspector = inspect(engine)
        assert "auth_sessions" in inspector.get_table_names()
        assert {column["name"] for column in inspector.get_columns("auth_sessions")} == {
            "token_hash",
            "user_id",
            "expires_at",
            "created_at",
        }
    finally:
        engine.dispose()


def test_alembic_upgrade_adopts_existing_create_all_database():
    database_url = postgres_url()
    engine = empty_test_engine()
    try:
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
        assert revision == "20260822_segment_pages_toc"
    finally:
        engine.dispose()


def test_alembic_upgrade_from_legacy_chain_backfills_missing_branches():
    """旧链已部署到 20260805_note_soft_delete 的库，升级 head 后自动补跑
    note_attachments / usage 分支，不被旧 alembic_version 跳过。"""
    database_url = postgres_url()
    engine = empty_test_engine()
    try:
        _create_all_except(engine, {"note_attachments", "usage_daily", "usage_token"})
        stamped = run_alembic_stamp(database_url, "20260805_note_soft_delete")
        assert stamped.returncode == 0, stamped.stdout + stamped.stderr
        first = run_alembic_upgrade(database_url, revision="20260805_note_soft_delete")
        assert first.returncode == 0, first.stdout + result_err(first)
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "20260805_note_soft_delete"
        assert "note_attachments" not in inspect(engine).get_table_names()
        assert "usage_daily" not in inspect(engine).get_table_names()

        second = run_alembic_upgrade(database_url)
        assert second.returncode == 0, second.stdout + second.stderr
        tables = inspect(engine).get_table_names()
        assert "note_attachments" in tables
        assert "usage_daily" in tables
        assert "usage_token" in tables
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        assert revision == "20260822_segment_pages_toc"
    finally:
        engine.dispose()


def result_err(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def test_alembic_upgrade_adds_non_null_initial_revision_to_legacy_notes():
    """既有笔记原地获得可用的乐观锁基线。"""
    database_url = postgres_url()
    engine = empty_test_engine()
    try:
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
            for column in inspect(engine).get_columns("user_notes")
        }
        assert columns["revision"]["nullable"] is False
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT revision FROM user_notes WHERE id = 'legacy-note'")
            ).scalar_one()
        assert revision == 1
    finally:
        engine.dispose()