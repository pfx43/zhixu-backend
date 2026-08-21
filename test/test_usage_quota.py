"""用量记账与配额开关测试 — QUOTA_ENFORCE、业务日时区、方言兼容。"""
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from pgutil import make_sessionmaker

from app.api import deps_quota
from app.services import usage_service
from app.crud import crud


# ── check_quota 开关 ──

def test_check_quota_passthrough_when_disabled():
    """QUOTA_ENFORCE=false：即使已超限也直接放行，不查 usage、不抛 429。"""
    user = {"user_id": 1, "api_limit_daily": 10, "token_limit_monthly": 10000}
    db = MagicMock()
    with patch.object(deps_quota, "QUOTA_ENFORCE", False):
        with patch.object(deps_quota, "get_daily_api_calls") as daily, \
             patch.object(deps_quota, "get_monthly_token_usage") as monthly:
            result = deps_quota.check_quota(current_user=user, db=db)
    assert result == user
    daily.assert_not_called()
    monthly.assert_not_called()


def test_enforce_quota_for_user_skips_db_when_disabled():
    """SSE 配额入口在开关关闭时不打开 Session。"""
    user = {"user_id": 1, "api_limit_daily": 10, "token_limit_monthly": 10000}
    with patch.object(deps_quota, "QUOTA_ENFORCE", False), \
         patch.object(deps_quota, "short_session") as session_cm, \
         patch.object(deps_quota, "get_daily_api_calls") as daily:
        deps_quota.enforce_quota_for_user(user)
    session_cm.assert_not_called()
    daily.assert_not_called()


# ── 业务日时区 ──

class _FakeDatetime:
    """固定时刻：2026-08-10 17:00 UTC == 北京时间 2026-08-11 01:00。"""

    _fixed = datetime(2026, 8, 10, 17, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return cls._fixed.astimezone(tz)
        return cls._fixed


def test_business_day_uses_app_timezone():
    with patch.object(usage_service, "datetime", _FakeDatetime):
        assert usage_service._today() == date(2026, 8, 11)  # 北京时间已跨日
        assert usage_service._current_yyyymm() == "202608"


# ── record_turn_usage 计数（PostgreSQL 测试库） ──

def _session_factory():
    _engine, SessionLocal = make_sessionmaker()
    return SessionLocal


def test_record_turn_usage_accumulates_daily_and_monthly():
    SessionLocal = _session_factory()
    with SessionLocal() as db:
        usage_service.record_turn_usage(
            1, prompt="你好", completion="回答", total_tokens=100, db=db
        )
        usage_service.record_turn_usage(
            1, prompt="你好2", completion="回答2", total_tokens=200, db=db
        )
        assert usage_service.get_daily_api_calls(1, db) == 2
        assert usage_service.get_monthly_token_usage(1, db) == 300

        # 不同用户隔离
        assert usage_service.get_daily_api_calls(2, db) == 0


def test_upsert_sql_postgres():
    assert "ON CONFLICT" in usage_service._upsert_sql("usage_daily")
    assert "ON CONFLICT" in usage_service._upsert_sql("usage_token")
    assert "ON DUPLICATE KEY UPDATE" not in usage_service._upsert_sql("usage_daily")


# ── 配额查询（PostgreSQL） ──

def test_get_user_with_plan_details_v2_runs_on_postgres():
    SessionLocal = _session_factory()
    with SessionLocal() as db:
        from app.models import User
        u = User(
            email="quota@example.com",
            password_hash="hash",
            nickname="quota",
            is_active=True,
            plan_level=0,
        )
        db.add(u)
        db.commit()

        result = crud.get_user_with_plan_details_v2(db, u.id)
    assert result is not None
    assert result["email"] == "quota@example.com"
    assert "days_remaining" in result
