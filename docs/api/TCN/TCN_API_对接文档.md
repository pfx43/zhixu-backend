# TCN 知识追踪引擎 —— 后端对接文档（完整版）

**服务地址**：`http://47.82.118.95:8001`  
**协议**：HTTP/1.1，Content-Type: application/json  
**认证**：所有 `/v1/user/*` 接口无需认证，直接调用  
**字符编码**：UTF-8  

---

## 接口总览

| # | 方法 | 路径 | 作用 |
|---|------|------|------|
| 1 | GET | `/health` | 服务健康检查 |
| 2 | POST | `/v1/user/predict` | **核心推理：答题 → 掌握度 + 断裂检测** |
| 3 | GET | `/v1/user/profile/{user_hash}` | 学生认知画像（简版） |
| 4 | GET | `/v1/user/report/{user_hash}` | 掌握度详细报告 |
| 5 | GET | `/v1/user/summary/{user_hash}` | 按学科汇总认知状态 |
| 6 | GET | `/v1/user/lvr_alert/{user_hash}` | 先修断裂违反告警 |
| 7 | GET | `/v1/user/gaps/{user_hash}` | 知识缺口检测 |
| 8 | GET | `/v1/user/vulnerabilities/{user_hash}` | 脆弱知识点检测 |
| 9 | GET | `/v1/user/learning/content` | 学习行动类型目录 |
| 10 | GET | `/v1/user/learning/status` | Learning OS 持久化状态 |
| 11 | POST | `/v1/user/learning/goals` | 创建学习目标 |
| 12 | GET | `/v1/user/learning/goals/{user_id}` | 查询学生的学习目标列表 |
| 13 | POST | `/v1/user/learning/evidence` | 提交学习证据并更新认知状态 |
| 14 | GET | `/v1/user/learning/today` | 获取当前最优学习行动建议 |
| 15 | POST | `/v1/user/learning/actions/{action_id}/verify` | 验证学习行动并推进状态 |
| 16 | GET | `/v1/user/learning/trajectory/{user_id}` | 读取学生学习轨迹 |

---

## 一、基础接口

### 1. 健康检查

#### `GET /health`

确认服务正常运行，建议在关键调用前做前置检查。

**请求**：无请求体，无需认证

**返回示例**：
```json
{
  "status": "ok",
  "nodes": 503,
  "graph_version": 3,
  "dense_mode": false,
  "constraint": "dynamic",
  "model": "tcn_v32",
  "ready": true,
  "live": true
}
```

| 字段 | 说明 |
|------|------|
| `status` | `"ok"` = 正常 |
| `nodes` | 当前知识图谱节点数 |
| `ready` | `true` = 推理引擎就绪，可接受推理请求 |
| `graph_version` | 图版本号，图更新时递增 |

**建议**：`ready=true` 且 `status="ok"` 再向该服务转发推理请求。

---

## 二、核心推理接口

### 2. 答题推理

#### `POST /v1/user/predict`

学生每完成一道题后调用。引擎返回该学生所有相关知识节点的实时掌握度，并检测先修关系是否存在逻辑断裂（LVR）。引擎内部自动维护每个学生的历史状态，调用方只需传当前这一步。

**请求体**：
```json
{
  "user_hash": "stu_20240001",
  "current_node": "math:导数定义",
  "user_action": "correct",
  "step_index": 5,
  "domain_id": "",
  "api_key": "",
  "session_id": "session_abc123"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_hash` | string | ✅ | 学生唯一标识符，业务方自定义，建议用脱敏ID |
| `current_node` | string | ✅ | 本题对应知识点节点ID，格式 `"学科:知识点名"` |
| `user_action` | string | ✅ | `"correct"`（答对）或 `"incorrect"`（答错） |
| `step_index` | int | 否 | 该用户第几步，默认0，建议业务方自增传入 |
| `domain_id` | string | 否 | 学科ID，可留空，引擎自动从节点名推断 |
| `api_key` | string | 否 | 留空，当前版本不需要 |
| `session_id` | string | 否 | 客户端会话ID，用于日志关联，可留空 |

