import json as _json
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import SQLALCHEMY_DATABASE_URL, _REPO_ROOT

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

_engine_kwargs: dict = {
    "echo": False,
    "pool_size": _pool_size,
    "max_overflow": _pool_max_overflow,
    "pool_pre_ping": True,
    "pool_recycle": _pool_recycle,
}

if "localhost" not in SQLALCHEMY_DATABASE_URL and "127.0.0.1" not in SQLALCHEMY_DATABASE_URL:
    import os
    if os.getenv("CACHE_BACKEND", "memory") == "memory":
        import warnings
        warnings.warn(
            "检测到远端 PostgreSQL 但 CACHE_BACKEND 不是 redis，"
            "多 worker 部署下会导致登录态分裂。",
            RuntimeWarning,
        )

engine = create_engine(SQLALCHEMY_DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def short_session():
    """独立于请求 DI 的短 Session：用完即关。

    供 SSE 期间的检索 / citation 使用，避免把 Depends(get_db) 活到流结束，
    也避免 Tina 把同步工具丢进线程时复用请求级 Session。
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# ── 异步引擎（PostgreSQL + asyncpg） ──
import re as _re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def _asyncpg_url_and_connect_args(sync_url: str) -> tuple[str, dict]:
    """psycopg2 的 options=-csearch_path=… 不能原样传给 asyncpg。"""
    async_url = _re.sub(
        r"^postgresql(?:\+\w+)?://",
        "postgresql+asyncpg://",
        sync_url,
        count=1,
    )
    parsed = urlparse(async_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    connect_args: dict = {}
    options = query.pop("options", "") or ""
    settings: dict[str, str] = {}
    for token in options.replace("-c", " ").split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip()
        if key:
            settings[key] = value.strip().strip('"')
    if settings:
        connect_args["server_settings"] = settings
    clean = urlunparse(parsed._replace(query=urlencode(query)))
    return clean, connect_args


_async_url, _async_connect_args = _asyncpg_url_and_connect_args(SQLALCHEMY_DATABASE_URL)

try:
    async_engine = create_async_engine(
        _async_url,
        connect_args=_async_connect_args,
        **_engine_kwargs,
    )
    AsyncSessionLocal = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
except Exception as _async_engine_err:
    import warnings as _w
    _w.warn(
        f"asyncpg 异步引擎初始化失败（测试/开发可忽略，生产需要 asyncpg）：{_async_engine_err}",
        RuntimeWarning,
    )
    async_engine = None
    AsyncSessionLocal = None


@asynccontextmanager
async def async_short_session():
    if AsyncSessionLocal is None:
        raise RuntimeError("异步会话不可用：请先安装 asyncpg 并配置 PostgreSQL 异步连接")
    db = AsyncSessionLocal()
    try:
        yield db
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()

Base = declarative_base()


def init_db():
    """创建全部 ORM 表。S1 使用 create_all；后续团队环境可改用 Alembic migration。"""
    import app.models  # noqa: F401 — 注册全部 model 到 Base.metadata

    Base.metadata.create_all(bind=engine)
