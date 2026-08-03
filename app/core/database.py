from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import SQLALCHEMY_DATABASE_URL, _DEFAULT_SQLITE_PATH, _REPO_ROOT

_is_sqlite = SQLALCHEMY_DATABASE_URL.startswith("sqlite")

_engine_kwargs: dict = {"echo": False}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_recycle"] = 3600

engine = create_engine(SQLALCHEMY_DATABASE_URL, **_engine_kwargs)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db():
    """创建全部 ORM 表。S1 使用 create_all；后续团队环境可改用 Alembic migration。"""
    if _is_sqlite:
        db_path = _DEFAULT_SQLITE_PATH
        if SQLALCHEMY_DATABASE_URL.startswith("sqlite:///"):
            url_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "", 1)
            if url_path and url_path != ":memory:":
                candidate = Path(url_path)
                if not candidate.is_absolute():
                    candidate = (_REPO_ROOT / candidate).resolve()
                db_path = candidate
        db_path.parent.mkdir(parents=True, exist_ok=True)

    import app.models  # noqa: F401 — 注册全部 model 到 Base.metadata

    Base.metadata.create_all(bind=engine)
