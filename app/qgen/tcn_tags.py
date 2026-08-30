"""按书的 tcn_domain 加载 TCN 知识点 name 列表。列尚未落地时 domain 为空，不锁 tag。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import List, Optional


def _tags_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "api" / "TCN" / "tcn-knowledge-tags.json"


@lru_cache(maxsize=4)
def _load_file() -> dict:
    path = _tags_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def tag_names_for_domain(domain: Optional[str]) -> List[str]:
    if not domain:
        return []
    data = _load_file()
    if data.get("domain") != domain:
        return []
    names: List[str] = []
    for item in data.get("tags") or []:
        name = (item.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def build_tag_hint(existing_hint: Optional[str], tcn_domain: Optional[str]) -> str:
    names = tag_names_for_domain(tcn_domain)
    if names:
        shown = "、".join(names[:80])
        extra = f"（共 {len(names)} 个，此处列出前 80 个）" if len(names) > 80 else ""
        return (
            f"本题知识点 tag 必须从下列名单中选择（学科 {tcn_domain}）{extra}：{shown}"
        )
    return (existing_hint or "").strip()
