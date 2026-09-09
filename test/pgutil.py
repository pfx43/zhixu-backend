"""PostgreSQL 测试辅助。表建在独立 schema `pytest` 里，不碰业务库的 public。"""
from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

TEST_SCHEMA = "pytest"


def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("TEST_DATABASE_URL 未设置；pytest 应从 conftest 写入。")
    return url


def with_search_path(url: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={TEST_SCHEMA}"
    return urlunparse(parsed._replace(query=urlencode(query)))


def reset_test_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{TEST_SCHEMA}" CASCADE'))
        conn.execute(text(f'CREATE SCHEMA "{TEST_SCHEMA}"'))
        conn.execute(text(f'SET search_path TO "{TEST_SCHEMA}"'))


def empty_test_engine() -> Engine:
    engine = create_engine(test_database_url(), pool_pre_ping=True)
    reset_test_schema(engine)
    return engine


def make_sessionmaker():
    from app.core.database import Base
    import app.models  # noqa: F401

    engine = empty_test_engine()
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    seed = SessionLocal()
    try:
        from app.services.tcn.domains import ensure_tcn_domains

        ensure_tcn_domains(seed)
        seed.commit()
    finally:
        seed.close()
    return engine, SessionLocal


def ensure_test_schema(url: str) -> None:
    """用无 search_path 的连接创建 schema（连的是 public，只建 schema，不改表）。"""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.pop("options", None)
    admin_url = urlunparse(parsed._replace(query=urlencode(query)))
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{TEST_SCHEMA}"'))
    finally:
        engine.dispose()
