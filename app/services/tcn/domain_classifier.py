"""抽目录同一趟判学科：封闭名单或 None。拿不准就 None。"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

from app.services.tcn.domains import normalize_domain
from app.utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


def parse_domain_output(text: Optional[str], allowed: Optional[List[str]] = None) -> Optional[str]:
    raw = (text or "").strip()
    if not raw:
        return None
    token = raw.split()[0].strip("`\"'。．,，")
    return normalize_domain(token, allowed)


def _prepare(
    *,
    title: str,
    toc_titles: Optional[List[str]],
    excerpt: str,
    allowed: Optional[List[str]],
) -> Tuple[Any, Optional[str], List[str]]:
    from app.services.llm.llm_pool import llm_pool
    from app.services.tcn.domains import DEFAULT_TCN_DOMAINS

    allowed_ids = [a for a in (allowed or []) if a]
    if not allowed_ids:
        allowed_ids = [item["id"] for item in DEFAULT_TCN_DOMAINS]

    llm = llm_pool.acquire()
    if llm is None:
        return None, None, allowed_ids

    roster = "、".join(allowed_ids)
    toc = "、".join((t or "").strip() for t in (toc_titles or []) if (t or "").strip())
    user = (
        f"封闭名单（只能输出其中一个，或 none）：{roster}\n"
        f"书名：{(title or '').strip() or '（无）'}\n"
        f"目录：{toc[:800] or '（无）'}\n"
        f"正文摘录：\n{(excerpt or '')[:1200]}"
    )
    return llm, user, allowed_ids


def _domain_from_resp(resp: Any, allowed_ids: List[str], title: str) -> Optional[str]:
    content = ""
    if isinstance(resp, dict):
        content = resp.get("content") or ""
    elif isinstance(resp, str):
        content = resp
    domain = parse_domain_output(content, allowed_ids)
    if domain:
        logger.info("TCN 学科分类: title=%s domain=%s", title, domain)
    return domain


async def classify_tcn_domain(
    *,
    title: str,
    toc_titles: Optional[List[str]] = None,
    excerpt: str = "",
    allowed: Optional[List[str]] = None,
) -> Optional[str]:
    """当前事件循环上 await apredict_no_stream。不开新 loop，不走 llm_runner。"""
    llm, user, allowed_ids = _prepare(
        title=title, toc_titles=toc_titles, excerpt=excerpt, allowed=allowed
    )
    if llm is None:
        return None
    try:
        resp = await llm.apredict_no_stream(
            input_text=user,
            sys_prompt=load_prompt("tcn_domain_classify"),
            temperature=0,
        )
    except Exception:
        logger.warning("TCN 学科分类调用失败，保持 tcn_domain=None", exc_info=True)
        return None
    return _domain_from_resp(resp, allowed_ids, title)


def classify_tcn_domain_sync(
    *,
    title: str,
    toc_titles: Optional[List[str]] = None,
    excerpt: str = "",
    allowed: Optional[List[str]] = None,
) -> Optional[str]:
    """同步切段：Tina 的 httpx.post。不开新 loop，不碰绑在主 loop 上的 aclient。"""
    llm, user, allowed_ids = _prepare(
        title=title, toc_titles=toc_titles, excerpt=excerpt, allowed=allowed
    )
    if llm is None:
        return None
    try:
        resp = llm.predict(
            input_text=user,
            sys_prompt=load_prompt("tcn_domain_classify"),
            temperature=0,
            stream=False,
        )
    except Exception:
        logger.warning("TCN 学科分类调用失败，保持 tcn_domain=None", exc_info=True)
        return None
    return _domain_from_resp(resp, allowed_ids, title)
