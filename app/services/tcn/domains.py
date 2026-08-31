"""TCN 封闭学科名单：只认 tcn_domains 表里的 id，否则 None。"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.tcn_domain import TcnDomain

DEFAULT_TCN_DOMAINS = (
    {"id": "higher_math", "label": "高等数学"},
    {"id": "math", "label": "数学"},
    {"id": "physics", "label": "物理"},
    {"id": "discrete_math", "label": "离散数学"},
)


def ensure_tcn_domains(db: Session) -> List[TcnDomain]:
    existing = {row.id: row for row in db.query(TcnDomain).all()}
    added = False
    for item in DEFAULT_TCN_DOMAINS:
        if item["id"] not in existing:
            row = TcnDomain(id=item["id"], label=item["label"])
            db.add(row)
            existing[item["id"]] = row
            added = True
    if added:
        db.flush()
    return list(existing.values())


def list_domain_ids(db: Optional[Session] = None) -> List[str]:
    if db is None:
        return [item["id"] for item in DEFAULT_TCN_DOMAINS]
    rows = ensure_tcn_domains(db)
    return [row.id for row in rows]


def list_domains_public(db: Session) -> List[dict]:
    rows = ensure_tcn_domains(db)
    by_id = {row.id: row.label for row in rows}
    out = []
    for item in DEFAULT_TCN_DOMAINS:
        out.append(
            {
                "id": item["id"],
                "label": by_id.get(item["id"], item["label"]),
            }
        )
        by_id.pop(item["id"], None)
    for domain_id, label in sorted(by_id.items()):
        out.append({"id": domain_id, "label": label})
    return out


def normalize_domain(value: Optional[str], allowed: Optional[List[str]] = None) -> Optional[str]:
    token = (value or "").strip()
    if not token or token.lower() in ("none", "null", "未知"):
        return None
    allowed_ids = list(allowed) if allowed is not None else [i["id"] for i in DEFAULT_TCN_DOMAINS]
    if token in allowed_ids:
        return token
    return None


def parse_user_domain(value: Optional[str], allowed: Optional[List[str]] = None) -> Optional[str]:
    """人改学科：空 / none → None；不在名单里的原样拒绝（返回 False 标记用 ValueError）。"""
    token = (value or "").strip()
    if not token or token.lower() in ("none", "null"):
        return None
    allowed_ids = list(allowed) if allowed is not None else [i["id"] for i in DEFAULT_TCN_DOMAINS]
    if token not in allowed_ids:
        raise ValueError(token)
    return token


def label_for_domain(db: Session, domain_id: Optional[str]) -> Optional[str]:
    domain_id = normalize_domain(domain_id)
    if not domain_id:
        return None
    row = db.query(TcnDomain).filter(TcnDomain.id == domain_id).first()
    if row:
        return row.label
    for item in DEFAULT_TCN_DOMAINS:
        if item["id"] == domain_id:
            return item["label"]
    return domain_id
