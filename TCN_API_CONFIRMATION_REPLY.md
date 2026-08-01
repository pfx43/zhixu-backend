# TCN 方对接确认回复

> **版本**：v1.4，2026-07-13  
> **发件方**：TCN 算法方  
> **收件方**：软件开发层

---

## 📌 阅读本文档前须知

本文档分为两类内容，性质不同，请注意区分：

**第一类：已确认内容（第一节 + 第三节）**

- 内容来源：直接从 TCN 服务端源码逐行核查提取
- 准确性：字段名称、类型、格式、特殊行为均已核实，不依赖推断
- 状态：**内容锁定，不会变更**，除非 TCN 方主动通知接口变更
- 可操作性：软件层收到后可立即按此对接

**第二类：草案内容（第二节，4 个新增接口）**

- 内容来源：基于 TCN 现有数据结构设计的接口方案，**代码尚未实现**
- 状态：2 天内完成开发，交付后会另发最终格式文档
- 注意：**草案字段名可能微调，请勿按草案提前写死代码**
- 可操作性：了解接口方向和字段含义即可，等最终文档后再实现

| 章节 | 类型 | 可否立即对接 |
|------|------|------------|
| 第一节（4 个已有接口） | ✅ 源码确认 | 立即对接 |
| 第二节（4 个新增接口） | ⚠️ 草案 | 等 2 天内交付通知 |
| 第三节（通用问题） | ✅ 源码确认 | 立即参考 |

---

## ⚠️ 最高优先级纠正（先读）

软件层清单中有 **5 处关键错误**，会直接导致解析代码出 bug：

| # | 纠正项 | 内容 |
|---|--------|------|
| 🔴 C1 | report 顶层结构 | `GET /v1/user/report` 顶层是 **object**，不是 array |
| 🔴 C2 | report parents 字段类型 | `parents` 是 **dict**（`{"node_id": mastery_float}`），不是对象数组 |
| 🔴 C3 | health 节点数字段名 | 字段名是 **`nodes`**，不是 `skills_count` |
| 🔴 C4 | predict node_mastery 内容 | **`node_mastery` 返回的不是当前节点**，而是图谱中前 10 个节点（索引 0–9）的掌握度（详见 1.2 节） |
| 🟡 C5 | report confidence 字段 | 当前运行模式（rule）下 `confidence` **始终为 0.0**，仅在 LEKT/GKT/AKT 模型下有实际值 |

---

## 一、已提供接口 — 响应格式确认

### 1.1 `GET /v1/user/report/{user_hash}`

**真实响应 JSON（源码核查）**：

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

**逐字段回答**：

| # | 确认项 | 实际值 | 备注 |
|---|--------|--------|------|
| 1 | 顶层数据类型 | **`object`** | 不是 array！4 个顶层 key：`user_hash`、`global_lvr`、`total_steps`、`nodes` |
| 2 | 完整 JSON 响应示例 | 见上方 | |
| 3 | 节点唯一标识 | `nodes` object 的 **key**（string） | 格式为 `domain:node_id`，如 `"math:quadratic_equation"` |
| 4 | 节点掌握度 | ✅ 存在，字段名 `mastery`，float 0–1 | |
| 5 | 节点中文名称 | ❌ **不存在** | report 只含算法状态，无图谱 name 字段。获取方式见下方说明 |
| 6 | 节点 index 编号 | ❌ **不存在** | |
| 7 | 节点可信度 confidence | ⚠️ 存在，字段名 `confidence`，但**当前 rule 模式下始终为 0.0**；只有切换为 LEKT/GKT/AKT 模型时才有实际值 | |
| 8 | 先修父节点 | ✅ 存在，字段名 `parents` | 类型为 **dict** `{parent_node_id: mastery_float}`，不是对象数组 |
| 9 | 父节点是否含 mastery | ✅ 是，`parents` dict 的 value 就是该父节点当前掌握度 | |
| 10 | 是否有后继节点字段 | ❌ **不存在** | 需通过 `/admin/graph/data/{domain}` 拿边数据后本地推导 |

