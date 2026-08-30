"""一页一个 Agent：工具只在内存攒题，交卷走主程序 complete。"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.qgen.tcn_tags import build_tag_hint
from app.services.agents.question_gen_agent import (
    agent_generate_for_page,
    is_generation_failure_marker,
)
from app.services.quiz.question_normalize import normalize_question

logger = logging.getLogger(__name__)


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


async def run_page(job: dict[str, Any], page: dict[str, Any]) -> tuple[str, list[dict], Optional[dict], str]:
    """返回 (ok|fail, questions, usage, error)。"""
    page_number = int(page["page_number"])
    tag_hint = build_tag_hint(job.get("tag_hint"), job.get("tcn_domain"))
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
    count = int(job.get("questions_per_page") or 1)
    user_id = int(job["user_id"])

    result = await agent_generate_for_page(
        page_payload,
        count=count,
        tag_hint=tag_hint,
        token=None,
        near_pages=near_pages,
        allowed_page_numbers=allowed,
        user_id=user_id,
    )
    if not result:
        return "fail", [], None, "无有效结构化题目"
    if is_generation_failure_marker(result[0]):
        reason = result[0].get("_question_generation_failure") or "llm_error"
        return "fail", [], None, reason

    questions: list[dict] = []
    for raw in result[:count]:
        normalized = normalize_question(raw) if isinstance(raw, dict) else None
        if normalized:
            questions.append(normalized)
    if not questions:
        return "fail", [], None, "题目字段校验失败"
    return "ok", questions, None, ""
