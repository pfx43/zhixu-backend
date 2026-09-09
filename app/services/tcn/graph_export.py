"""从本地 TCN 学科完整图谱读点 + 内部边，不打 /admin/graph。"""
from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

# 封闭学科完整导出：assets/tcn/domain-graphs/{domain}.tcn-domain-graph.json
_DOMAIN_GRAPH_SUFFIX = ".tcn-domain-graph.json"


def _domain_graphs_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "assets" / "tcn" / "domain-graphs"


def _domain_graph_path(domain: str) -> Path:
    return _domain_graphs_dir() / f"{domain}{_DOMAIN_GRAPH_SUFFIX}"


@lru_cache(maxsize=8)
def _load_export(domain: str) -> dict:
    path = _domain_graph_path(domain)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    for item in data.get("domains") or []:
        if item.get("domain") == domain:
            return item
    return {}


def load_domain_graph(domain: Optional[str]) -> dict:
    """返回 {nodes: [{id,name}], edges: [{source,target,weight}]}，只用本科内部边。"""
    if not domain:
        return {"nodes": [], "edges": []}
    raw = _load_export(domain)
    nodes_out: List[dict] = []
    node_ids = set()
    for node in raw.get("nodes") or []:
        if (node.get("status") or "active") != "active":
            continue
        node_id = (node.get("id") or "").strip()
        name = (node.get("name") or "").strip() or node_id
        if not node_id:
            continue
        node_ids.add(node_id)
        nodes_out.append({"id": node_id, "name": name})

    inner = raw.get("inner_edges")
    if not isinstance(inner, list):
        inner = [
            e
            for e in (raw.get("edges") or [])
            if (e.get("from") in node_ids and e.get("to") in node_ids)
        ]
    edges_out = []
    for edge in inner:
        src = (edge.get("from") or "").strip()
        dst = (edge.get("to") or "").strip()
        if src not in node_ids or dst not in node_ids:
            continue
        item = {"source": src, "target": dst}
        if edge.get("weight") is not None:
            item["weight"] = edge["weight"]
        edges_out.append(item)
    return {"nodes": nodes_out, "edges": edges_out}


def mastery_from_report(nodes_data: dict, node_id: str) -> Optional[float]:
    raw = (nodes_data or {}).get(node_id)
    if raw is None:
        return None
    if isinstance(raw, dict):
        value = raw.get("mastery")
        if isinstance(value, (int, float)):
            return float(value)
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


_READY = 0.6


def frontier_nodes(
    nodes: List[dict],
    edges: List[dict],
    mastery: Dict[str, Optional[float]],
    limit: int = 3,
) -> List[dict]:
    """先修已够、自身偏低（或还没记录）的节点，最多 limit 个。

    没有任何掌握度时只返回起点（没有先修的点）。
    """
    if not nodes or limit <= 0:
        return []
    parents: Dict[str, List[str]] = defaultdict(list)
    for edge in edges:
        src = edge.get("source")
        dst = edge.get("target")
        if src and dst:
            parents[dst].append(src)

    painted = any(v is not None for v in mastery.values())
    candidates: List[dict] = []
    for node in nodes:
        node_id = node.get("id")
        name = node.get("name") or node_id
        if not node_id:
            continue
        self_m = mastery.get(node_id)
        if self_m is not None and self_m >= _READY:
            continue
        prereqs = parents.get(node_id) or []
        if prereqs:
            if not painted:
                continue
            vals = [mastery.get(p) for p in prereqs]
            if any(v is None or v < _READY for v in vals):
                continue
            reason = (
                "先修已过，掌握度偏低"
                if self_m is not None
                else "先修已过，还没有掌握记录"
            )
        else:
            reason = (
                "起点，掌握度偏低" if self_m is not None else "起点，还没有掌握记录"
            )
        candidates.append(
            {
                "id": node_id,
                "name": name,
                "mastery": self_m,
                "reason": reason,
                "sort": self_m if self_m is not None else -1.0,
            }
        )
    candidates.sort(key=lambda item: (item["sort"], item["name"]))
    return [
        {k: item[k] for k in ("id", "name", "mastery", "reason")}
        for item in candidates[:limit]
    ]
