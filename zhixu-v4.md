# zhixu-v4：TCN 引擎层对接与重复接口治理方案

> **版本**：v2.0（基于 TCN 方 2026-07-13 源码确认后修订）  
> **日期**：2026-07-15  
> **基线文档**：  
> - `SYSTEM_ARCHITECTURE_BRIEF.md`（TCN 引擎层职责边界与接口规范，v1.1）  
> - `TCN_API_CONFIRMATION_REPLY.md`（TCN 方源码级接口确认回复，v1.4）  
> - `后端能力补齐清单.md`（原 21 项后端缺口）  
> - `zhixu-v2.md`（融合执行计划）  
> 
> **核心原则**：TCN 引擎层（算法团队，port 8001）已实现 LEKT 推理、LVR 计算、CABR 约束、UserMask 持久化。我方后端不再维护同质算法模块，统一通过 HTTP 调用 TCN 接口。
>
> **v2.0 变更**：基于 TCN 源码级确认回复，修正了 report 顶层结构、parents 类型、predict 响应字段、node_id 格式等 5 处关键错误；增加图谱数据缓存机制；更新全部代码示例。

---

## 目录

- [一、TCN 已确认的接口能力](#一tcn-已确认的接口能力)
- [二、我方重复接口清单与处理决策](#二我方重复接口清单与处理决策)
- [三、需要改造的接口（保留但切换数据源）](#三需要改造的接口保留但切换数据源)
- [四、TCN 客户端完整接入方案](#四tcn-客户端完整接入方案)
- [五、图谱数据缓存方案（含中文名称）](#五图谱数据缓存方案含中文名称)
- [六、分步实施计划](#六分步实施计划)
- [七、需要 TCN 新增的接口（2 天内交付）](#七需要-tcn-新增的接口2-天内交付)
- [八、验证检查表](#八验证检查表)
- [附录 A：TCN 回复纠正追踪](#附录-atcn-回复纠正追踪)

---

## 一、TCN 已确认的接口能力

> **来源**：`TCN_API_CONFIRMATION_REPLY.md` 第 1 节，从 TCN 服务端源码逐行核查提取，准确性已核实。  
> **OpenAPI 文档**：`http://127.0.0.1:8001/docs`（Swagger UI），可一次性核对所有字段。

### 1.1 接口总览

| 编号 | 接口 | 方法 | 端点 | 鉴权 | 核心能力 |
|------|------|------|------|------|---------|
| A1 | 更新知识状态 | POST | `/v1/user/predict` | **无需鉴权** | LEKT 贝叶斯更新掌握度 |
| A2 | 认知画像摘要 | GET | `/v1/user/profile/{user_hash}` | **无需鉴权** | global_lvr、total_steps、node_count、graph_version |
| A3 | 完整掌握报告 | GET | `/v1/user/report/{user_hash}` | **无需鉴权** | 顶层 object，nodes dict（稀疏），含 parents dict |
| A4 | 健康检查 | GET | `/health` | **无需鉴权** | status、nodes(总节点数)、graph_version、constraint、model |
| A5 | 图谱域列表 | GET | `/admin/graph/domains` | `X-Admin-Token` | 所有域名列表 |
| A6 | 图谱数据 | GET | `/admin/graph/data/{domain}` | `X-Admin-Token` | 单域全量节点(id+name+status)+边(from+to+weight+relation) |

### 1.2 `POST /v1/user/predict` — 请求与响应

**请求体**（完整字段，TCN 源码确认）：
```json
{
  "api_key": "",
  "user_hash": "a3f9c1d2e8b7...",
  "domain_id": "math",
  "current_node": "math:quadratic_equation",
  "user_action": "correct",
  "step_index": 12,
  "session_id": "sess_20260713_001"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `api_key` | string | 是 | 当前版本未验证，**传空字符串** `""` |
| `user_hash` | string | 是 | 用户唯一标识，任意 string（建议 sha256 hex 32 位） |
| `domain_id` | string | 否 | 领域 ID，如 `"math"`，可传空字符串 |
| `current_node` | string | 是 | 当前答题的知识节点 ID，格式 `"domain:node_id"` |
| `user_action` | string | 是 | 仅 `"correct"` / `"incorrect"`，非 correct 一律视为 incorrect |
| `step_index` | int | 是 | 会话内步骤序号，从 0 递增，影响 LVR 计算时序 |
| `session_id` | string | 否 | 日志关联用，可选 |

**真实完整响应**（8 个字段）：
```json
{
  "user_hash": "a3f9c1d2e8b7...",
  "lvr": 0.12,
  "vs": 0.03,
  "diagnosis": "LVR=0.120: quadratic(0.85) > linear(0.40) [3 edges violated]. Recommend: review linear (mastery=0.40)",
  "recommended_backtrack": "math:linear_equation",
  "node_mastery": {
    "math:arithmetic": 0.95,
    "math:counting": 0.88,
    "math:addition": 0.91,
    "math:subtraction": 0.87,
    "math:multiplication": 0.82,
    "math:division": 0.79,
    "math:fractions": 0.71,
    "math:decimals": 0.68,
    "math:percentages": 0.65,
    "math:ratios": 0.60
  },
  "epsilon_used": 0.05,
  "training_phase": "unknown"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `lvr` | float | 全局 LVR（0–1） |
| `vs` | float | Violation Severity（0–1） |
| `diagnosis` | string | 诊断描述文本，含具体违反边信息 |
| `recommended_backtrack` | string\|null | 建议回溯的节点 id，无违反时为 null |
| `node_mastery` | dict | ⚠️ **图谱前 10 个节点**（索引 0–9）的掌握度，**不保证包含 current_node** |
| `epsilon_used` | float | 本次约束阈值（static 模式固定 0.05） |
| `training_phase` | string | 当前版本硬编码为 `"unknown"` |

> ⚠️ **关键认知**：`node_mastery` 是图谱前 10 个节点，不是 current_node。如需当前节点的最新掌握度，在 predict 后调用 `GET /v1/user/report/{user_hash}` 查询。

### 1.3 `GET /v1/user/report/{user_hash}` — 真实格式

**真实响应**（顶层是 object，不是 array）：
```json
{
  "user_hash": "a3f9c1d2e8b7...",
  "global_lvr": 0.12,
  "total_steps": 47,
  "nodes": {
    "math:quadratic_equation": {
      "mastery": 0.85,
      "confidence": 0.72,
      "parents": {
        "math:linear_equation": 0.91,
        "math:factoring": 0.78
      }
    },
    "math:linear_equation": {
      "mastery": 0.91,
      "confidence": 0.0,
      "parents": {}
    }
  }
}
```

**字段说明**：

| 层级 | 字段 | 类型 | 说明 |
|------|------|------|------|
| 顶层 | `user_hash` | string | 同请求 |
| 顶层 | `global_lvr` | float | 全局 LVR |
| 顶层 | `total_steps` | int | 用户总学习步数 |
| 顶层 | `nodes` | **object (dict)** | 用户实际练习过的节点（稀疏），key 为 `"domain:node_id"` |
| nodes[key] | `mastery` | float | 节点掌握度（0–1） |
| nodes[key] | `confidence` | float | ⚠️ rule 模式始终 0.0，LEKT/GKT/AKT 模式才有值 |
| nodes[key] | `parents` | **dict** | `{parent_node_id: mastery_float}`，空对象表示根节点 |
| — | **无 name 字段** | — | ❌ 不含中文名称，需从 `/admin/graph/data/{domain}` 获取 |
| — | **无 index 字段** | — | ❌ 不含 |
| — | **无 dependents 字段** | — | ❌ 无后继节点，需从图谱边数据推导 |

> **nodes 覆盖范围**：仅包含**用户实际练习过的节点**（稀疏存储）。rule 模式下每次 predict 只写一个节点；LEKT 模式下写全部节点。未练习过的节点默认掌握度 0.5。

### 1.4 `GET /v1/user/profile/{user_hash}`

```json
{
  "user_hash": "a3f9c1d2e8b7...",
  "total_steps": 47,
  "global_lvr": 0.12,
  "graph_version": 3,
  "node_count": 42
}
```

> `node_count` 是用户已练习的节点数（稀疏），不是图谱总节点数。图谱总节点数通过 `/health` 的 `nodes` 字段查询。

### 1.5 `GET /health`

```json
{
  "status": "ok",
  "nodes": 503,
  "graph_version": 3,
  "dense_mode": false,
  "constraint": "static",
  "model": "lekt"
}
```

> ⚠️ 节点数字段名是 `nodes`（不是 `skills_count`）。

### 1.6 `GET /admin/graph/data/{domain}` — 图谱数据

**用途**：获取节点中文名称、边关系、构建本地 id→name 映射表。

| 字段 | 说明 |
|------|------|
| `nodes[].id` | 节点标识，对应 report 的 nodes dict key |
| `nodes[].name` | 节点中文名称 |
| `nodes[].status` | 节点状态 |
| `edges[].from` / `edges[].to` | 先修边方向 |
| `edges[].weight` / `edges[].relation` / `edges[].edge_type` | 边属性 |

> **建议**：启动时全量拉取所有域的图谱（503 节点约 50–100KB），本地缓存为 `{node_id: name}` 的 dict，实现 O(1) 查询。

---

## 二、我方重复接口清单与处理决策

### 2.1 直接淘汰的接口（3 个）

| 序号 | 接口 | 文件 | 行数 | 淘汰原因 | TCN 替代 |
|------|------|------|------|---------|---------|
| D1 | `POST /api/v1/kt/correct` | `app/api/v1/kt.py:21-30` | 10 | 本地 LEKT 约束修正，TCN predict 已覆盖且更强 | `POST /v1/user/predict` |
| D2 | `POST /api/v1/kt/evaluate` | `app/api/v1/kt.py:33-42` | 10 | 本地 LVR 评估，TCN predict 含 lvr+vs+diagnosis | predict 响应字段 |
| D3 | `GET /health` 中的 LEKT 状态 | `server.py:105-112` | 8 | 本地 LEKT 加载检测，TCN 有独立 health | TCN `GET /health` |

### 2.2 淘汰的底层文件（8 个）

| 序号 | 文件 | 说明 |
|------|------|------|
| F1 | `lekt_service.py`（305 行） | LEKTService 单例 |
| F2 | `lekt_api.cp314-win_amd64.pyd` | LEKTAPI 二进制 |
| F3 | `logic_matrix.npy` | 7×7 先修关系矩阵 |
| F4 | `generate_matrix.py`（153 行） | 矩阵生成工具 |
| F5 | `my_skills.csv` | 技能名称模板 |
| F6 | `app/core/lekt_state.py`（7 行） | get_lekt Depends |
| F7 | `server.py:25/L53-L57/L99-L101` | LEKTService 相关代码 |
| F8 | `server.py:31-39` | SKILL_NAMES 硬编码 |

### 2.3 淘汰的 Schema 模型（2 个）

| 序号 | 模型 | 文件 |
|------|------|------|
| S1 | `CorrectResponse` | `models.py:11-15` |
| S2 | `EvaluateResponse` | `models.py:18-22` |

---

## 三、需要改造的接口（保留但切换数据源）

### 3.1 改造概览

| 序号 | 接口 | 当前数据源 | 改为 TCN 数据源 | 前端是否感知 |
|------|------|----------|---------------|------------|
| R1 | `POST /api/v1/kt/learning-path` | `logic_matrix.npy` | TCN `report.nodes` + 图谱缓存 | **否**（不变） |
| R2 | `POST /api/v1/kt/prerequisites` | `logic_matrix.npy` | TCN `report` 的 `parents` dict + 图谱缓存重建 dependents | **否**（不变） |
| R3 | `GET /api/v1/kt/skill-graph` | `logic_matrix.npy` | 图谱缓存 + TCN `report.nodes` 叠加 mastery | **增字段**（前向兼容） |
| R4 | `GET /api/v1/kt/states` | 此前未实现 | TCN `report.nodes` → `{node_id: mastery}` | **新增** |

### 3.2 R1：学习路径推荐 — 改造方案

**当前实现**（`lekt_service.py:209-253`）：从 `logic_matrix.npy` 读边，NumPy 贪心算法。

**改造后**（`app/services/kt_service.py`，新建）：
```python
async def recommend_learning_path(
    user_hash: str, 
    graph_cache: dict,  # {node_id: {name, parents: [node_id, ...], dependents: [node_id, ...]}}
    top_k: int = 5
) -> dict:
    # 1. 调 TCN report 获取掌握度（nodes dict 稀疏，未练习的默认 0.5）
    report = await tcn_client.get_report(user_hash)
    nodes_mastery = report["nodes"]  # dict: {node_id: {mastery, parents}}
    
    # 2. 合并图谱缓存结构和 report 掌握度
    candidates = []
    for node_id, info in graph_cache.items():
        mastery = nodes_mastery.get(node_id, {}).get("mastery", 0.5)
        if mastery >= 0.8:
            continue  # 已掌握
        
        # 检查先修是否满足
        prereqs_ok = True
        for parent_id in info.get("parents", []):
            parent_mastery = nodes_mastery.get(parent_id, {}).get("mastery", 0.5)
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
            "priority_score": importance + (1 - mastery),
        })
    
    candidates.sort(key=lambda x: x["priority_score"], reverse=True)
    return {"recommendations": candidates[:top_k]}
```

接口响应结构**不变**：
```json
{
  "recommendations": [
    {
      "skill_id": "math:linear_equation",
      "skill_name": "一元一次方程",
      "current_mastery": 0.45,
      "importance": 3,
      "priority_score": 3.55
    }
  ]
}
```

### 3.3 R2：先修关系查询 — 改造方案

**改造后**：
```python
async def get_prerequisites(
    user_hash: str, 
    skill_id: str, 
    graph_cache: dict
) -> dict:
    # 1. 调 TCN report
    report = await tcn_client.get_report(user_hash)
    nodes = report["nodes"]
    
    # 2. 查图谱缓存获取节点名和先修/后继关系
    node_info = graph_cache.get(skill_id, {})
    
    # 3. 从 report 的 parents dict 获取先修节点的 mastery
    parents_mastery = nodes.get(skill_id, {}).get("parents", {})
    prerequisites = []
    for parent_id, parent_mastery in parents_mastery.items():
        prerequisites.append({
            "id": parent_id,
            "name": graph_cache.get(parent_id, {}).get("name", parent_id),
            "mastery": parent_mastery,
        })
    
    # 4. 从图谱缓存获取后继节点
    dependents = []
    for dep_id in node_info.get("dependents", []):
        dep_mastery = nodes.get(dep_id, {}).get("mastery", 0.5)
        dependents.append({
            "id": dep_id,
            "name": graph_cache.get(dep_id, {}).get("name", dep_id),
            "mastery": dep_mastery,
        })
    
    return {
        "skill": {
            "id": skill_id,
            "name": node_info.get("name", skill_id),
        },
        "prerequisites": prerequisites,
        "dependents": dependents,
    }
```

接口响应结构**不变**（只增加父节点 mastery 字段）：
```json
{
  "skill": {"id": "math:linear_equation", "name": "一元一次方程"},
  "prerequisites": [
    {"id": "math:addition", "name": "加法", "mastery": 0.95}
  ],
  "dependents": [
    {"id": "math:quadratic_equation", "name": "一元二次方程", "mastery": 0.85}
  ]
}
```

### 3.4 R3：技能图谱 — 改造方案

**改造后**：
```python
async def get_skill_graph(user_hash: str, graph_cache: dict) -> dict:
    # 1. 调 TCN report 获取用户掌握度
    report = await tcn_client.get_report(user_hash)
    user_nodes = report["nodes"]
    
    # 2. 从图谱缓存构建全量 skills + edges，叠加用户掌握度
    skills = []
    for node_id, info in graph_cache.items():
        skill_entry = {
            "id": node_id,
            "name": info["name"],
        }
        # 叠加用户掌握度（只给练习过的节点，未练习的不加该字段）
        if node_id in user_nodes:
            skill_entry["mastery"] = user_nodes[node_id]["mastery"]
            skill_entry["confidence"] = user_nodes[node_id]["confidence"]
        skills.append(skill_entry)
    
    # 3. 从图谱缓存提取边
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
```

**响应**（新增 `mastery`/`confidence`，仅练习过的节点有这两个字段）：
```json
{
  "skills": [
    {"id": "math:addition", "name": "加法", "mastery": 0.95, "confidence": 0.0},
    {"id": "math:quadratic_equation", "name": "一元二次方程", "mastery": 0.85, "confidence": 0.72},
    {"id": "math:calculus_intro", "name": "微积分入门"}
  ],
  "edges": [{"source": "math:addition", "target": "math:quadratic_equation"}],
  "total_skills": 503,
  "total_edges": 1200
}
```

### 3.5 R4：认知状态查询（新增）

```python
@router.get("/states")
async def get_skill_states(
    current_user: dict = Depends(get_current_active_user),
):
    user_hash = current_user["user_hash"]
    report = await tcn_client.get_report(user_hash)
    nodes = report["nodes"]
    # TCN report.nodes dict → {node_id: mastery}
    states = {node_id: info["mastery"] for node_id, info in nodes.items()}
    return states
```

**响应**：
```json
{
  "math:addition": 0.95,
  "math:linear_equation": 0.91,
  "math:quadratic_equation": 0.85
}
```

---

## 四、TCN 客户端完整接入方案

### 4.1 新增文件

```
zhishi-master/backend/
├── app/
│   ├── core/
│   │   └── tcn_config.py          # [新建] TCN 连接配置
│   ├── services/
│   │   ├── tcn_client.py           # [新建] TCN HTTP 客户端
│   │   └── graph_cache.py          # [新建] 图谱数据缓存
│   ├── models/
│   │   └── tcn_schemas.py          # [新建] TCN 接口请求/响应模型
```

### 4.2 TCN 配置

```python
# app/core/tcn_config.py
import os

TCN_BASE_URL = os.getenv("TCN_BASE_URL", "http://127.0.0.1:8001")
TCN_ADMIN_TOKEN = os.getenv("TCN_ADMIN_TOKEN", "")
TCN_TIMEOUT = int(os.getenv("TCN_TIMEOUT", "5"))
TCN_MAX_RETRIES = int(os.getenv("TCN_MAX_RETRIES", "2"))
TCN_ENABLED = os.getenv("TCN_ENABLED", "true").lower() == "true"
TCN_SECRET_SALT = os.getenv("TCN_SECRET_SALT", "zhixu-tcn-salt-2026")
```

### 4.3 TCN 客户端实现（修正版）

```python
# app/services/tcn_client.py
import hashlib
import logging
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

from app.core.tcn_config import (
    TCN_BASE_URL,
    TCN_ADMIN_TOKEN,
    TCN_ENABLED,
    TCN_MAX_RETRIES,
    TCN_SECRET_SALT,
    TCN_TIMEOUT,
)

logger = logging.getLogger(__name__)


class TCNClient:
    """TCN 引擎层 HTTP 客户端 — 单例"""

    _instance: Optional["TCNClient"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._client = httpx.AsyncClient(
            base_url=TCN_BASE_URL.rstrip("/"),
            timeout=httpx.Timeout(TCN_TIMEOUT),
            headers={"X-Admin-Token": TCN_ADMIN_TOKEN},
        )
        self._enabled = TCN_ENABLED

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def generate_user_hash(user_id: int) -> str:
        """生成用户哈希，确保跨设备一致。sha256 前 32 位 hex（TCN 无长度限制）"""
        raw = f"{user_id}:{TCN_SECRET_SALT}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    async def health_check(self) -> dict:
        """探测 TCN 引擎可用性"""
        try:
            resp = await self._client.get("/health")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"TCN 健康检查失败: {e}")
            self._enabled = False
            return {"status": "unreachable", "nodes": 0}

    # ─────────────────────────────────────────────
    # /v1/user/* 端点（无需鉴权）
    # ─────────────────────────────────────────────

    @retry(stop=stop_after_attempt(TCN_MAX_RETRIES), wait=wait_fixed(1))
    async def predict(
        self,
        user_hash: str,
        current_node: str,
        user_action: str,
        domain_id: str = "",
        step_index: int = 0,
        session_id: str = "",
    ) -> dict:
        """
        POST /v1/user/predict
        请求体含 7 个字段（含 api_key=""），返回 8 个字段
        """
        if not self._enabled:
            return {
                "lvr": 0.0, "vs": 0.0,
                "diagnosis": "", "recommended_backtrack": None,
                "node_mastery": {},
                "epsilon_used": 0.05, "training_phase": "degraded",
                "_degraded": True,
            }

        payload = {
            "api_key": "",
            "user_hash": user_hash,
            "domain_id": domain_id,
            "current_node": current_node,
            "user_action": user_action,
            "step_index": step_index,
            "session_id": session_id,
        }

        resp = await self._client.post("/v1/user/predict", json=payload)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(TCN_MAX_RETRIES), wait=wait_fixed(1))
    async def get_profile(self, user_hash: str) -> dict:
        """
        GET /v1/user/profile/{user_hash}
        返回 5 个字段（含 graph_version 和 node_count）
        """
        if not self._enabled:
            return {
                "total_steps": 0, "global_lvr": 0.0,
                "graph_version": 0, "node_count": 0,
            }
        resp = await self._client.get(f"/v1/user/profile/{user_hash}")
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(TCN_MAX_RETRIES), wait=wait_fixed(1))
    async def get_report(self, user_hash: str) -> dict:
        """
        GET /v1/user/report/{user_hash}
        返回顶层 object: {user_hash, global_lvr, total_steps, nodes}
        nodes 是 dict，key 为 "domain:node_id"，value 为 {mastery, confidence, parents}
        parents 是 dict，{parent_node_id: mastery_float}
        """
        if not self._enabled:
            return {
                "user_hash": user_hash,
                "global_lvr": 0.0,
                "total_steps": 0,
                "nodes": {},
            }
        resp = await self._client.get(f"/v1/user/report/{user_hash}")
        resp.raise_for_status()
        return resp.json()

    # ─────────────────────────────────────────────
    # /admin/graph/* 端点（需 X-Admin-Token）
    # ─────────────────────────────────────────────

    @retry(stop=stop_after_attempt(TCN_MAX_RETRIES), wait=wait_fixed(1))
    async def get_graph_domains(self) -> list[str]:
        """GET /admin/graph/domains — 获取所有域名列表"""
        if not self._enabled:
            return []
        resp = await self._client.get("/admin/graph/domains")
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(TCN_MAX_RETRIES), wait=wait_fixed(1))
    async def get_graph_data(self, domain: str) -> dict:
        """
        GET /admin/graph/data/{domain}
        返回单域完整图谱：nodes[{id, name, status}] + edges[{from, to, weight, relation, edge_type}]
        """
        if not self._enabled:
            return {"nodes": [], "edges": []}
        resp = await self._client.get(f"/admin/graph/data/{domain}")
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()


# 全局单例
tcn_client = TCNClient()
```

### 4.4 TCN 数据模型

```python
# app/models/tcn_schemas.py
from pydantic import BaseModel
from typing import Optional


class TCNPredictRequest(BaseModel):
    api_key: str = ""
    user_hash: str
    domain_id: str = ""
    current_node: str
    user_action: str  # "correct" | "incorrect"
    step_index: int = 0
    session_id: str = ""


class TCNPredictResponse(BaseModel):
    user_hash: str
    lvr: float
    vs: float
    diagnosis: str = ""
    recommended_backtrack: Optional[str] = None
    node_mastery: dict[str, float] = {}  # 前 10 个节点
    epsilon_used: float = 0.05
    training_phase: str = "unknown"


class TCNProfileResponse(BaseModel):
    user_hash: str = ""
    total_steps: int = 0
    global_lvr: float = 0.0
    graph_version: int = 0
    node_count: int = 0


class TCNHealthResponse(BaseModel):
    status: str
    nodes: int
    graph_version: int = 0
    dense_mode: bool = False
    constraint: str = "static"
    model: str = "lekt"
```

### 4.5 应用启动集成

```diff
# server.py

- from lekt_service import LEKTService
+ from app.services.tcn_client import tcn_client
+ from app.services.graph_cache import init_graph_cache, get_graph_cache
+ from app.core.tcn_config import TCN_BASE_URL

- SKILL_NAMES = { ... }

  @asynccontextmanager
  async def lifespan(app: FastAPI):
      # 1. 初始化数据库
      ...

-     # 2. 加载 LEKT 推理模型
-     lekt = LEKTService(...)
-     app.state.lekt = lekt

+     # 2. 探测 TCN 引擎
+     print(f"[Server] 正在探测 TCN 引擎 ({TCN_BASE_URL})...")
+     health = await tcn_client.health_check()
+     if health.get("status") == "ok":
+         print(f"[Server] TCN 引擎就绪，{health.get('nodes', '?')} 个技能节点")
+         
+         # 3. 加载图谱缓存（node_id → 中文名称 + 先修/后继关系）
+         print("[Server] 正在加载图谱数据缓存...")
+         await init_graph_cache()
+         cache = get_graph_cache()
+         print(f"[Server] 图谱缓存就绪，{len(cache)} 个节点")
+     else:
+         print("[Server] 警告: TCN 引擎不可达，KT 功能将降级")

-     # 4. 初始化 AgentManager
+     # 4. 初始化 AgentManager
      ...

      yield

+     await tcn_client.close()
      logger.info("服务关闭")
```

### 4.6 降级策略

| 场景 | 降级行为 | 影响范围 |
|------|---------|---------|
| TCN 不可达 | `_enabled=False`，所有接口返回默认值（lvr=0, mastery=0.5, nodes={}） | KT 功能静默降级，Chat 等主流程不受阻 |
| `/admin/graph/*` 不可达 | 图谱缓存为空，前端显示 `node_id` 裸 ID 而非中文名 | 仅影响名称展示，不影响功能 |
| predict 报错（retry 耗尽） | 返回 `_degraded=True` | 单次知识状态不更新 |
| report 报错 | 返回空 `nodes: {}` | states/skill-graph 返回空数据 |

---

## 五、图谱数据缓存方案（含中文名称）

### 5.1 设计目标

TCN `report` 接口不含节点中文名称。`/admin/graph/data/{domain}` 含全量 `id + name + edges`。建议启动时全量拉取，本地缓存，后续 O(1) 查询。

### 5.2 数据结构

```python
# app/services/graph_cache.py
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 全局缓存: {node_id: {"name": "加法", "parents": ["math:arithmetic"], "dependents": ["math:multiplication"]}}
_graph_cache: dict = {}


def get_graph_cache() -> dict:
    """获取图谱缓存（O(1)）"""
    return _graph_cache


async def init_graph_cache():
    """启动时加载所有域的图谱数据到缓存"""
    global _graph_cache
    from app.services.tcn_client import tcn_client

    if not tcn_client.is_enabled:
        logger.warning("TCN 不可达，跳过图谱缓存初始化")
        return

    try:
        # 1. 获取所有域
        domains = await tcn_client.get_graph_domains()
        if not domains:
            logger.warning("图谱域列表为空")
            return

        # 2. 逐域拉取全量数据
        for domain in domains:
            try:
                data = await tcn_client.get_graph_data(domain)
                nodes = data.get("nodes", [])
                edges = data.get("edges", [])

                # 构建 node_id → {name, parents, dependents}
                for node in nodes:
                    node_id = node["id"]
                    if node_id not in _graph_cache:
                        _graph_cache[node_id] = {
                            "name": node.get("name", node_id),
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
```

### 5.3 使用方式

```python
from app.services.graph_cache import get_graph_cache

cache = get_graph_cache()
node_info = cache.get("math:quadratic_equation")
if node_info:
    print(node_info["name"])       # "一元二次方程"
    print(node_info["parents"])    # ["math:linear_equation", "math:factoring"]
    print(node_info["dependents"]) # ["math:calculus_intro"]
```

---

## 六、分步实施计划

### Step 1：新增 TCN 客户端 + 图谱缓存（1 天）

| 任务 | 文件 | 产出 |
|------|------|------|
| 1.1 | 新建 `app/core/tcn_config.py` | TCN 连接配置（含 `TCN_ADMIN_TOKEN`），从 `.env` 读取 |
| 1.2 | 新建 `app/services/tcn_client.py` | TCNClient：predict(7字段请求+8字段响应)/profile/report/get_graph_domains/get_graph_data |
| 1.3 | 新建 `app/services/graph_cache.py` | 启动时拉取全量图谱 → 本地 dict 缓存 {node_id→{name,parents,dependents}} |
| 1.4 | 新建 `app/models/tcn_schemas.py` | TCNPredictRequest/Response, TCNProfileResponse, TCNHealthResponse |
| 1.5 | 修改 `server.py` 启动流程 | TCN health 探测 + `init_graph_cache()` |
| 1.6 | `.env` 新增变量 | `TCN_BASE_URL`、`TCN_ADMIN_TOKEN` |
| 1.7 | User 模型扩展 | `users` 表新增 `user_hash` 字段，注册时自动生成 |

**验证**：启动日志输出 "TCN 引擎就绪，503 个技能节点" + "图谱缓存就绪，503 个节点"。

### Step 2：淘汰重复接口与文件（1 天）

| 任务 | 操作 |
|------|------|
| 2.1 | 删除 `POST /api/v1/kt/correct` 路由 |
| 2.2 | 删除 `POST /api/v1/kt/evaluate` 路由 |
| 2.3 | 从 `kt.py` 移除 `CorrectResponse`/`EvaluateResponse` |
| 2.4 | 删除 `models.py` 中 `CorrectResponse`/`EvaluateResponse` |
| 2.5 | 删除 `lekt_service.py`（整个文件） |
| 2.6 | 删除 `lekt_api.cp314-win_amd64.pyd` |
| 2.7 | 删除 `logic_matrix.npy` |
| 2.8 | 删除 `generate_matrix.py` |
| 2.9 | 删除 `my_skills.csv` |
| 2.10 | 删除 `app/core/lekt_state.py` |
| 2.11 | 清理 `server.py` 中 LEKTService/SKILL_NAMES 残留 |
| 2.12 | 删除 `kt_backend/` 整个目录 |

**验证**：`git grep "lekt_service\|LEKTService\|get_lekt\|CorrectResponse\|EvaluateResponse\|logic_matrix"` 无残留。

### Step 3：改造保留接口（2 天）

| 任务 | 文件 | 操作 |
|------|------|------|
| 3.1 | `app/api/v1/kt.py` | 移除 `get_lekt` Depends，注入 `tcn_client` + `get_graph_cache` |
| 3.2 | 新建 `app/services/kt_service.py` | `recommend_learning_path()` / `get_prerequisites()` / `get_skill_graph()` — 基于 TCN report + graph_cache |
| 3.3 | `app/api/v1/kt.py` → 3 个改造路由 | 调用 kt_service 对应方法 |
| 3.4 | `app/api/v1/kt.py` → 新增 `get_skill_states` | `report.nodes → {node_id: mastery}` |
| 3.5 | `app/schemas/` schema 更新 | `SkillInfo` 增加可选字段 `mastery`/`confidence`；`PrerequisiteResponse` 增加 `mastery` |
| 3.6 | 前端 `zhishi-web/src/lib/api/kt.ts` | 确认 4 个改造接口响应结构兼容 |

**验证**：`/api/v1/kt/states` 返回 `{"math:addition": 0.95, ...}`；`/api/v1/kt/skill-graph` 含 `mastery` 字段。

### Step 4：Chat 流程集成 TCN predict（2 天）

| 任务 | 文件 | 操作 |
|------|------|------|
| 4.1 | `app/api/v1/chat.py` | SSE 响应完成后，异步调 `tcn_client.predict()` |
| 4.2 | ChatRequest 扩展 | 增加可选字段 `tc_node_id` / `tc_user_action` / `tc_domain_id` |
| 4.3 | Chat SSE 响应 | 增加 `lvr` / `diagnosis` / `recommended_backtrack` 透传 |
| 4.4 | Tutor 流程 | 辅导回答正确/错误后异步调 predict |

**验证**：完成一次 Chat 对话后，`/api/v1/kt/states` 能看到掌握度变化。

### Step 5：等待 TCN 4 个新接口（summary/gaps/vulnerabilities/lvr_alert）

TCN 方承诺 2 天内交付。届时补充接入。

### Step 6：清理与文档（0.5 天）

| 任务 | 说明 |
|------|------|
| 6.1 | 更新 `requirements.txt`（新增 `httpx`、`tenacity`） |
| 6.2 | 更新 `docs/API.md` |
| 6.3 | 更新前端 `zhishi-web/src/lib/api/kt.ts`（移除 `correctStates`/`evaluateStates`） |

---

## 七、需要 TCN 新增的接口（2 天内交付）

> **来源**：`TCN_API_CONFIRMATION_REPLY.md` 第 2 节，以下为草案，字段名以最终交付文档为准。

| 编号 | 接口 | 端点 | 优先级 | 用途 | 状态 |
|------|------|------|--------|------|------|
| N1 | 用户状态摘要 | `GET /v1/user/summary/{user_hash}` | **P0** | LLM System Prompt 注入 | 2 天内交付 |
| N2 | 先修断层查询 | `GET /v1/user/gaps/{user_hash}` | P1 | 先修提示、断层诊断、错题归因 | 2 天内交付 |
| N3 | 认知脆弱点 | `GET /v1/user/vulnerabilities/{user_hash}` | P1 | 推理模式伪掌握预警 | 2 天内交付 |
| N4 | LVR 预警状态 | `GET /v1/user/lvr_alert/{user_hash}` | P1 | 前端预警 Banner | 2 天内交付 |

**N1 summary 草案格式**：
```json
{
  "user_hash": "a3f9c1d2e8b7...",
  "mastered_count": 127,
  "total_count": 503,
  "mastery_rate": 0.25,
  "global_lvr": 0.12,
  "weakest_domain": "math_calculus",
  "most_active_node": "math:quadratic_equation",
  "last_updated_step": 47,
  "total_steps": 47
}
```

> ⚠️ `last_updated_step` 是整数步骤序号，**不是时间戳**。TCN 不记录 datetime。如需时间信息，软件层自行记录每次 predict 调用的时间。

**N2 gaps 草案格式**：
```json
[
  {
    "node_id": "math:quadratic_equation",
    "mastery": 0.85,
    "severity": 0.38,
    "missing_prerequisites": [
      {"node_id": "math:linear_equation", "mastery": 0.42, "gap": 0.38}
    ]
  }
]
```

**N3 vulnerabilities 草案格式**：
```json
[
  {
    "node_id": "math:quadratic_equation",
    "mastery": 0.88,
    "weakest_prerequisite_id": "math:factoring",
    "weakest_prerequisite_mastery": 0.21,
    "risk_gap": 0.67,
    "risk_level": "high"
  }
]
```

**N4 lvr_alert 草案格式**：
```json
{
  "global_lvr": 0.28,
  "alert_level": "warning",
  "top_violations": [
    {"parent_id": "math:linear_equation", "parent_mastery": 0.41, "child_id": "math:quadratic_equation", "child_mastery": 0.88, "gap": 0.42}
  ]
}
```

---

## 八、验证检查表

### 8.1 代码审计

- [ ] `git grep "lekt_service"` 返回空
- [ ] `git grep "LEKTService"` 返回空
- [ ] `git grep "get_lekt"` 返回空
- [ ] `git grep "CorrectResponse"` 返回空
- [ ] `git grep "EvaluateResponse"` 返回空
- [ ] `git grep "logic_matrix"` 返回空
- [ ] `lekt_api.cp314-win_amd64.pyd` 已删除
- [ ] `logic_matrix.npy` 已删除
- [ ] `kt_backend/` 目录已删除
- [ ] `app/services/tcn_client.py` 存在
- [ ] `app/services/graph_cache.py` 存在
- [ ] `app/models/tcn_schemas.py` 存在
- [ ] `server.py` 不含 LEKTService 导入

### 8.2 功能验证

- [ ] 后端启动日志："TCN 引擎就绪，503 个技能节点"
- [ ] 后端启动日志："图谱缓存就绪，503 个节点"
- [ ] TCN 不可达时，`/api/v1/kt/states` 返回 `{}`（不报 500）
- [ ] TCN 可达时，`/api/v1/kt/skill-graph` 返回含 `name` 和 `mastery` 字段
- [ ] TCN 可达时，`/api/v1/kt/learning-path` 返回推荐路径
- [ ] TCN 可达时，`/api/v1/kt/prerequisites` 返回先修关系（含 parents mastery）
- [ ] `/api/v1/kt/correct` 返回 404
- [ ] `/api/v1/kt/evaluate` 返回 404
- [ ] Chat 流程完成后，`/api/v1/kt/states` 反映 mastery 变化

### 8.3 回归验证

- [ ] `/api/v1/auth/login` 正常
- [ ] `/api/v1/chat` SSE 流式正常
- [ ] `/api/v1/kb/upload` 正常
- [ ] `/api/v1/quiz/*` 正常
- [ ] `/api/v1/tutor/*` 正常
- [ ] `/health` 正常

### 8.4 TCN 对接验证（按 TCN 回复 C1-C5 纠正后）

- [ ] `tcn_client.get_report()` 返回类型为 `dict`（object），不是 `list`
- [ ] report.nodes 的 key 格式为 `"domain:node_id"`
- [ ] parents 解析为 dict `{parent_id: mastery}`
- [ ] health 节点数读取字段为 `nodes`（不是 `skills_count`）
- [ ] `tcn_client.predict()` 请求含 `api_key: ""`
- [ ] predict 响应未将 `node_mastery` 当作 current_node 处理
- [ ] 图谱缓存正确包含 `name` / `parents` / `dependents`

---

## 附录 A：TCN 回复纠正追踪

| 编号 | 纠正项 | 原方案（错误） | 确认后（正确） | 修正位置 |
|------|--------|-------------|-------------|---------|
| C1 | report 顶层结构 | `list[dict]` | `object`（user_hash, global_lvr, total_steps, nodes 四个 key） | 4.3 `get_report()` 返回类型 |
| C2 | parents 类型 | `[{node_id, mastery}]` | `dict`：`{parent_id: mastery_float}` | 3.3/3.4 的 parents 解析逻辑 |
| C3 | health 节点数字段名 | `skills_count` | `nodes` | 4.3 `health_check()` |
| C4 | predict node_mastery | current_node 掌握度 | 前 10 个节点（索引 0–9） | 4.3 predict 注释 + 使用方式 |
| C5 | confidence 可用性 | 始终有值 | rule 模式始终 0.0 | 3.4 skill-graph 响应说明 |
| — | node_id 格式 | `skill_0` | `domain:node_id`（如 `math:quadratic_equation`） | 全文 |
| — | predict 请求缺 api_key | 未传 | 需传 `api_key: ""` | 4.3 `predict()` |
| — | predict 响应少 5 字段 | 3 个 | 8 个（含 diagnosis/backtrack/node_mastery/epsilon/training_phase） | 4.4 `TCNPredictResponse` |
| — | profile 多字段 | 3 个 | 5 个（含 graph_version/node_count） | 4.4 `TCNProfileResponse` |
| — | 图谱数据获取 | 无方案 | `/admin/graph/domains` + `/admin/graph/data/{domain}` | 第 5 章 + 4.3 |
| — | 节点中文名获取 | 假设 report 含 name | report 不含，需单独拉图谱 | 第 5 章 graph_cache |

---

## 附录 B：文件变更汇总

| 操作 | 文件 | 行数 |
|------|------|------|
| **新建** | `app/core/tcn_config.py` | ~20 |
| **新建** | `app/services/tcn_client.py` | ~180 |
| **新建** | `app/services/graph_cache.py` | ~90 |
| **新建** | `app/services/kt_service.py` | ~120 |
| **新建** | `app/models/tcn_schemas.py` | ~40 |
| **修改** | `server.py` | ~20 改 |
| **修改** | `app/api/v1/kt.py` | ~50 改（删 20 + 改 30 + 增 states 路由） |
| **修改** | `app/models/models.py` | ~5 改（删 2 schema） |
| **修改** | `app/api/v1/chat.py` | ~40 增（predict 异步集成） |
| **修改** | `.env` / `.env.example` | +5 行 |
| **删除** | `lekt_service.py` | -305 |
| **删除** | `lekt_api.cp314-win_amd64.pyd` | - |
| **删除** | `logic_matrix.npy` | - |
| **删除** | `generate_matrix.py` | -153 |
| **删除** | `my_skills.csv` | -12 |
| **删除** | `app/core/lekt_state.py` | -7 |
| **删除** | `kt_backend/` (整个目录) | - |

---

*本方案 v2.0 基于 TCN 源码级确认回复修订，所有接口字段、类型、格式均已核实可对接。OpenAPI 文档：`http://127.0.0.1:8001/docs`。*