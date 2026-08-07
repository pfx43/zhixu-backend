"""
用量服务 — token 记账 & 配额查询
提供 record_turn_usage() 按日/月原子累加 API 调用次数和 token 消耗。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


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
    """返回当前年月字符串，如 '202608'。"""
    return datetime.now(timezone.utc).strftime("%Y%m")


def _today() -> date:
    """返回当前 UTC 日期。"""
    return datetime.now(timezone.utc).date()


# ── 公开 API ──


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
            prompt_tokens = prompt_tokens or _estimate_tokens(prompt)
            completion_tokens = completion_tokens or _estimate_tokens(completion)
            final_total = prompt_tokens + completion_tokens

        yyyymm = _current_yyyymm()
        today = _today()

        # ── usage_token 按月原子累加 ──
        db.execute(
            text(
                """
                INSERT INTO usage_token (user_id, yyyymm, prompt_tokens, completion_tokens, total_tokens)
                VALUES (:user_id, :yyyymm, :prompt, :completion, :total)
                ON CONFLICT (user_id, yyyymm)
                DO UPDATE SET
                    prompt_tokens = usage_token.prompt_tokens + :prompt,
                    completion_tokens = usage_token.completion_tokens + :completion,
                    total_tokens = usage_token.total_tokens + :total
                """
            ),
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
            text(
                """
                INSERT INTO usage_daily (user_id, date, api_calls)
                VALUES (:user_id, :date, 1)
                ON CONFLICT (user_id, date)
                DO UPDATE SET api_calls = usage_daily.api_calls + 1
                """
            ),
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
            "SELECT total_tokens FROM usage_token WHERE user_id = :uid AND yyyymm = :ym"
        ),
        {"uid": user_id, "yyyymm": yyyymm},
    ).fetchone()
    return row[0] if row else 0
