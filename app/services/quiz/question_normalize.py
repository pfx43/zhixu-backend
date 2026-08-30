"""题目字段校验 — 出题 Agent 与主程序入库共用，不碰数据库。"""
from typing import Optional


def normalize_question(raw: dict) -> Optional[dict]:
    stem = (raw.get("stem") or raw.get("question") or "").strip()
    answer = (raw.get("answer") or "").strip()
    qtype = (raw.get("question_type") or "single_choice").strip().lower()
    options = raw.get("options") or []
    if not stem or not answer:
        return None

    norm_options = []
    for opt in options:
        if isinstance(opt, dict):
            key = str(opt.get("key", "")).strip().upper()
            text = str(opt.get("text", "")).strip()
        else:
            continue
        if key and text:
            norm_options.append({"key": key, "text": text})

    if qtype == "single_choice":
        answer = answer.upper()
        if len(norm_options) < 2 or answer not in {o["key"] for o in norm_options}:
            return None
    elif qtype in ("short_answer", "application"):
        if not norm_options:
            norm_options = []
    else:
        qtype = "single_choice"
        answer = answer.upper()
        if len(norm_options) < 2:
            return None

    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    ref_text = (raw.get("reference_text") or "").strip() or None
    return {
        "stem": stem,
        "options": norm_options,
        "answer": answer,
        "explanation": (raw.get("explanation") or "").strip() or None,
        "tags": tags,
        "question_type": qtype,
        "reference_text": ref_text,
    }
