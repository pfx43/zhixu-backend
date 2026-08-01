"""
题干规范化与 content_hash 计算 — 用于 global_questions 全局去重
"""
import hashlib
import json
import re
import unicodedata
from typing import Any, List, Union


def normalize_text(text: str) -> str:
    """去除空白、标点，统一 Unicode 形式并转小写。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^\w\u4e00-\u9fff]", "", text)
    return text.lower()


def _options_to_str(options: Union[List[Any], str, None]) -> str:
    if options is None:
        return ""
    if isinstance(options, str):
        try:
            parsed = json.loads(options)
            return json.dumps(parsed, ensure_ascii=False, sort_keys=True)
        except (json.JSONDecodeError, TypeError):
            return options
    return json.dumps(options, ensure_ascii=False, sort_keys=True)


def compute_content_hash(
    stem: str,
    options: Union[List[Any], str, None],
    answer: str,
) -> str:
    """题干 + 选项 + 答案规范化后 SHA256。"""
    raw = (
        normalize_text(stem)
        + normalize_text(_options_to_str(options))
        + normalize_text(answer)
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
