# 知拾 (Zhishi) 后端 API 接口功能清单

> **版本**：v3.2（TCN 全线对接完成）  
> **日期**：2026-07-18  
> **基线代码**：`zhishi-master/backend`（经 2026-07-18 全量审计）  
> **治理依据**：`zhixu-v4.md` v2.0（TCN 对接与重复接口治理方案，源码级确认）  
> **TCN 对接**：`SYSTEM_ARCHITECTURE_BRIEF.md` + `TCN_API_CONFIRMATION_REPLY.md` + `respond_fix.md`  
> **用途**：前端对接参考文档。所有 TCN 相关字段均经 TCN 方源码级核实。

---

## 目录

- [通用说明](#通用说明)
- [1. 账号认证 (Auth)](#1-账号认证-auth)
- [2. 用户套餐 (Plan)](#2-用户套餐-plan)
- [3. 智能聊天 (Chat)](#3-智能聊天-chat)
- [4. 知识库管理 (KB)](#4-知识库管理-kb)
- [5. 知识追踪 (KT)](#5-知识追踪-kt)
- [6. 题目管理 (Questions)](#6-题目管理-questions)
- [7. 刷题 (Quiz)](#7-刷题-quiz)
- [8. 辅导 (Tutor)](#8-辅导-tutor)
- [9. 首页建议 (Dashboard)](#9-首页建议-dashboard)
- [10. 学习分析 (Analytics)](#10-学习分析-analytics)
- [11. 学习报告 (Reports)](#11-学习报告-reports)
- [12. 针对训练 (Training)](#12-针对训练-training)
- [13. 个人画像 (Profile) — 待实现](#13-个人画像-profile--待实现)
- [14. 笔记系统 (Notes) — 待实现](#14-笔记系统-notes--待实现)
- [15. 提醒系统 (Reminders) — 待实现](#15-提醒系统-reminders--待实现)
- [16. 通知中心 (Notifications) — 待实现](#16-通知中心-notifications--待实现)
- [17. 统一搜索 (Search) — 待实现](#17-统一搜索-search--待实现)
- [18. 学习路径 (Learning Path) — 待实现](#18-学习路径-learning-path--待实现)
- [19. 数据同步 (Sync) — 待实现](#19-数据同步-sync--待实现)
- [20. 系统健康 (Health)](#20-系统健康-health)
- [附录 A：状态码规范](#附录-a状态码规范)
- [附录 B：TCN 外部接口参考](#附录-btcn-外部接口参考)

---

## 通用说明

### 鉴权方式

所有业务接口（除注册、登录、密码重置、健康检查外）需在请求头中携带 Bearer Token：

```
Authorization: Bearer <access_token>
```

### 基础路径

```
http://<host>:8765/api/v1
```

### TCN 引擎路径

```
http://<TCN_HOST>:8001
```

### 通用错误响应格式

```json
{
  "detail": "错误描述信息"
}
```

### 接口状态标记

| 标记 | 含义 |
|------|------|
| ✅ 已实现 | 代码已完成，可直接调用 |
| 🔄 已改造 | TCN 对接后数据源已切换（接口路径不变，响应结构前向兼容） |
| ❌ 已淘汰 | TCN 对接后删除（返回 404） |
| 📋 待实现 | 规划中，尚未开发 |
| ➕ v2.0 新增 | TCN 对接后新增接口 |

---

## 1. 账号认证 (Auth)

**路由前缀**：`/api/v1/auth`  
**权限**：部分接口免登录

### 1.1 接口列表

| 方法 | 路径 | 鉴权 | 状态 | 说明 |
|------|------|------|------|------|
| POST | `/auth/register` | 否 | ✅ | 用户注册（自动生成 user_hash） |
| POST | `/auth/token` | 否 | ✅ | 用户登录（OAuth2 password grant） |
| POST | `/auth/refresh-token` | 是 | ✅ | 刷新 Token |
| GET | `/auth/users/me` | 是 | ✅ | 获取当前用户信息（含套餐详情） |
| GET | `/auth/users/me/plan` | 是 | ✅ | 获取当前用户套餐详情 |
| GET | `/auth/users/me/quota` | 是 | ✅ | 检查 API 配额状态 |
| POST | `/auth/users/me/upgrade-plan` | 是 | ✅ | 升级套餐 |
| PATCH | `/auth/users/me` | 是 | ✅ | 更新个人资料（白名单字段） |
| POST | `/auth/send-verification` | 否 | ✅ | 发送验证码（邮箱或手机号） |
| POST | `/auth/verify-email` | 否 | ✅ | 验证邮箱 |
| POST | `/auth/forgot-password` | 否 | ✅ | 发送密码重置邮件 |
| POST | `/auth/reset-password` | 否 | ✅ | 使用重置 Token 修改密码 |
| POST | `/auth/change-password` | 是 | ✅ | 已登录用户修改密码 |
| POST | `/auth/logout` | 是 | ✅ | 退出登录 |
| DELETE | `/auth/account` | 是 | ✅ | 注销账号 |
| GET | `/auth/check-email-verification/{email}` | 否 | ✅ | 检查邮箱验证状态 |
| GET | `/auth/test-token-info` | 是 | ✅ | 测试 Token 有效性 |

### 1.2 关键接口详情

#### 注册

```
POST /api/v1/auth/register
```

**请求体**：
```json
{
  "email": "user@example.com",
  "password": "secure_password",
  "username": "可选用户名",
  "nickname": "可选昵称",
  "verification_code": "可选验证码"
}
```

**响应**（201）：
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": null,
  "nickname": "新用户",
  "is_active": true,
  "created_at": "2026-07-18T00:00:00Z",
  "access_token": "eyJ...",
  "token_type": "bearer",
  "message": "注册成功"
}
```

#### 登录

```
POST /api/v1/auth/token
Content-Type: application/x-www-form-urlencoded
```

**请求体**：
```
username=user@example.com（或手机号）
password=secure_password
```

**响应**：
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 604800
}
```

---

## 2. 用户套餐 (Plan)

**路由前缀**：`/api/v1/plan`

| 方法 | 路径 | 鉴权 | 状态 | 说明 |
|------|------|------|------|------|
| GET | `/plan/` | 否 | ✅ | 获取所有可用套餐列表 |
| GET | `/plan/my-plan` | 是 | ✅ | 获取当前用户套餐及升级选项 |

---

## 3. 智能聊天 (Chat)

**路由前缀**：`/api/v1/chat`  
**鉴权**：是  
**存储**：Redis 缓存 + 文件持久化（storage/）

### 3.1 接口列表

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/chat` | ✅ | 发送消息（stream=true 时 SSE 流式） |
| GET | `/chat/sessions` | ✅ | 列出当前用户所有会话 |
| GET | `/chat/history?session_id=xxx` | ✅ | 获取指定会话聊天历史 |
| DELETE | `/chat/sessions/{session_id}` | ✅ | 删除指定会话 |

### 3.2 发送消息

```
POST /api/v1/chat
Authorization: Bearer <token>
```

**请求体**：
```json
{
  "content": "请解释微积分的基本原理",
  "session_id": "a1b2c3d4e5f6（可选，不传则自动创建新会话）",
  "stream": true,
  "collection_id": "可选知识库分区ID，限定检索范围",
  "tc_node_id": "math:quadratic_equation（可选，TCN 答题节点ID）",
  "tc_user_action": "correct（可选，\"correct\"|\"incorrect\"）",
  "tc_domain_id": "math（可选，领域ID）"
}
```

> `tc_node_id` / `tc_user_action` / `tc_domain_id` 为 TCN 集成新增字段，全部可选。传入后对话完成会自动更新用户知识状态。

**非流式响应**（200）：
```json
{
  "session_id": "a1b2c3d4e5f6",
  "session_title": "请解释微积分的基本原理",
  "role": "assistant",
  "content": "微积分是研究函数变化率和累积量的数学分支...",
  "created_at": "2026-07-18T10:00:00Z",
  "citations": [
    {
      "document_id": "doc_001",
      "document_name": "高等数学.pdf",
      "segment_index": 3,
      "content_snippet": "微积分的基本思想是...",
      "similarity": 0.92
    }
  ]
}
```

**SSE 流式事件格式**（stream=true）：

```
event: message
data: {"session_id":"a1b2","role":"assistant","content":"微"}

event: message
data: {"session_id":"a1b2","role":"assistant","content":"积分","reasoning_content":"先考虑函数的极限..."}

event: message
data: {"session_id":"a1b2","role":"assistant","content":"是...","citations":[...]}

event: message
data: {"session_id":"a1b2","role":"system","content":"","lvr":0.12,"diagnosis":"No logical violation detected."}
```

> 最后一条 `role:"system"` 事件在 TCN 集成后新增，仅在传入 `tc_node_id` + `tc_user_action` 时返回。

**SSE 数据字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 会话 ID |
| `role` | string | 消息角色（assistant / tool / system） |
| `content` | string | 回复文本片段 |
| `reasoning_content` | string? | 推理过程片段（推理类 LLM 输出） |
| `tool_name` | string? | 工具调用名称 |
| `citations` | array? | 引用信息 |
| `lvr` | float? | TCN 全局 LVR（知识状态一致性指标，0–1）— system 事件 |
| `diagnosis` | string? | TCN 诊断描述 — system 事件 |

---

## 4. 知识库管理 (KB)

**路由前缀**：`/api/v1/kb`  
**鉴权**：是

### 4.1 知识库分区 (Collections)

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| GET | `/kb/collections` | ✅ | 列出所有分区 |
| POST | `/kb/collections` | ✅ | 创建分区 |
| PATCH | `/kb/collections/{collection_id}` | ✅ | 更新分区名称/描述 |
| DELETE | `/kb/collections/{collection_id}` | ✅ | 删除分区 |
| GET | `/kb/categories` | ✅ | 分区别名（兼容前端路径） |
| POST | `/kb/categories` | ✅ | 创建分区（别名） |
| PATCH | `/kb/categories/{collection_id}` | ✅ | 更新分区（别名） |
| DELETE | `/kb/categories/{collection_id}` | ✅ | 删除分区（别名） |

**创建分区请求**：
```json
{
  "name": "数学笔记",
  "zone": "study",
  "description": "高等数学相关资料"
}
```

> `zone` 枚举：`"study"`（学习区） / `"life"`（生活区）

### 4.2 文档管理

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/kb/upload` | ✅ | 上传文档（multipart/form-data） |
| GET | `/kb/documents` | ✅ | 文档列表（分页，可按 collection_id 过滤） |
| GET | `/kb/documents/{batch_id}/status` | ✅ | 查询索引进度 |
| GET | `/kb/documents/{doc_id}/content` | ✅ | 获取解析后文本内容 |
| GET | `/kb/documents/{doc_id}/file` | ✅ | 下载/预览原始文件 |
| GET | `/kb/documents/{doc_id}/segments` | ✅ | 列出文档分段 |
| GET | `/kb/documents/{doc_id}/pages` | ✅ | 按页码平铺文档 |
| GET | `/kb/documents/{doc_id}/pages/{page_number}` | ✅ | 单页详情 |
| DELETE | `/kb/documents/{doc_id}` | ✅ | 删除文档 |

**上传文档**（multipart/form-data）：
- `file`：文件（支持 txt / md / csv / json / html / pdf / docx / png / jpg / gif / webp）
- `collection_id`：可选分区 ID

### 4.3 配置查询

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| GET | `/kb/config` | ✅ | 查询 RAG 后端类型、上传限制、支持格式 |

---

## 5. 知识追踪 (KT)

**路由前缀**：`/api/v1/kt`  
**鉴权**：是  
**数据源**：TCN 引擎层（port 8001），`zhixu-v4.md` v2.0 治理

### 5.1 KT 接口总览

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/kt/correct` | ❌ 已淘汰 | 由 TCN predict 替代，Chat 对话自动调用 |
| POST | `/kt/evaluate` | ❌ 已淘汰 | 由 TCN predict 响应内嵌 lvr+diagnosis 替代 |
| POST | `/kt/learning-path` | 🔄 已改造 | 基于 TCN report + 图谱缓存推荐学习路径 |
| POST | `/kt/prerequisites` | 🔄 已改造 | 查询节点先修/后继关系 |
| GET | `/kt/skill-graph` | 🔄 已改造 | 全量技能图谱叠加用户掌握度 |
| GET | `/kt/states` | ➕ 已实现 | 用户已练习节点掌握度快照 |
| GET | `/kt/summary` | ➕ 已实现 | 用户知识状态摘要（注入 LLM Prompt 用） |
| GET | `/kt/gaps` | ➕ 已实现 | 先修断层查询 |
| GET | `/kt/vulnerabilities` | ➕ 已实现 | 认知脆弱点（伪掌握）预警 |
| GET | `/kt/lvr-alert` | ➕ 已实现 | LVR 预警状态（含回溯建议） |

---

### 5.2 学习路径推荐

```
POST /api/v1/kt/learning-path
Authorization: Bearer <token>
```

**请求体**：
```json
{
  "states": {},
  "top_k": 5
}
```

> `states` 字段保留兼容但后端已自动从 TCN report 获取实际掌握度数据。

**响应**：
```json
{
  "recommendations": [
    {
      "skill_id": "math:linear_equation",
      "skill_name": "一元一次方程",
      "current_mastery": 0.42,
      "importance": 3,
      "priority_score": 3.58
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `skill_id` | string | 节点标识，格式 `"domain:node_id"`（如 `"math:linear_equation"`） |
| `skill_name` | string | 节点中文名称 |
| `current_mastery` | float | 当前掌握度 0–1 |
| `importance` | int | 重要性（被多少后继节点依赖） |
| `priority_score` | float | 优先得分 |

---

### 5.3 先修关系查询

```
POST /api/v1/kt/prerequisites
Authorization: Bearer <token>
```

**请求体**：
```json
{
  "skill_id": "math:linear_equation"
}
```

**响应**：
```json
{
  "skill": {"id": "math:linear_equation", "name": "一元一次方程"},
  "prerequisites": [
    {"id": "math:addition", "name": "加法", "mastery": 0.95},
    {"id": "math:subtraction", "name": "减法", "mastery": 0.87}
  ],
  "dependents": [
    {"id": "math:quadratic_equation", "name": "一元二次方程", "mastery": 0.85}
  ]
}
```

---

### 5.4 技能图谱

```
GET /api/v1/kt/skill-graph
Authorization: Bearer <token>
```

**响应**：
```json
{
  "skills": [
    {"id": "math:addition", "name": "加法", "mastery": 0.95, "confidence": 0.0},
    {"id": "math:linear_equation", "name": "一元一次方程", "mastery": 0.42, "confidence": 0.72},
    {"id": "math:calculus_intro", "name": "微积分入门"}
  ],
  "edges": [
    {"source": "math:addition", "target": "math:linear_equation"}
  ],
  "total_skills": 503,
  "total_edges": 1200
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `skills[].id` | string | 节点标识，格式 `"domain:node_id"` |
| `skills[].name` | string | 节点中文名称 |
| `skills[].mastery` | float? | 用户掌握度 0–1（仅练习过的节点有此字段） |
| `skills[].confidence` | float? | 可信度（rule 模式始终 0.0） |

---

### 5.5 认知状态查询

```
GET /api/v1/kt/states
Authorization: Bearer <token>
```

**响应**：
```json
{
  "math:addition": 0.95,
  "math:linear_equation": 0.42,
  "math:quadratic_equation": 0.85
}
```

> 仅包含用户**实际练习过**的节点（稀疏存储）。

---

### 5.6 用户知识状态摘要（新增）

```
GET /api/v1/kt/summary
Authorization: Bearer <token>
```

> **用途**：每次 Chat 对话前拉取，注入 LLM System Prompt。三种对话模式（普通/知识追踪/推理）均依赖此接口。

**响应**：
```json
{
  "user_hash": "a3f9c1d2e8b7...",
  "diagnosis_version": "rule",
  "total_steps": 16,
  "overall_mastery": 0.5367,
  "global_lvr": 0.0147,
  "lvr_level": "normal",
  "graph_version": 3,
  "domain_summary": [
    {"domain": "math", "mastery_avg": 0.55, "node_count": 83, "visited_count": 0},
    {"domain": "higher_math", "mastery_avg": 0.56, "node_count": 233, "visited_count": 0},
    {"domain": "discrete_math", "mastery_avg": 0.525, "node_count": 100, "visited_count": 0},
    {"domain": "physics", "mastery_avg": 0.5, "node_count": 87, "visited_count": 0}
  ],
  "last_active_node": "discrete_math:命题与联结词",
  "computed_at": "2026-07-17T12:03:16Z"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `overall_mastery` | float | 整体掌握度均值 0–1 |
| `global_lvr` | float | 全局 LVR |
| `lvr_level` | string | `"normal"` / `"warning"` / `"critical"` |
| `domain_summary` | array | 按领域分组统计 |
| `domain_summary[].mastery_avg` | float | 该领域平均掌握度 |
| `domain_summary[].node_count` | int | 该领域总节点数 |
| `last_active_node` | string | 最近活跃节点 |

---

### 5.7 先修断层查询（新增）

```
GET /api/v1/kt/gaps?limit=10&threshold=0.6
Authorization: Bearer <token>
```

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `limit` | int | 50 | 返回条数 |
| `threshold` | float | 0.6 | 掌握度阈值 |

**响应**：
```json
{
  "user_hash": "a3f9c1d2e8b7...",
  "diagnosis_version": "rule",
  "mastery_threshold": 0.6,
  "total_gaps": 495,
  "returned_gaps": 10,
  "limit": 10,
  "gaps": [
    {
      "node_id": "math:函数的概念与性质",
      "domain": "math",
      "mastery": 0.5,
      "children_count": 12,
      "is_visited": false
    }
  ],
  "computed_at": "2026-07-17T12:03:16Z"
}
```

> `gaps` 按 `children_count`（后继节点数）降序排列，`children_count` 越大表示该断层影响面越大。

---

### 5.8 认知脆弱点预警（新增）

```
GET /api/v1/kt/vulnerabilities?limit=10
Authorization: Bearer <token>
```

> **触发条件**：节点掌握度 ≥ 0.7 但先修节点掌握度低（CASM 风险）。

**响应**：
```json
{
  "user_hash": "a3f9c1d2e8b7...",
  "diagnosis_version": "rule",
  "mastery_threshold_high": 0.7,
  "total_vulnerabilities": 1,
  "returned_vulnerabilities": 1,
  "limit": 10,
  "vulnerabilities": [
    {
      "node_id": "discrete_math:命题与联结词",
      "domain": "discrete_math",
      "mastery": 1.0,
      "fragility_score": 0.5333,
      "weak_prerequisites": [
        {"node_id": "math:命题与逻辑", "mastery": 0.3, "gap": 0.65},
        {"node_id": "math:逻辑联结词", "mastery": 0.5, "gap": 0.45},
        {"node_id": "math:充分必要条件", "mastery": 0.45, "gap": 0.5}
      ]
    }
  ],
  "computed_at": "2026-07-17T12:03:44Z"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `fragility_score` | float | 脆弱分数（越高伪掌握风险越大） |
| `weak_prerequisites[].gap` | float | 先修掌握度差值 |

---

### 5.9 LVR 预警状态（新增）

```
GET /api/v1/kt/lvr-alert?limit=10
Authorization: Bearer <token>
```

**响应**：
```json
{
  "user_hash": "a3f9c1d2e8b7...",
  "diagnosis_version": "rule",
  "global_lvr": 0.0147,
  "lvr_level": "normal",
  "alert_code": "LVR_NORMAL",
  "alert_text": null,
  "total_violations": 18,
  "returned_violations": 10,
  "limit": 10,
  "violations": [
    {
      "parent_node": "higher_math:映射与函数",
      "child_node": "higher_math:函数的基本性质",
      "parent_mastery": 0.45,
      "child_mastery": 0.6,
      "gap": 0.1
    }
  ],
  "backtrack_recommended": [
    "discrete_math:合取范式与析取范式",
    "higher_math:映射与函数",
    "math:命题与逻辑"
  ],
  "computed_at": "2026-07-17T12:03:16Z"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `alert_code` | string | `LVR_NORMAL`（绿）/ `LVR_WARNING`（黄，lvr≥0.15）/ `LVR_CRITICAL`（红，lvr≥0.35） |
| `lvr_level` | string | 同 `alert_code` 的语义别名 |
| `violations[].parent_node` | string | 先修节点 |
| `violations[].child_node` | string | 后继节点 |
| `violations[].gap` | float | 违反程度 |
| `backtrack_recommended` | string[] | 可直接注入 LLM 的回溯建议 |

---

## 6. 题目管理 (Questions)

**路由前缀**：`/api/v1/questions`  
**鉴权**：是

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/questions/generate` | ✅ | 对文档/分段批量 AI 出题 |
| POST | `/questions/generate-from-pages` | ✅ | 对选中页批量 AI 出题 |
| POST | `/questions/extract-from-pages` | ✅ | 从选中页提取教材自带题目 |
| GET | `/questions` | ✅ | 列出用户可见题目（可按 document_id / collection_id 过滤） |
| GET | `/questions/{question_id}` | ✅ | 单题详情（含溯源 provenance） |
| DELETE | `/questions?document_id=xxx` | ✅ | 删除指定文档的题库引用 |
| DELETE | `/questions/bulk` | ✅ | 批量删除题库引用 |

---

## 7. 刷题 (Quiz)

**路由前缀**：`/api/v1/quiz`  
**鉴权**：是

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/quiz/sessions` | ✅ | 创建刷题会话 |
| GET | `/quiz/sessions/{session_id}` | ✅ | 获取会话进度（不含标准答案） |
| POST | `/quiz/sessions/{session_id}/answers` | ✅ | 提交单题答案 |
| GET | `/quiz/sessions/{session_id}/results` | ✅ | 汇总错题与 unknown 题目 |

**创建会话请求**：
```json
{
  "document_id": "doc_xxx",
  "collection_id": "col_xxx",
  "question_ids": ["q_001", "q_002"],
  "question_count": 10
}
```

**提交答案请求**：
```json
{
  "question_id": "q_001",
  "user_answer": "B. 42",
  "status": "answered",
  "time_spent_seconds": 45
}
```

> `status`：`"answered"` / `"unknown"`（表示"我不会"）

---

## 8. 辅导 (Tutor)

**路由前缀**：`/api/v1/tutor`  
**鉴权**：是

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/tutor/sessions` | ✅ | 从题目创建苏格拉底式辅导会话 |
| GET | `/tutor/sessions/{session_id}` | ✅ | 获取辅导会话详情与对话历史 |
| POST | `/tutor/sessions/{session_id}/messages` | ✅ | 发送消息（支持 SSE 流式） |

---

## 9. 首页建议 (Dashboard)

**路由前缀**：`/api/v1/dashboard`  
**鉴权**：是

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| GET | `/dashboard/suggestions` | ✅ | 基于知识库文档 LLM 生成 2-3 条个性化建议 |

---

## 10. 学习分析 (Analytics)

**路由前缀**：`/api/v1/analytics`  
**鉴权**：是

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| GET | `/analytics/stats` | ✅ | 汇总文档、题库与刷题进度 |
| GET | `/analytics/tag-stats` | ✅ | 按 tag 与题型聚合错题统计 |
| POST | `/analytics/learning-report` | ✅ | 生成 LLM 学习报告并保存到笔记 |

---

## 11. 学习报告 (Reports)

**路由前缀**：`/api/v1/reports`  
**鉴权**：是

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/reports/generate` | ✅ | 生成 LLM 学习报告 |
| GET | `/reports` | ✅ | 列出历史学习报告 |
| GET | `/reports/latest` | ✅ | 获取最新一份学习报告 |
| GET | `/reports/{report_id}` | ✅ | 获取指定学习报告 |

---

## 12. 针对训练 (Training)

**路由前缀**：`/api/v1/training`  
**鉴权**：是

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/training/targeted/start` | ✅ | Agent 制定训练计划 |
| GET | `/training/targeted/reports/{report_id}/active-session` | ✅ | 查询未完成训练会话 |
| GET | `/training/targeted/sessions/{session_id}` | ✅ | 恢复训练会话 |
| POST | `/training/targeted/tutor/{agent_session_id}` | ✅ | 训练页 AI 辅导（SSE 流式） |

---

## 13. 个人画像 (Profile)

**路由前缀**：`/api/v1/profile`  
**鉴权**：是  
**状态**：📋 待实现

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| GET | `/profile` | 📋 | 查询当前个人画像 |
| POST | `/profile/build` | 📋 | 创建画像构建任务 |
| GET | `/profile/tasks/{task_id}` | 📋 | 查询构建任务状态 |
| POST | `/profile/tasks/{task_id}/confirm` | 📋 | 提交确认回答 |
| GET | `/profile/graph` | 📋 | 获取画像图谱 |
| POST | `/profile/nodes/{node_id}/feedback` | 📋 | 提交画像节点反馈 |

---

## 14. 笔记系统 (Notes)

**路由前缀**：`/api/v1/notes`  
**鉴权**：是  
**状态**：📋 待实现（`UserNote` 模型已有）

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/notes` | 📋 | 创建笔记 |
| GET | `/notes` | 📋 | 列出笔记（分页） |
| GET | `/notes/{note_id}` | 📋 | 获取笔记详情 |
| PATCH | `/notes/{note_id}` | 📋 | 更新笔记 |
| DELETE | `/notes/{note_id}` | 📋 | 删除笔记 |
| GET | `/notes/search?q=xxx` | 📋 | 全文搜索笔记 |
| POST | `/notes/from-chat` | 📋 | 从 AI 回答生成笔记 |

---

## 15. 提醒系统 (Reminders)

**路由前缀**：`/api/v1/reminders`  
**鉴权**：是  
**状态**：📋 待实现

---

## 16. 通知中心 (Notifications)

**路由前缀**：`/api/v1/notifications`  
**鉴权**：是  
**状态**：📋 待实现

---

## 17. 统一搜索 (Search)

**路由前缀**：`/api/v1/search`  
**鉴权**：是  
**状态**：📋 待实现

---

## 18. 学习路径 (Learning Path)

**路由前缀**：`/api/v1/learning-path`  
**鉴权**：是  
**状态**：📋 待实现

---

## 19. 数据同步 (Sync)

**路由前缀**：`/api/v1/sync`  
**鉴权**：是  
**状态**：📋 待实现

---

## 20. 系统健康 (Health)

| 方法 | 路径 | 鉴权 | 状态 | 说明 |
|------|------|------|------|------|
| GET | `/health` | 否 | ✅ | 应用健康检查 |

**响应**：
```json
{
  "status": "ok",
  "skills_count": 503,
  "model_loaded": true
}
```

> `status`：`"ok"`（TCN 可达）/ `"degraded"`（TCN 不可达，KT 降级但 Chat 等主流程不受影响）

---

## 附录 A：状态码规范

| 状态码 | 含义 | 使用场景 |
|--------|------|---------|
| 200 | 成功 | GET / PATCH 请求成功 |
| 201 | 已创建 | POST 创建资源成功 |
| 400 | 请求错误 | 参数校验失败、业务规则不满足 |
| 401 | 未授权 | Token 缺失 / 无效 / 过期 |
| 404 | 未找到 | 资源不存在或接口已淘汰 |
| 409 | 冲突 | 重复创建资源 |
| 413 | 请求体过大 | 文件超过大小限制 |
| 422 | 不可处理的实体 | Pydantic 校验失败 |
| 429 | 请求过多 | API 配额耗尽 |
| 500 | 服务器错误 | 内部异常 |
| 503 | 服务不可用 | TCN / LLM 等依赖不可达 |

---

## 附录 B：TCN 外部接口参考

> TCN 引擎层（port 8001）为独立服务，我方后端通过 HTTP 调用。以下为真实接口格式（`respond_fix.md` v1.0，2026-07-17）。  
> **OpenAPI 文档**：`http://<TCN_HOST>:8001/docs`  
> **当前 TCN 地址**：`http://47.82.118.95:8001`

### B.1 已提供接口

| 方法 | 端点 | 鉴权 | 我方调用位置 | 说明 |
|------|------|------|------------|------|
| POST | `/v1/user/predict` | 否 | Chat/Tutor 答题后 | 更新知识状态 |
| GET | `/v1/user/profile/{user_hash}` | 否 | 认知画像查询 | 摘要信息 |
| GET | `/v1/user/report/{user_hash}` | 否 | KT 改造接口数据源 | 完整掌握报告 |
| GET | `/v1/user/summary/{user_hash}` | 否 | Chat 前注入 Prompt | 知识状态摘要 |
| GET | `/v1/user/gaps/{user_hash}` | 否 | 断层诊断 | 先修断层 |
| GET | `/v1/user/vulnerabilities/{user_hash}` | 否 | 伪掌握预警 | 认知脆弱点 |
| GET | `/v1/user/lvr_alert/{user_hash}` | 否 | LVR 预警 | 预警状态+回溯建议 |
| GET | `/health` | 否 | 启动时健康探测 | 引擎状态 |
| GET | `/admin/graph/domains` | X-Admin-Token | 启动时拉取图谱 | 域名列表 |
| GET | `/admin/graph/data/{domain}` | X-Admin-Token | 启动时拉取图谱 | 单域全量节点+边 |

### B.2 predict 请求格式（完整 7 字段）

```json
{
  "api_key": "",
  "user_hash": "a3f9c1d2e8b7...",
  "domain_id": "math",
  "current_node": "math:quadratic_equation",
  "user_action": "correct",
  "step_index": 12,
  "session_id": "sess_20260718_001"
}
```

### B.3 predict 响应格式（8 字段）

```json
{
  "user_hash": "a3f9c1d2e8b7...",
  "lvr": 0.0044,
  "vs": 0.00022,
  "diagnosis": "No logical violation detected.",
  "recommended_backtrack": null,
  "node_mastery": {
    "discrete_math:命题与联结词": 0.6,
    "discrete_math:命题公式与真值表": 0.5
  },
  "epsilon_used": 0.05,
  "training_phase": "unknown"
}
```

> ⚠️ `node_mastery` 是图谱前 10 个节点（索引 0–9），不保证包含 `current_node`。

### B.4 report 响应格式

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
    }
  }
}
```

> ⚠️ 顶层是 **object**。`nodes` 是 dict（key=`"domain:node_id"`），稀疏存储。`parents` 是 dict（`{parent_id: mastery_float}`）。

---

## 更新记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-07-18 | v3.2 | 全线 TCN 对接完成：ChatRequest 新增 TCN 字段 + SSE 新增 lvr/diagnosis；KT 新增 4 个接口完整文档（summary/gaps/vulnerabilities/lvr-alert）+ 真实格式替换；附录 B 全面更新为 respond_fix.md 真实格式 |
| 2026-07-15 | v3.1 | TCN 源码确认初版 |
| 2026-07-15 | v3.0 | 初始版本：淘汰 2 个接口 + 改造 3 个 + 新增 states |