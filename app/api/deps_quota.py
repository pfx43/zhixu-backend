"""
配额强制中间件 — 在需要计费的 API 路由中通过 Depends 注入
校验日 API 调用次数、月 token 消耗、知识库数量是否超限。
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.services.usage_service import get_daily_api_calls, get_monthly_token_usage

logger = logging.getLogger(__name__)


def check_quota(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    """强制配额校验 — 超限抛出 429。

    校验内容：
    1. 日 API 调用次数上限 (api_limit_daily)
    2. 月 token 消耗上限 (token_limit_monthly)

    知识库数量请使用单独的 check_kb_quota 依赖。

    Returns:
        current_user dict（透传，方便下游继续使用）
    """
    user_id = current_user["user_id"]

    # 从会话 payload 读取配额值（避免额外 DB 查询）
    api_limit = current_user.get("api_limit_daily", 100)
    token_limit = current_user.get("token_limit_monthly", 100000)

    # ── 检查日 API 调用次数 ──
    if api_limit > 0:  # 0 表示不限制
        daily_calls = get_daily_api_calls(user_id, db)
        if daily_calls >= api_limit:
            raise HTTPException(
                status_code=429,
                detail=f"日 API 调用次数已达上限 ({api_limit} 次/天)，请明日再试或升级套餐",
            )

    # ── 检查月 token 消耗 ──
    if token_limit > 0:
        monthly_tokens = get_monthly_token_usage(user_id, db)
        if monthly_tokens >= token_limit:
            raise HTTPException(
                status_code=429,
                detail=f"月 token 用量已达上限 ({token_limit} tokens/月)，请升级套餐",
            )

    return current_user


def check_kb_quota(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    """知识库数量配额校验 — 超限抛出 429。"""
    user_id = current_user["user_id"]
    kb_limit = current_user.get("knowledge_base_limit", 1)

    if kb_limit <= 0:
        return current_user

    # 查询用户当前知识库集合数量
    from app.models import KbCollection
    count = db.query(KbCollection).filter(
        KbCollection.user_id == user_id,
    ).count()

    if count >= kb_limit:
        raise HTTPException(
            status_code=429,
            detail=f"知识库数量已达上限 ({kb_limit} 个)，请升级套餐",
        )

    return current_user
