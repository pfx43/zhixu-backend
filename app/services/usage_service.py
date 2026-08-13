"""
用量服务 — token 记账 & 配额查询
提供 record_turn_usage() 按日/月原子累加 API 调用次数和 token 消耗。
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import APP_TIMEZONE
from app.core.database import AsyncSessionLocal, SessionLocal
from app.models import AuthSession, User
from app.services.auth.auth_session_service import _utc_now, get_session_user, hash_token

logger = logging.getLogger(__name__)

_BUSINESS_TZ = ZoneInfo(APP_TIMEZONE)


# ── tiktoken 估算（可选依赖） ──
_tiktoken_encoding = None


def _get_tiktoken_encoding():
    """惰性加载 tiktoken 编码器，仅当需要估算时才加载。"""
    global _tiktoken_encoding
    if _tiktoken_encoding is not None:
        return _tiktoken_encoding
    try:
        import tiktoken
        _tiktoken_encoding = tiktoken.get_encoding("cl100k_base")
        logger.info("tiktoken 编码器已加载 (cl100k_base)")
    except Exception:
        logger.warning("tiktoken 不可用，token 估算将使用字符数粗略估算")
        _tiktoken_encoding = False  # 标记为已尝试但失败
    return _tiktoken_encoding


def _estimate_tokens(text: str) -> int:
    """估算文本 token 数：优先 tiktoken，降级字符数/2 粗略估算。"""
    if not text:
        return 0
    enc = _get_tiktoken_encoding()
    if enc and enc is not False:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    # 降级：中文约 1.5 字符/token，英文约 4 字符/token，取中值 ≈2
    return max(1, len(text) // 2)


def _current_yyyymm() -> str:
    """返回业务日所在年月字符串，如 '202608'（按 APP_TIMEZONE）。"""
    return datetime.now(_BUSINESS_TZ).strftime("%Y%m")


def _today() -> date:
    """返回业务日日期（按 APP_TIMEZONE）。"""
    return datetime.now(_BUSINESS_TZ).date()


def _upsert_sql(dialect: str, table: str) -> str:
    """按方言生成原子累加 upsert；SQLite/PostgreSQL 走 ON CONFLICT，MySQL 走 ON DUPLICATE KEY UPDATE。"""
    if dialect == "mysql":
        if table == "usage_token":
            return """
                INSERT INTO usage_token (user_id, yyyymm, prompt_tokens, completion_tokens, total_tokens)
                VALUES (:user_id, :yyyymm, :prompt, :completion, :total)
                ON DUPLICATE KEY UPDATE
                    prompt_tokens = usage_token.prompt_tokens + VALUES(prompt_tokens),
                    completion_tokens = usage_token.completion_tokens + VALUES(completion_tokens),
                    total_tokens = usage_token.total_tokens + VALUES(total_tokens)
                """
        return """
            INSERT INTO usage_daily (user_id, date, api_calls)
            VALUES (:user_id, :date, 1)
            ON DUPLICATE KEY UPDATE api_calls = usage_daily.api_calls + 1
            """
    if table == "usage_token":
        return """
            INSERT INTO usage_token (user_id, yyyymm, prompt_tokens, completion_tokens, total_tokens)
            VALUES (:user_id, :yyyymm, :prompt, :completion, :total)
            ON CONFLICT (user_id, yyyymm)
            DO UPDATE SET
                prompt_tokens = usage_token.prompt_tokens + :prompt,
                completion_tokens = usage_token.completion_tokens + :completion,
                total_tokens = usage_token.total_tokens + :total
            """
    return """
        INSERT INTO usage_daily (user_id, date, api_calls)
        VALUES (:user_id, :date, 1)
        ON CONFLICT (user_id, date)
        DO UPDATE SET api_calls = usage_daily.api_calls + 1
        """


# ── 公开 API ──


async def resolve_user_id_by_token(token: str) -> int:
    """客户端登录 token → user_id（异步 DB 访问）；token 为空或解析不到返回 0。

    供 RAGTools 等组件按客户端凭据动态绑定用户身份（反查逻辑唯一出处）。
    """
    if not token:
        return 0
    try:
        async with AsyncSessionLocal() as db:
            session = (
                await db.execute(
                    select(AuthSession).where(
                        AuthSession.token_hash == hash_token(token),
                        AuthSession.expires_at > _utc_now(),
                    )
                )
            ).scalar_one_or_none()
            if session is None:
                return 0
            user = await db.get(User, session.user_id)
            return user.id if user else 0
    except Exception:
        logger.exception("resolve_user_id_by_token 反查用户失败: token=<redacted>")
        return 0


async def record_usage_for_token(token: str, usage: dict) -> None:
    """按客户端登录 token 反查 user_id 并异步写入用量表。

    每次 LLM 调用（含 Agent 工具循环内每一轮）记录一条；token 为空、
    解析不到用户或记账失败均跳过，不阻塞生成。
    """
    user_id = await resolve_user_id_by_token(token)
    if not user_id:
        return
    try:
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        if total_tokens is None:
            total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

        yyyymm = _current_yyyymm()
        today = _today()

        async with AsyncSessionLocal() as db:
            dialect = db.bind.dialect.name
            token_sql = _upsert_sql(dialect, "usage_token")
            daily_sql = _upsert_sql(dialect, "usage_daily")
            await db.execute(
                text(token_sql),
                {
                    "user_id": user_id,
                    "yyyymm": yyyymm,
                    "prompt": prompt_tokens or 0,
                    "completion": completion_tokens or 0,
                    "total": total_tokens or 0,
                },
            )
            await db.execute(
                text(daily_sql),
                {"user_id": user_id, "date": today},
            )
            await db.commit()
    except Exception:
        logger.exception("record_usage_for_token 记账失败: token=<redacted>")


def record_turn_usage(
    user_id: int,
    *,
    prompt: str = "",
    completion: str = "",
    total_tokens: Optional[int] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    db: Optional[Session] = None,
) -> dict:
    """记录一次 LLM 调用的用量。

    优先使用传入的精确 token 数；若缺失则用 tiktoken 估算。

    Args:
        user_id: 用户 ID
        prompt: 用户提示词文本（用于估算）
        completion: LLM 补全文本（用于估算）
        total_tokens: 精确的总 token 数（优先）
        prompt_tokens: 精确的 prompt token 数
        completion_tokens: 精确的 completion token 数
        db: 可选的数据库会话；若未提供则新建一个

    Returns:
        dict 包含 estimated 标记和最终 token 数
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    estimated = False

    try:
        # ── 确定 token 数 ──
        if total_tokens is not None:
            final_total = total_tokens
            if prompt_tokens is None:
                prompt_tokens = _estimate_tokens(prompt)
            if completion_tokens is None:
                completion_tokens = max(0, final_total - prompt_tokens)
        else:
            estimated = True
            if prompt_tokens is None:
                prompt_tokens = _estimate_tokens(prompt)
            if completion_tokens is None:
                completion_tokens = _estimate_tokens(completion)
            final_total = prompt_tokens + completion_tokens

        yyyymm = _current_yyyymm()
        today = _today()

        dialect = db.bind.dialect.name if db.bind is not None else "sqlite"
        token_sql = _upsert_sql(dialect, "usage_token")
        daily_sql = _upsert_sql(dialect, "usage_daily")

        # ── usage_token 按月原子累加 ──
        db.execute(
            text(token_sql),
            {
                "user_id": user_id,
                "yyyymm": yyyymm,
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": final_total,
            },
        )

        # ── usage_daily 按日原子累加 ──
        db.execute(
            text(daily_sql),
            {"user_id": user_id, "date": today},
        )

        db.commit()

        if estimated:
            logger.debug(
                "usage recorded (estimated): user_id=%s total=%d prompt=%d completion=%d",
                user_id,
                final_total,
                prompt_tokens,
                completion_tokens,
            )
        else:
            logger.debug(
                "usage recorded: user_id=%s total=%d",
                user_id,
                final_total,
            )

        return {
            "estimated": estimated,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": final_total,
        }

    except Exception:
        db.rollback()
        logger.exception("记录用量失败: user_id=%s", user_id)
        return {"estimated": True, "total_tokens": 0}

    finally:
        if close_db:
            db.close()


def get_daily_api_calls(user_id: int, db: Session) -> int:
    """查询用户当日的 API 调用次数。"""
    today = _today()
    row = db.execute(
        text(
            "SELECT api_calls FROM usage_daily WHERE user_id = :uid AND date = :date"
        ),
        {"uid": user_id, "date": today},
    ).fetchone()
    return row[0] if row else 0


def get_monthly_token_usage(user_id: int, db: Session) -> int:
    """查询用户当月的 total_tokens 消耗。"""
    yyyymm = _current_yyyymm()
    row = db.execute(
        text(
            "SELECT total_tokens FROM usage_token WHERE user_id = :uid AND yyyymm = :yyyymm"
        ),
        {"uid": user_id, "yyyymm": yyyymm},
    ).fetchone()
    return row[0] if row else 0
