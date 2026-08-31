"""按书的 tcn_domain 加载 TCN 知识点 name 列表。无学科时不锁 tag。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import List, Optional


def _tags_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "api" / "TCN"


def _tags_path(domain: str) -> Path:
    named = _tags_dir() / f"{domain}.json"
    if named.is_file():
        return named
    return _tags_dir() / "tcn-knowledge-tags.json"


@lru_cache(maxsize=8)
def _load_file(domain: str) -> dict:
    path = _tags_path(domain)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def tag_names_for_domain(domain: Optional[str]) -> List[str]:
    if not domain:
        return []
    data = _load_file(domain)
    if data.get("domain") != domain:
        return []
    names: List[str] = []
    for item in data.get("tags") or []:
        name = (item.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def name_to_id_map(domain: Optional[str]) -> dict:
    if not domain:
        return {}
    data = _load_file(domain)
    if data.get("domain") != domain:
        return {}
    out: dict = {}
    for item in data.get("tags") or []:
        name = (item.get("name") or "").strip()
        node_id = (item.get("id") or "").strip()
        if name and node_id:
            out[name] = node_id
    return out


def legal_names(domain: Optional[str]) -> set:
    return set(name_to_id_map(domain))


def name_to_id(domain: Optional[str], name: Optional[str]) -> Optional[str]:
    token = (name or "").strip()
    if not token or not domain:
        return None
    return name_to_id_map(domain).get(token)


def first_legal_node(domain: Optional[str], tags: Optional[list]) -> Optional[str]:
    """交卷用：第一个落在该领域词表里的 name → 节点 id。"""
    mapping = name_to_id_map(domain)
    if not mapping:
        return None
    for raw in tags or []:
        token = (raw or "").strip() if isinstance(raw, str) else ""
        node_id = mapping.get(token)
        if node_id:
            return node_id
    return None


def tags_allowed_for_domain(tags: Optional[list], domain: Optional[str]) -> bool:
    """无学科不锁。有学科时每个 tag 都必须是该科 name，且至少有一个。"""
    if not domain:
        return True
    allowed = legal_names(domain)
    if not allowed:
        return True
    names = [(t or "").strip() for t in (tags or []) if isinstance(t, str) and (t or "").strip()]
    if not names:
        return False
    return all(name in allowed for name in names)


def keep_questions_with_legal_tags(questions: list, domain: Optional[str]) -> list:
    if not domain:
        return list(questions)
    return [
        q for q in questions
        if isinstance(q, dict) and tags_allowed_for_domain(q.get("tags") or [], domain)
    ]


def build_tag_hint(existing_hint: Optional[str], tcn_domain: Optional[str]) -> str:
    names = tag_names_for_domain(tcn_domain)
    if names:
        shown = "、".join(names[:80])
        extra = f"（共 {len(names)} 个，此处列出前 80 个）" if len(names) > 80 else ""
        return (
            f"本题知识点 tag 必须从下列名单中选择（学科 {tcn_domain}）{extra}：{shown}"
        )
    return (existing_hint or "").strip()