> **nodes 覆盖范围说明**：`nodes` dict 只包含该用户**实际练习过的节点**（稀疏存储）。rule 模式下每次 predict 只写一个节点；LEKT/GKT/AKT 模式下每次 predict 写全部节点。未练习过的节点不出现在 nodes 中（默认掌握度 0.5）。

> **节点中文名获取**：调用 `GET /admin/graph/data/{domain}` 返回完整图谱，`nodes[].id` 对应节点标识，`nodes[].name` 为中文名称。建议软件层**启动时拉一次所有域的图谱**，本地建 `id → name` 映射表，后续渲染直接查表。

---

### 1.2 `POST /v1/user/predict`

**请求体（完整字段）**：

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

- `api_key`：当前版本**未验证**，传空字符串即可
- `domain_id`：可传空字符串，建议传（用于 event 记录）
- `step_index`：会话内步骤序号，从 0 开始递增，影响 LVR 计算时序
- `session_id`：日志关联用，可选

**真实完整响应**：

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

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_hash` | string | 同请求 |
| `lvr` | float | 全局 LVR（先修偏序违反率），0–1 |
| `vs` | float | Violation Severity（违反严重度），0–1 |
| `diagnosis` | string | 诊断描述文本，含具体违反边信息 |
| `recommended_backtrack` | string or null | 建议回溯的节点 id；无违反时为 `null` |
| `node_mastery` | dict | ⚠️ **图谱中前 10 个节点**（按索引 0–9 顺序）的掌握度，不是 current_node 的掌握度 |
| `epsilon_used` | float | 本次推理的约束阈值（static 模式固定 0.05） |
| `training_phase` | string | 当前版本**硬编码为 `"unknown"`** |

> **⚠️ `node_mastery` 重要说明**：该字段返回的是图谱索引最小的前 10 个节点的掌握度，**不保证包含 current_node**。如果软件层需要当前节点练习后的最新掌握度，应在 predict 返回后调用 `GET /v1/user/report/{user_hash}` 查询具体节点的 mastery。

**补充确认**：

| # | 确认项 | 实际值 |
|---|--------|--------|
| 11 | 完整响应字段 | 8 个字段，见上表 |
| 12 | `node_mastery` 含义 | 前 10 个节点更新**后**的掌握度（不是 delta，不是 current_node） |
| 13 | `user_action` 枚举值 | 仅 **`"correct"`** 和 **`"incorrect"`** 两个值。非 `"correct"` 一律视为 incorrect，无其他枚举值 |
| 14 | 新用户首次调用是否需要初始化 | **直接调用即可**，无需初始化。初始掌握度默认 0.5，首次调用时自动创建用户状态 |

---

### 1.3 `GET /v1/user/profile/{user_hash}`

**真实响应**：

```json
{
  "user_hash": "a3f9c1d2e8b7...",
  "total_steps": 47,
  "global_lvr": 0.12,
  "graph_version": 3,
  "node_count": 503
}
```

| # | 确认项 | 实际值 |
|---|--------|--------|
| 15 | 完整响应字段 | 5 个字段，见上（与清单预测基本一致，多一个 `graph_version`） |

> **注意**：`node_count` 是该用户已练习的节点数（稀疏存储），不是图谱总节点数。图谱总节点数通过 `GET /health` 的 `nodes` 字段查询。

---

### 1.4 `GET /health`

**真实响应**：

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

| # | 确认项 | 实际值 |
|---|--------|--------|
| 16 | 完整响应字段 | 6 个字段，见上 |
| 17 | 节点数字段名 | ⚠️ **`nodes`**，不是 `skills_count`，需修改代码 |
| 18 | 是否返回图版本号 | ✅ 存在，字段名 `graph_version`（int） |

---

## 二、需要 TCN 新增的接口

> **排期：以下 4 个接口将在 2 天内完成交付，交付后主动通知并提供最终格式文档。**  
> **以下为设计草案，字段名可能微调，请勿提前写死代码，以最终交付版本为准。**  
> **建议软件层：先完成第一节已有接口的修复对接，新接口到位后再接入。**

---

### 2.1 `GET /v1/user/summary/{user_hash}` — P0，2 天内

**用途**：每次 Chat 对话前注入 LLM System Prompt，三种对话模式均依赖此接口。

**可计算字段说明**：

| 字段 | 数据来源 | 可否提供 |
|------|---------|---------|
| `mastered_count` | UserMask.nodes 中 mastery > 0.7 的节点数 | ✅ 可提供 |
| `total_count` | GraphMerger.num_nodes | ✅ 可提供 |
| `global_lvr` | UserMask.global_lvr | ✅ 可提供 |
| `total_steps` | UserMask.total_steps | ✅ 可提供 |
| `weakest_domain` | 按 domain 前缀分组，取平均 mastery 最低的域 | ✅ 可提供（id 形如 `"math"`） |
| `most_active_node` | UserMask.nodes 中 last_updated_step 最大的节点 | ✅ 可提供 |
| `last_updated_step` | 最近一次更新的步骤序号（整数） | ✅ 可提供（**注意：是步骤序号，不是时间戳**，TCN 不记录 datetime） |

**草案格式（以最终交付为准）**：

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

> **说明**：TCN 内部不记录时间戳，`last_updated_step` 是整数步骤序号，不是 datetime。如软件层需要时间信息，建议在软件层记录每次调用 predict 的时间，与 `step_index` 对应存储。

---

### 2.2 `GET /v1/user/gaps/{user_hash}` — P1，2 天内

**用途**：先修提示、断层诊断、错题归因。

**计算原理**：遍历全部边（parent → child），找出 `child_mastery > parent_mastery + epsilon` 的违反边，按违反程度（gap 值）降序排列，聚合到 child 节点维度。复用现有 `engine._diagnose()` 的核心逻辑。

| # | 确认项 | 回复 |
|---|--------|------|
| 21 | 预计可交付时间 | **2 天内** |
| 22 | 返回格式 | 按 severity 降序的节点列表 |
| 23 | "严重度"计算口径 | `child_mastery - parent_mastery - epsilon`，即先修偏序违反量，不是掌握度差值绝对值 |

**草案格式（以最终交付为准）**：

```json
[
  {
    "node_id": "math:quadratic_equation",
    "mastery": 0.85,
    "severity": 0.38,
    "missing_prerequisites": [
      {
        "node_id": "math:linear_equation",
        "mastery": 0.42,
        "gap": 0.38
      },
      {
        "node_id": "math:factoring",
        "mastery": 0.31,
        "gap": 0.49
      }
    ]
  }
]
```

> **注意**：`node_name`（中文名）字段需要查图谱 name 字段，草案中暂不包含。若软件层本地已建 id→name 映射表，可自行补充。如需 TCN 直接返回，最终交付时确认。

---

### 2.3 `GET /v1/user/vulnerabilities/{user_hash}` — P1，2 天内

**用途**：推理模式"伪掌握"预警。识别高掌握度但先修未达标的节点（即 CASM 风险节点）。

**计算原理**：从违反边集合中筛选 `child_mastery > 0.7`（高掌握）且 `parent_mastery < 0.5`（先修薄弱）的情况，按 `child_mastery - parent_mastery` 降序排列。

| # | 确认项 | 回复 |
|---|--------|------|
| 24 | 预计可交付时间 | **2 天内** |
| 25 | 返回格式 | 高掌握度 + 先修缺口最大的节点列表，按风险程度降序 |

**草案格式（以最终交付为准）**：

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

> `risk_level` 分级：`high`（gap > 0.5）/ `medium`（0.3–0.5）/ `low`（< 0.3）

---

### 2.4 `GET /v1/user/lvr_alert/{user_hash}` — P1，2 天内

**用途**：前端 LVR 预警 Banner 展示 + Chat 降级策略判断。

**计算原理**：读 `UserMask.global_lvr`，按阈值分级；top violations 从 `edge_arrays()` 向量化计算违反边，取 gap 最大的前 5 条。

| # | 确认项 | 回复 |
|---|--------|------|
| 26 | 预计可交付时间 | **2 天内** |
| 27 | 预警级别分级标准 | ✅ 接受对方暂定方案：0–0.15 正常（`normal`）/ 0.15–0.35 注意（`warning`）/ >0.35 警告（`alert`） |
| 28 | 是否包含最严重先修违反边 | ✅ 返回前 5 条，按 gap 降序 |

**草案格式（以最终交付为准）**：

```json
{
  "user_hash": "a3f9c1d2e8b7...",
  "global_lvr": 0.28,
  "alert_level": "warning",
  "top_violations": [
    {
      "parent_id": "math:linear_equation",
      "parent_mastery": 0.41,
      "child_id": "math:quadratic_equation",
      "child_mastery": 0.88,
      "gap": 0.42
    },
    {
      "parent_id": "math:factoring",
      "parent_mastery": 0.21,
      "child_id": "math:quadratic_equation",
      "child_mastery": 0.88,
      "gap": 0.62
    }
  ]
}
```

---

### 2.5 图谱结构查询 — 已有替代方案，无需等新接口

| # | 确认项 | 回复 |
|---|--------|------|
| 29 | 全量图谱接口 | **现在就可用**：`GET /admin/graph/domains` 获取所有域名列表，`GET /admin/graph/data/{domain}` 获取单域完整数据（节点含 `id`/`name`/`status`，边含 `from`/`to`/`weight`/`relation`/`edge_type`） |
| 30 | 单节点查询 | 无单节点接口。建议启动时全量拉取（503 节点约 50–100KB），本地缓存后 O(1) 查询，性能无问题 |

---

## 三、通用对接问题

| # | 确认项 | 实际值 |
|---|--------|--------|
| 31 | TCN 基础 URL | ✅ `http://127.0.0.1:8001`，正确 |
| 32 | 是否需要鉴权 | `/v1/user/*` 端点**无需鉴权**，直接调用。`/admin/*` 需要 `X-Admin-Token` Header，软件层只需调 `/v1/user/*` |
| 33 | 速率限制 | **无**速率限制。2 次重试间隔 1s 的策略可以保留，但非 TCN 要求 |
| 34 | `user_hash` 格式约束 | 任意 string，无长度限制（建议 < 128 chars）。`sha256(uid+salt)` 前 32 位 hex（32字符）完全可接受 |
| 35 | Swagger / OpenAPI 文档 | ✅ **已有**：<br>• Swagger UI：`http://127.0.0.1:8001/docs`<br>• ReDoc：`http://127.0.0.1:8001/redoc`<br>• OpenAPI JSON：`http://127.0.0.1:8001/openapi.json`<br>**建议优先访问 `/docs`，可一次性解决所有字段核对** |
| 36 | report 节点总数上限 | 不固定，取决于已加载的图谱。实时总节点数查 `GET /health` 的 `nodes` 字段 |

