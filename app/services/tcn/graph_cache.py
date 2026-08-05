"""图谱数据缓存 — 启动时从 TCN /admin/graph/* 拉取全量图谱

缓存结构：{node_id: {"name": "加法", "parents": ["math:arithmetic"], "dependents": ["math:multiplication"]}}
"""

import logging

logger = logging.getLogger(__name__)

# 全局缓存
_graph_cache: dict = {}


def get_graph_cache() -> dict:
    """获取图谱缓存（O(1)）"""
    return _graph_cache


async def init_graph_cache():
    """启动时加载所有域的图谱数据到缓存"""
    global _graph_cache
    from app.services.tcn.tcn_client import tcn_client

    _graph_cache = {}

    if not tcn_client.is_enabled:
        logger.warning("TCN 不可达，跳过图谱缓存初始化")
        return

    try:
        domains_resp = await tcn_client.get_graph_domains()
        domain_list = domains_resp.get("domains", []) if isinstance(domains_resp, dict) else domains_resp
        if not domain_list:
            logger.warning("图谱域列表为空")
            return

        for entry in domain_list:
            domain = entry["name"] if isinstance(entry, dict) else entry
            try:
                data = await tcn_client.get_graph_data(domain)
                nodes = data.get("nodes", [])
                edges = data.get("edges", [])

                # 构建 node_id → {name, parents, dependents}
                for node in nodes:
                    node_id = node["id"]
                    if node_id not in _graph_cache:
                        _graph_cache[node_id] = {
                            "name": node.get("label", node.get("name", node_id)),
                            "parents": [],
                            "dependents": [],
                        }

                # 构建先修/后继关系
                for edge in edges:
                    parent_id = edge["from"]
                    child_id = edge["to"]
                    if parent_id in _graph_cache:
                        _graph_cache[parent_id].setdefault("dependents", []).append(child_id)
                    if child_id in _graph_cache:
                        _graph_cache[child_id].setdefault("parents", []).append(parent_id)

                logger.info(f"域 [{domain}]: {len(nodes)} 节点, {len(edges)} 边")
            except Exception as e:
                logger.error(f"拉取域 [{domain}] 图谱失败: {e}")

        logger.info(f"图谱缓存初始化完成，共 {len(_graph_cache)} 个节点")
    except Exception as e:
        logger.error(f"图谱缓存初始化失败: {e}")