**节点ID格式示例**：
```
math:导数定义
math:极限
discrete_math:命题逻辑
physics:牛顿第二定律
higher_math:多元函数微分
```

**返回示例**：
```json
{
  "user_hash": "stu_20240001",
  "lvr": 0.076,
  "vs": 8.9e-7,
  "diagnosis": "LVR=0.076: Mild inconsistency.",
  "recommended_backtrack": null,
  "node_mastery": {
    "math:极限": 0.903,
    "math:导数定义": 0.845,
    "math:微积分基本定理": 0.845,
    "math:链式法则": 0.446,
    "math:泰勒展开": 0.419
  },
  "epsilon_used": 0.040,
  "architecture_version": "tcn-v3.2",
  "checkpoint_version": "product503-v1",
  "graph_version": 3,
  "solver_name": "cp_pdhg_diag",
  "solver_iterations": 164,
  "solver_converged": true,
  "solver_residual": 8.7e-5,
  "cmag": 0.0,
  "max_violation": 8.7e-5,
  "fallback_used": false
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `lvr` | float | **逻辑违反率（核心）**，0~1，>0 说明存在先修断裂，>0.15 建议触发预警 |
| `vs` | float | 违反严重度，越小越好 |
| `diagnosis` | string | 人类可读诊断文本 |
| `recommended_backtrack` | string\|null | 建议回溯补学的节点，null=无需回溯 |
| `node_mastery` | object | **各知识节点掌握度**（0~1），key=节点ID，value=掌握概率 |
| `solver_converged` | bool | 约束优化是否收敛，`false` 时丢弃本次结果 |
| `fallback_used` | bool | `false`=正常走神经网络，`true`=触发降级兜底 |

**业务使用建议**：
- `node_mastery` 掌握度 < 0.6 → 标记弱项，推送相关题
- `lvr > 0.15` → 触发知识断裂预警，引导补学先修
- `recommended_backtrack != null` → 直接展示该节点的补学引导
- `solver_converged = false` → 丢弃本次结果，记录异常日志

**错误返回**：

| 状态码 | 场景 |
|--------|------|
| 400 | 请求体格式错误或缺必填字段 |
| 404 | `current_node` 不在知识图谱中 |
| 503 | 推理引擎未就绪 |

---

## 三、用户状态查询接口

> 以下接口在学生有答题记录后生效，首次答题前查询返回 404。

### 3. 认知画像（简版）

#### `GET /v1/user/profile/{user_hash}`

**作用**：学生列表页概览，获取答题步数和全局断裂率。

**返回示例**：
```json
{
  "user_hash": "stu_20240001",
  "total_steps": 42,
  "global_lvr": 0.063,
  "graph_version": 3,
  "node_count": 35
}
```

| 字段 | 说明 |
|------|------|
| `total_steps` | 累计答题步数 |
| `global_lvr` | 全局逻辑违反率 |
| `node_count` | 已接触的知识节点数 |

---

### 4. 掌握度详细报告

#### `GET /v1/user/report/{user_hash}`

**作用**：学情报告页，返回每个节点掌握度及其先修节点掌握情况。

**返回示例**：
```json
{
  "user_hash": "stu_20240001",
  "global_lvr": 0.063,
  "total_steps": 42,
  "nodes": {
    "math:导数定义": {
      "mastery": 0.845,
      "confidence": 0.91,
      "parents": {
        "math:极限": 0.903,
        "math:函数连续性": 0.780
      }
    },
    "math:链式法则": {
      "mastery": 0.446,
      "confidence": 0.62,
      "parents": {
        "math:导数定义": 0.845
      }
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `nodes[*].mastery` | 当前掌握度（0~1） |
| `nodes[*].confidence` | 模型估计置信度 |
| `nodes[*].parents` | 该节点的先修节点及其掌握度 |

---

### 5. 认知状态概要

#### `GET /v1/user/summary/{user_hash}`

**作用**：按学科汇总掌握情况，适合大屏或管理端。

**返回示例**：
```json
{
  "user_hash": "stu_20240001",
  "diagnosis_version": "tcn-v3.2-g3",
  "total_steps": 42,
  "overall_mastery": 0.713,
  "global_lvr": 0.063,
  "lvr_level": "mild",
  "graph_version": 3,
  "domain_summary": [
    {
      "domain": "math",
      "mastery_avg": 0.782,
      "node_count": 180,
      "visited_count": 22
    },
    {
      "domain": "discrete_math",
      "mastery_avg": 0.641,
      "node_count": 120,
      "visited_count": 13
    }
  ],
  "last_active_node": "math:链式法则",
  "computed_at": "2026-08-28T08:30:00Z"
}
```

**`lvr_level` 枚举**：

| 值 | LVR 范围 | 建议动作 |
|----|---------|---------|
| `"none"` | 0 | 正常 |
| `"mild"` | 0~0.15 | 观察 |
| `"moderate"` | 0.15~0.35 | 推送补学 |
| `"severe"` | >0.35 | 强制回溯 |

---

### 6. 先修违反告警

#### `GET /v1/user/lvr_alert/{user_hash}?limit=10`

**作用**：精确列出哪对节点存在先修违反，定位具体断裂位置。

**Query 参数**：

| 参数 | 类型 | 默认值 | 范围 |
|------|------|--------|------|
| `limit` | int | 10 | 1-200 |

**返回示例**：
```json
{
  "user_hash": "stu_20240001",
  "global_lvr": 0.063,
  "lvr_level": "mild",
  "alert_code": "LVR_MILD",
  "alert_text": "轻微先修不一致，建议关注薄弱节点",
  "total_violations": 3,
  "returned_violations": 3,
  "limit": 10,
  "violations": [
    {
      "parent_node": "math:极限",
      "child_node": "math:导数定义",
      "parent_mastery": 0.44,
      "child_mastery": 0.85,
      "gap": 0.41
    }
  ],
  "backtrack_recommended": ["math:极限", "math:函数连续性"],
  "computed_at": "2026-08-28T08:30:00Z"
}
```

`backtrack_recommended`：引擎直接给出的补学节点列表，可展示给学生。

---

### 7. 知识缺口检测

#### `GET /v1/user/gaps/{user_hash}?threshold=0.6&limit=50`

**作用**：找出掌握度低于阈值且阻碍后续学习的节点（卡脖子知识点）。

**Query 参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | 50 | 最多返回条数，1-200 |
| `threshold` | float | 0.6 | 低于此值视为缺口，0.0-1.0 |

**返回示例**：
```json
{
  "user_hash": "stu_20240001",
  "mastery_threshold": 0.6,
  "total_gaps": 8,
  "returned_gaps": 8,
  "gaps": [
    {
      "node_id": "math:链式法则",
      "domain": "math",
      "mastery": 0.42,
      "children_count": 5,
      "is_visited": true
    },
    {
      "node_id": "math:泰勒展开",
      "domain": "math",
      "mastery": 0.38,
      "children_count": 3,
      "is_visited": false
    }
  ],
  "computed_at": "2026-08-28T08:30:00Z"
}
```

| 字段 | 说明 |
|------|------|
| `children_count` | 依赖该节点的后续知识点数，越多影响越广，优先补这个 |
| `is_visited` | `true`=做过题但没学好；`false`=还未接触 |

---

### 8. 脆弱知识点检测

#### `GET /v1/user/vulnerabilities/{user_hash}?threshold=0.7&limit=50`

**作用**：找出表面掌握度高但先修薄弱的"虚高"节点，防止学生基础不稳导致后续遗忘。

**Query 参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | 50 | 最多返回条数 |
| `threshold` | float | 0.7 | 掌握度高于此值才检查其先修 |

**返回示例**：
```json
{
  "user_hash": "stu_20240001",
  "mastery_threshold_high": 0.7,
  "total_vulnerabilities": 2,
  "vulnerabilities": [
    {
      "node_id": "math:微积分基本定理",
      "domain": "math",
      "mastery": 0.85,
      "fragility_score": 0.73,
      "weak_prerequisites": [
        {
          "node_id": "math:极限",
          "mastery": 0.44,
          "gap": 0.41
        }
      ]
    }
  ],
  "computed_at": "2026-08-28T08:30:00Z"
}
```

| 字段 | 说明 |
|------|------|
| `fragility_score` | 脆弱程度（0~1），越高越危险 |
| `weak_prerequisites` | 该节点的薄弱先修列表 |

---

## 四、Learning OS 接口（学习计划与目标管理）

> Learning OS 是一套围绕学生目标驱动的学习闭环系统：设定目标 → 提交证据 → 获取行动建议 → 验证完成。所有操作存储于服务器 SQLite，持久化保存。
>
> **注意**：Learning OS 使用 `user_id` 字段（而非 `user_hash`），业务方可保持一致传同一个值。

---

### 9. 学习行动类型目录

#### `GET /v1/user/learning/content`

**作用**：获取系统支持的学习行动类型和原因枚举，用于前端渲染和解释引擎给出的行动建议。

**请求**：无参数

**返回示例**：
```json
{
  "version": "learning-content-v1",
  "actions": {
    "baseline_assessment": {
      "label": "基线评估",
      "description": "先获取足够证据，才能形成可靠学习判断。"
    },
    "review_prerequisite": {
      "label": "复习先修知识",
      "description": "先打好基础，再学习后续知识。"
    },
    "verify_mastery": {
      "label": "验证掌握情况",
      "description": "再次验证确认当前判断是否可靠。"
    }
  },
  "reasons": {
    "insufficient_evidence": {
      "title": "证据不足",
      "description": "系统尚未获取足够的学习证据，暂不能给出推荐。"
    },
    "constraint_violation": {
      "title": "知识约束结构不一致",
      "description": "当前状态与知识先修关系不一致，建议先复习基础。"
    },
    "verification_needed": {
      "title": "需要一次验证",
      "description": "当前状态需要验证确认，再决定是否能继续。"
    },
    "state_updated": {
      "title": "状态已更新",
      "description": "新的学习证据已写入知识状态，下一步需要验证。"
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `actions` | 系统支持的学习行动类型，key 为 action_type |
| `reasons` | 引擎给出行动建议的原因枚举 |

---

### 10. Learning OS 持久化状态

#### `GET /v1/user/learning/status`

**作用**：确认 Learning OS 存储是否正常，用于系统自检。

**返回示例**：
```json
{
  "store": "SqliteLearningOSStore",
  "persistent": true,
  "content_version": "learning-content-v1"
}
```

| 字段 | 说明 |
|------|------|
| `persistent` | `true` = 数据持久化存储（SQLite），重启不丢失 |
| `content_version` | 当前学习内容目录版本 |

---

### 11. 创建学习目标

#### `POST /v1/user/learning/goals`

**作用**：为学生创建一个学习目标，作为后续学习行动和证据提交的锚点。

**请求体**：
```json
{
  "user_id": "stu_20240001",
  "domain_id": "math",
  "title": "掌握微积分基础",
  "desired_outcome": "能独立完成导数和积分的基础题型",
  "target_date": "2026-09-30",
  "priority": 1
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | 学生ID（1-128字符） |
| `domain_id` | string | ✅ | 学科ID（1-128字符），如 `"math"` |
| `title` | string | ✅ | 目标标题（1-200字符） |
| `desired_outcome` | string | ✅ | 期望达成的结果描述（1-500字符） |
| `target_date` | string\|null | 否 | 目标日期，格式 `"YYYY-MM-DD"`，null=不设截止 |
| `priority` | int | 否 | 优先级 1-5，1最高，默认3 |

**返回示例**：
```json
{
  "goal": {
    "id": "goal_abc123",
    "user_id": "stu_20240001",
    "domain_id": "math",
    "title": "掌握微积分基础",
    "desired_outcome": "能独立完成导数和积分的基础题型",
    "target_date": "2026-09-30",
    "priority": 1,
    "status": "active",
    "created_at": "2026-08-28T08:00:00Z"
  }
}
```

返回的 `goal.id` 后续提交证据时需要用到。

---

### 12. 查询学生学习目标列表

#### `GET /v1/user/learning/goals/{user_id}`

**作用**：获取该学生所有活跃的学习目标。

**路径参数**：`user_id` = 学生ID

**返回示例**：
```json
{
  "user_id": "stu_20240001",
  "goals": [
    {
      "id": "goal_abc123",
      "user_id": "stu_20240001",
      "domain_id": "math",
      "title": "掌握微积分基础",
      "desired_outcome": "能独立完成导数和积分的基础题型",
      "target_date": "2026-09-30",
      "priority": 1,
      "status": "active",
      "created_at": "2026-08-28T08:00:00Z"
    }
  ]
}
```

---

### 13. 提交学习证据

#### `POST /v1/user/learning/evidence`

**作用**：将一次学习行为（答题、练习等）作为证据提交给 Learning OS，引擎自动更新该学生的认知状态，并返回下一步建议的学习行动。

**与 `/v1/user/predict` 的区别**：`predict` 是推理接口（获取掌握度），`evidence` 是学习闭环接口（推进学习计划）。两者可以联合使用，也可以单独使用。

**请求体**：
```json
{
  "user_id": "stu_20240001",
  "goal_id": "goal_abc123",
  "node_id": "math:导数定义",
  "kind": "assessment",
  "outcome": "correct",
  "source": "exam_platform",
  "session_id": "session_xyz",
  "idempotency_key": "exam_001_q5",
  "payload": {}
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | 学生ID |
| `node_id` | string | ✅ | 知识点节点ID（1-256字符） |
| `outcome` | string | ✅ | `"correct"` 或 `"incorrect"` |
| `goal_id` | string\|null | 否 | 关联的学习目标ID，null=不关联目标 |
| `kind` | string | 否 | 证据类型，默认 `"assessment"`，可自定义（如 `"practice"`, `"quiz"`） |
| `source` | string | 否 | 证据来源，默认 `"internal_api"`，建议填业务平台名称 |
| `session_id` | string | 否 | 会话ID，用于日志关联 |
| `idempotency_key` | string\|null | 否 | 幂等键，防止同一条记录被重复提交，建议填题目唯一ID |
| `payload` | object | 否 | 附加信息，业务方自定义，引擎透传不处理 |

**返回示例**：
```json
{
  "created": true,
  "evidence": {
    "id": "ev_def456",
    "user_id": "stu_20240001",
    "node_id": "math:导数定义",
    "kind": "assessment",
    "outcome": "correct",
    "source": "exam_platform",
    "created_at": "2026-08-28T08:10:00Z"
  },
  "state": {
    "mastery": 0.845,
    "confidence": 0.91
  },
  "next_action": {
    "action_id": "act_789",
    "action_type": "verify_mastery",
    "node_id": "math:链式法则",
    "reason": "state_updated",
    "label": "验证掌握情况",
    "description": "新的学习证据已写入，建议验证当前掌握是否稳固。"
  }
}
```

| 字段 | 说明 |
|------|------|
| `created` | `true`=新记录创建；`false`=幂等键命中，未重复写入 |
| `state.mastery` | 提交后该节点的最新掌握度 |
| `next_action` | 引擎建议的下一步学习行动 |
| `next_action.action_type` | 行动类型（见接口9的类型枚举） |
| `next_action.node_id` | 建议学习的目标节点 |
| `next_action.reason` | 给出该建议的原因（见接口9的原因枚举） |

---

### 14. 获取今日学习行动建议

#### `GET /v1/user/learning/today?user_id=stu_20240001&goal_id=goal_abc123`

**作用**：根据学生当前认知状态和学习目标，由引擎计算出当前最优的一个学习行动建议（该做什么、该学哪个节点）。

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | 学生ID |
| `goal_id` | string | 否 | 指定目标ID，null=按所有目标综合给出建议 |

**返回示例**：
```json
{
  "action": {
    "action_id": "act_789",
    "action_type": "review_prerequisite",
    "node_id": "math:极限",
    "reason": "constraint_violation",
    "label": "复习先修知识",
    "description": "当前知识状态与先修约束不一致，建议先复习极限基础。"
  }
}
```

| 字段 | 说明 |
|------|------|
| `action_type` | 行动类型：`baseline_assessment` / `review_prerequisite` / `verify_mastery` |
| `node_id` | 引擎建议学习的具体节点 |
| `reason` | 给出该建议的原因（见接口9） |
| `action_id` | 行动ID，后续调用接口15验证时使用 |

---

### 15. 验证学习行动

#### `POST /v1/user/learning/actions/{action_id}/verify`

**作用**：学生完成了引擎建议的行动（如完成了复习），将结果提交验证，引擎据此更新认知状态并给出下一步行动。这是学习闭环的推进步骤。

**路径参数**：`action_id` = 接口14或13返回的 `action_id`

**请求体**：
```json
{
  "user_id": "stu_20240001",
  "outcome": "correct",
  "notes": "完成了3道极限练习题，均答对",
  "session_id": "session_xyz"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | 学生ID |
| `outcome` | string | ✅ | `"correct"` 或 `"incorrect"` |
| `notes` | string | 否 | 验证备注（最多2000字符） |
| `session_id` | string | 否 | 会话ID |

**返回示例**：
```json
{
  "verification": {
    "id": "ver_123",
    "action_id": "act_789",
    "user_id": "stu_20240001",
    "outcome": "correct",
    "notes": "完成了3道极限练习题，均答对",
    "created_at": "2026-08-28T08:20:00Z"
  },
  "evidence": {
    "id": "ev_ghi789",
    "node_id": "math:极限",
    "outcome": "correct"
  },
  "state": {
    "mastery": 0.78,
    "confidence": 0.85
  },
  "next_action": {
    "action_id": "act_890",
    "action_type": "verify_mastery",
    "node_id": "math:导数定义",
    "reason": "state_updated",
    "label": "验证掌握情况",
    "description": "极限基础更新后，请验证导数定义的掌握是否稳固。"
  }
}
```

---

### 16. 读取学习轨迹

#### `GET /v1/user/learning/trajectory/{user_id}`

**作用**：获取该学生完整的学习行动历史（目标 → 证据 → 行动 → 验证的时间线），适合教师端查看学生学习过程。

**路径参数**：`user_id` = 学生ID

**返回示例**：
```json
{
  "user_id": "stu_20240001",
  "goals": [
    {
      "id": "goal_abc123",
      "title": "掌握微积分基础",
      "status": "active"
    }
  ],
  "evidence": [
    {
      "id": "ev_def456",
      "node_id": "math:导数定义",
      "outcome": "correct",
      "created_at": "2026-08-28T08:10:00Z"
    }
  ],
  "actions": [
    {
      "id": "act_789",
      "action_type": "review_prerequisite",
      "node_id": "math:极限",
      "created_at": "2026-08-28T08:05:00Z"
    }
  ],
  "verifications": [
    {
      "id": "ver_123",
      "action_id": "act_789",
      "outcome": "correct",
      "created_at": "2026-08-28T08:20:00Z"
    }
  ]
}
```

---

## 五、错误码汇总

| 状态码 | 场景 | 返回体示例 |
|--------|------|-----------|
| 400 | 请求体格式错误/字段缺失/字段超长 | `{"detail": "field required"}` |
| 404 | 节点不存在 / 用户无记录 / action_id 不存在 | `{"detail": "User not found"}` |
| 503 | 推理引擎或存储未就绪 | `{"detail": "Engine not ready"}` |
| 500 | 服务内部错误 | `{"detail": "Internal server error"}` |

---

## 六、典型对接流程

### 场景A：只做答题推理（最简单）
```
学生答题 → POST /v1/user/predict → 拿 node_mastery + lvr → 展示给学生/教师
```

### 场景B：答题推理 + 知识诊断
```
学生答题  → POST /v1/user/predict         → 实时掌握度
间歇查询  → GET  /v1/user/gaps/{id}        → 找卡脖子节点
         → GET  /v1/user/lvr_alert/{id}   → 先修断裂详情
         → GET  /v1/user/vulnerabilities/{id} → 虚高节点
```

### 场景C：完整学习闭环（Learning OS）
```
1. 创建目标  → POST /v1/user/learning/goals
2. 获取建议  → GET  /v1/user/learning/today?user_id=xxx
3. 提交证据  → POST /v1/user/learning/evidence（每次答题）
4. 验证完成  → POST /v1/user/learning/actions/{id}/verify
5. 查轨迹    → GET  /v1/user/learning/trajectory/{id}
```

---

## 七、快速接入示例

### Python
```python
import requests

BASE = "http://47.82.118.95:8001"

# 答题推理
resp = requests.post(f"{BASE}/v1/user/predict", json={
    "user_hash": "stu_20240001",
    "current_node": "math:导数定义",
    "user_action": "correct",
    "step_index": 1
})
data = resp.json()
print("LVR:", data["lvr"])
print("掌握度:", data["node_mastery"])

# 创建学习目标
resp = requests.post(f"{BASE}/v1/user/learning/goals", json={
    "user_id": "stu_20240001",
    "domain_id": "math",
    "title": "掌握微积分基础",
    "desired_outcome": "能独立完成导数和积分基础题",
    "priority": 1
})
goal_id = resp.json()["goal"]["id"]

# 获取今日学习建议
resp = requests.get(f"{BASE}/v1/user/learning/today",
                    params={"user_id": "stu_20240001", "goal_id": goal_id})
print("今日建议:", resp.json()["action"])
```

### curl
```bash
# 答题推理
curl -X POST http://47.82.118.95:8001/v1/user/predict \
  -H "Content-Type: application/json" \
  -d '{"user_hash":"stu_20240001","current_node":"math:导数定义","user_action":"correct","step_index":1}'

# 获取知识缺口
curl "http://47.82.118.95:8001/v1/user/gaps/stu_20240001?threshold=0.6&limit=10"

# 获取今日学习建议
curl "http://47.82.118.95:8001/v1/user/learning/today?user_id=stu_20240001"
```

---

## 八、注意事项

1. **节点ID必须准确**：`current_node` / `node_id` 必须是知识图谱中存在的节点，否则返回404。节点列表向产品方获取，图版本更新时同步一次。
2. **user_hash vs user_id**：推理接口（predict/profile/report/summary/lvr_alert/gaps/vulnerabilities）用 `user_hash`；Learning OS 接口用 `user_id`。业务方建议传同一个值。
3. **无状态调用**：引擎内部维护每个学生的历史状态，调用方只传当前这一步，不需要传历史。
4. **幂等键防重提交**：`/learning/evidence` 建议填 `idempotency_key`（题目唯一ID），防止网络重试导致重复记录。
5. **并发限制**：推理接口限速 60次/分钟（per IP），学习接口无限速，高并发场景提前联系服务方。
6. **LVR 判断阈值**：推荐以 `0.15` 为分界，超过触发补学引导。
