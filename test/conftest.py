"""pytest configuration — adds backend/ to sys.path so all tests can import app.* modules."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_TEST_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

load_dotenv(_BACKEND_DIR / ".env")

# 测试专用开关：测试后门 token 与内部健康检查 key（生产环境不得设置）
os.environ.setdefault("ALLOW_TEST_TOKEN", "1")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")
# 测试环境保留 /openapi.json（契约测试依赖）；生产不设置，文档仍关闭
os.environ.setdefault("ENABLE_OPENAPI", "1")

from pgutil import TEST_SCHEMA, ensure_test_schema, with_search_path  # noqa: E402


def _configure_test_database() -> None:
    explicit = os.environ.get("TEST_DATABASE_URL", "").strip()
    url = explicit or os.environ.get("DATABASE_URL", "").strip()
    scheme = url.split("://", 1)[0].lower() if url else ""
    if not scheme.startswith("postgresql"):
        raise RuntimeError(
            "测试需要 PostgreSQL。请设置 DATABASE_URL 或 TEST_DATABASE_URL，例如 "
            "postgresql+psycopg2://zhixu:password@127.0.0.1:5432/zhixu"
            f"（单测使用独立 schema `{TEST_SCHEMA}`，不写 public 业务表）。"
        )
    ensure_test_schema(url)
    test_url = with_search_path(url)
    os.environ["DATABASE_URL"] = test_url
    os.environ["TEST_DATABASE_URL"] = test_url


_configure_test_database()
