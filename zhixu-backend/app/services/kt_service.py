"""KT 知识追踪服务层 — 基于 TCN report + 图谱缓存

核实依据：TCN_API_CONFIRMATION_REPLY.md v1.4
"""

from app.services.tcn_client import tcn_client
from app.services.graph_cache import get_graph_cache


async def recommend_learning_path(user_hash: str, top_k: int = 5) -> dict:
    """基于 TCN report 掌握度 + 图谱缓存先修关系，推荐学习路径"""
    graph_cache = get_graph_cache()
    report = await tcn_client.get_report(user_hash)
    nodes_data = report.get("nodes", {})

    candidates = []
    for node_id, info in graph_cache.items():
        mastery = nodes_data.get(node_id, {}).get("mastery", 0)
        if mastery >= 0.8:
            continue

        prereqs_ok = True
        for parent_id in info.get("parents", []):
            parent_mastery = nodes_data.get(parent_id, {}).get("mastery", 0)
            if parent_mastery < 0.6:
                prereqs_ok = False
                break
        if not prereqs_ok:
            continue

        importance = len(info.get("dependents", []))
        candidates.append({
            "skill_id": node_id,
            "skill_name": info["name"],
            "current_mastery": round(mastery, 3),
            "importance": importance,
            "priority_score": round(importance + (1 - mastery), 3),
        })

    candidates.sort(key=lambda x: x["priority_score"], reverse=True)
    return {"recommendations": candidates[:top_k]}


async def get_prerequisites(user_hash: str, skill_id: str) -> dict:
    """查询指定节点的先修关系"""
    graph_cache = get_graph_cache()
    report = await tcn_client.get_report(user_hash)
    nodes_data = report.get("nodes", {})

    node_info = graph_cache.get(skill_id, {})
    if not node_info:
        return {"skill": None, "prerequisites": [], "dependents": []}

    parents_mastery = nodes_data.get(skill_id, {}).get("parents", {})
    prerequisites = []
    for parent_id, parent_mastery in parents_mastery.items():
        prerequisites.append({
            "id": parent_id,
            "name": graph_cache.get(parent_id, {}).get("name", parent_id),
            "mastery": parent_mastery,
        })

    dependents = []
    for dep_id in node_info.get("dependents", []):
        dep_mastery = nodes_data.get(dep_id, {}).get("mastery", 0)
        dependents.append({
            "id": dep_id,
            "name": graph_cache.get(dep_id, {}).get("name", dep_id),
            "mastery": dep_mastery,
        })

    return {
        "skill": {"id": skill_id, "name": node_info.get("name", skill_id)},
        "prerequisites": prerequisites,
        "dependents": dependents,
    }


async def get_skill_graph(user_hash: str) -> dict:
    """返回全量图谱+用户掌握度叠加"""
    graph_cache = get_graph_cache()
    report = await tcn_client.get_report(user_hash)
    user_nodes = report.get("nodes", {})

    skills = []
    for node_id, info in graph_cache.items():
        entry = {"id": node_id, "name": info["name"]}
        if node_id in user_nodes:
            entry["mastery"] = user_nodes[node_id]["mastery"]
            entry["confidence"] = user_nodes[node_id]["confidence"]
        skills.append(entry)

    edges = []
    for node_id, info in graph_cache.items():
        for child_id in info.get("dependents", []):
            edges.append({"source": node_id, "target": child_id})

    return {
        "skills": skills,
        "edges": edges,
        "total_skills": len(skills),
        "total_edges": len(edges),
    }


async def get_skill_states(user_hash: str) -> dict:
    """返回已练习节点的掌握度快照 {node_id: mastery}"""
    report = await tcn_client.get_report(user_hash)
    nodes = report.get("nodes", {})
    return {node_id: info["mastery"] for node_id, info in nodes.items()}