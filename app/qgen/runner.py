"""一页一个 Agent：工具只在内存攒题，交卷走主程序 complete。"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.qgen.tcn_tags import build_tag_hint, keep_questions_with_legal_tags
from app.services.agents.question_gen_agent import (
    agent_generate_for_page,
    is_generation_failure_marker,
)
from app.services.quiz.qgen_count import persist_questions_per_page, questions_per_page_cap
from app.services.quiz.question_normalize import normalize_question

logger = logging.getLogger(__name__)

_RETRY_HINT = "上次知识点不在封闭名单内，必须只从名单里选 name，禁止自造或「自动生成」。"


def _near_pages_map(raw: Any) -> dict[int, dict]:
    if not isinstance(raw, dict):
        return {}
    out: dict[int, dict] = {}
    for key, page in raw.items():
        try:
            num = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(page, dict):
            out[num] = page
    return out


async def _generate_normalized(
    *,
    page_payload: dict,
    count: Optional[int],
    tag_hint: str,
    near_pages: dict,
    allowed: set,
    user_id: int,
    tcn_domain: Optional[str],
) -> tuple[str, list[dict], str]:
    cap = questions_per_page_cap(count)
    result = await agent_generate_for_page(
        page_payload,
        count=count,
        tag_hint=tag_hint,
        token=None,
        near_pages=near_pages,
        allowed_page_numbers=allowed,
        user_id=user_id,
        tcn_domain=tcn_domain,
    )
    if not result:
        return "fail", [], "无有效结构化题目"
    if is_generation_failure_marker(result[0]):
        reason = result[0].get("_question_generation_failure") or "llm_error"
        return "fail", [], reason

    questions: list[dict] = []
    for raw in result[:cap]:
        normalized = normalize_question(raw) if isinstance(raw, dict) else None
        if normalized:
            questions.append(normalized)
    questions = keep_questions_with_legal_tags(questions, tcn_domain)
    if not questions:
        return "fail", [], "无有效结构化题目"
    return "ok", questions, ""


async def run_page(job: dict[str, Any], page: dict[str, Any]) -> tuple[str, list[dict], Optional[dict], str]:
    """返回 (ok|fail, questions, usage, error)。"""
    page_number = int(page["page_number"])
    tcn_domain = job.get("tcn_domain") or None
    tag_hint = build_tag_hint(job.get("tag_hint"), tcn_domain)
    near_pages = _near_pages_map(page.get("near_pages"))
    allowed = set()
    for item in page.get("allowed_page_numbers") or []:
        try:
            allowed.add(int(item))
        except (TypeError, ValueError):
            continue
    if not allowed:
        allowed = set(near_pages) | {page_number}

    page_payload = {
        "page_number": page_number,
        "title": page.get("title") or f"第 {page_number} 页",
        "content": page.get("content") or "",
        "segment_id": page.get("segment_id"),
    }
    persisted = persist_questions_per_page(job.get("questions_per_page"))
    count = persisted if persisted > 0 else None
    user_id = int(job["user_id"])

    kwargs = dict(
        page_payload=page_payload,
        count=count,
        tag_hint=tag_hint,
        near_pages=near_pages,
        allowed=allowed,
        user_id=user_id,
        tcn_domain=tcn_domain,
    )
    status, questions, error = await _generate_normalized(**kwargs)
    if tcn_domain and status != "ok" and error not in (
        "llm_timeout",
        "llm_error",
        "agent_unavailable",
    ):
        kwargs["tag_hint"] = f"{tag_hint}\n{_RETRY_HINT}"
        status, questions, error = await _generate_normalized(**kwargs)
        if questions:
            status, error = "ok", ""
    if status != "ok" or not questions:
        return "fail", [], None, error or "无有效结构化题目"
    return "ok", questions, None, ""