---

## 四、建议对方行动顺序

| 优先级 | 行动 | 说明 |
|--------|------|------|
| **立即** | 访问 `http://127.0.0.1:8001/docs` 查看 OpenAPI 文档 | 一次性核对所有已有接口字段 |
| **立即** | 修复 report 解析：顶层改 object，节点 id 取 `nodes` dict 的 key | 当前逻辑错误导致功能崩溃 |
| **立即** | 修复 `parents` 解析：改为 dict，value 即为父节点 mastery | 同上 |
| **立即** | 修复 health 节点数读取：`skills_count` → `nodes` | |
| **立即** | 注意 `node_mastery` 是前 10 个节点，不是 current_node；如需当前节点最新掌握度，调 report 接口 | 避免错误理解 predict 结果 |
| **本周** | 启动时拉取图谱建 id→name 映射缓存（`/admin/graph/data/{domain}`） | 解决前端节点中文名显示 |
| **等通知** | 等待 4 个新接口（summary/gaps/vulnerabilities/lvr_alert）交付通知 | 2天内，TCN 方交付后主动通知 |
| **可延后** | predict 响应中 `diagnosis`、`recommended_backtrack` 等字段按需接入 | 不影响核心推理功能 |

---

*TCN 方，2026-07-13*  
*新增接口交付后将另发最终格式文档。如有疑问优先以 `/docs` OpenAPI 文档为准。*
