"""题目生成失败与历史固定模板的防护工具。"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

_FALLBACK_STEM = re.compile(r"^关于「.+」，以下哪项最符合原文内容？$")
_FALLBACK_EXPLANATIONS = {"请参考原文段落。", "请参考原文页面。"}
_FALLBACK_OPTIONS = {
    "B": "与原文无关的干扰项",
    "C": "片面或不完整的描述",
    "D": "明显错误的描述",
}


class FallbackTemplateRejected(ValueError):
    """固定占位模板试图进入正式用户题库。"""

    classification = "invalid_output"


def _decode_options(options: Any) -> list[dict]:
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(options, list):
        return []
    return [item for item in options if isinstance(item, dict)]


def is_fixed_fallback_template(
    *,
    stem: Optional[str],
    options: Any,
    answer: Optional[str],
    question_type: Optional[str] = "single_choice",
    explanation: Optional[str] = None,
) -> bool:
    """用完整结构签名识别旧固定模板，不使用宽泛关键词匹配。"""
    if not stem or not _FALLBACK_STEM.fullmatch(stem.strip()):
        return False
    if (question_type or "").strip().lower() != "single_choice":
        return False
    if (answer or "").strip().upper() != "A":
        return False
    if explanation is not None and explanation.strip() not in _FALLBACK_EXPLANATIONS:
        return False

    decoded = _decode_options(options)
    if len(decoded) != 4:
        return False

    by_key = {
        str(item.get("key", "")).strip().upper(): str(
            item.get("text", "")
        ).strip()
        for item in decoded
    }
    if set(by_key) != {"A", "B", "C", "D"} or not by_key["A"]:
        return False
    return all(by_key[key] == value for key, value in _FALLBACK_OPTIONS.items())


def is_quarantined_question(question: Any) -> bool:
    """判断数据库题目是否应从正式用户题库隔离。"""
    if getattr(question, "source_type", None) == "fallback":
        return True
    return is_fixed_fallback_template(
        stem=getattr(question, "stem", None),
        options=getattr(question, "options", None),
        answer=getattr(question, "answer", None),
        question_type=getattr(question, "question_type", None),
        explanation=getattr(question, "explanation", None),
    )
