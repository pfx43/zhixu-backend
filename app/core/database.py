import json as _json
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import SQLALCHEMY_DATABASE_URL, _DEFAULT_SQLITE_PATH, _REPO_ROOT

_is_sqlite = SQLALCHEMY_DATABASE_URL.startswith("sqlite")

# 从 config.json 读取数据库连接池参数（有默认值兜底）
_pool_size = 5
_pool_max_overflow = 10
_pool_recycle = 3600
try:
    _cfg_path = _REPO_ROOT / "config.json"
    if _cfg_path.exists():
        with open(_cfg_path, "r", encoding="utf-8") as _f:
            _cfg = _json.load(_f)
        _db_cfg = _cfg.get("database", {})
        _pool_size = int(_db_cfg.get("pool_size", 5))
        _pool_max_overflow = int(_db_cfg.get("max_overflow", 10))
        _pool_recycle = int(_db_cfg.get("pool_recycle", 3600))
except Exception:
    pass

_engine_kwargs: dict = {"echo": False}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs.update({
        "pool_size": _pool_size,
        "max_overflow": _pool_max_overflow,
        "pool_pre_ping": True,
        "pool_recycle": _pool_recycle,
    })

    # 生产环境禁止默默回落 SQLite
    _is_postgresql = SQLALCHEMY_DATABASE_URL.startswith("postgresql")
    if _is_postgresql and "localhost" not in SQLALCHEMY_DATABASE_URL and "127.0.0.1" not in SQLALCHEMY_DATABASE_URL:
        import os
        if os.getenv("CACHE_BACKEND", "memory") == "memory":
            import warnings
            warnings.warn(
                "检测到远端 PostgreSQL 但 CACHE_BACKEND 不是 redis，"
                "多 worker 部署下会导致登录态分裂。",
                RuntimeWarning,
            )

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
