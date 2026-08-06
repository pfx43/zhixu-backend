# 知拾 (Zhishi) 后端 API 文档

> **Base URL**: `http://localhost:8765`
>
> **Content-Type**: `application/json`（文件上传使用 `multipart/form-data`）
>
> **鉴权方式**: Bearer Token（`Authorization: Bearer <token>`），通过 `/api/v1/auth/token` 登录获取

---

## 目录

- [1. 账号认证 (Auth)](#1-账号认证-auth---apiv1auth)
- [2. 用户套餐 (Plan)](#2-用户套餐-plan---apiv1plan)
- [3. 新用户引导 (Onboarding)](#3-新用户引导-onboarding---apiv1onboarding)
- [4. 智能聊天 (Chat)](#4-智能聊天-chat---apiv1chat)
- [5. 知识库管理 (KB)](#5-知识库管理-kb---apiv1kb)
- [6. 题目 (Questions)](#6-题目-questions---apiv1questions)
- [7. 刷题 (Quiz)](#7-刷题-quiz---apiv1quiz)
- [8. 辅导 (Tutor)](#8-辅导-tutor---apiv1tutor)
- [9. 知识追踪 (KT)](#9-知识追踪-kt---apiv1kt)
- [10. 学习分析 (Analytics)](#10-学习分析-analytics---apiv1analytics)
- [11. 学习报告 (Reports)](#11-学习报告-reports---apiv1reports)
- [12. 针对训练 (Training)](#12-针对训练-training---apiv1training)
- [13. 笔记系统 (Notes)](#13-笔记系统-notes---apiv1notes)
- [14. 独立知识搜索 (Search)](#14-独立知识搜索-search---apiv1search)
- [15. 首页建议 (Dashboard)](#15-首页建议-dashboard---apiv1dashboard)
- [16. 系统/测试接口](#16-系统测试接口)

---

## 通用说明

### 鉴权

除登录和注册外，所有接口均需在请求头中携带 Token：

```
Authorization: Bearer 7f1d8c4a9b2e6f0135a7c9d0e2b4f681
```

Token 是服务端生成的不透明随机值，数据库仅保存其 SHA-256 哈希和有效期。
登录会话默认有效 7 天，后端进程重启不会使有效会话丢失。退出登录只失效当前
Token；修改密码、重置密码和注销账号会失效该账号的全部 Token。

### 错误响应格式

```json
{
  "detail": "错误描述信息"
}
```

常见 HTTP 状态码：

| 状态码 | 含义 |
|:---:|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数有误 |
| 401 | 未登录或 Token 过期 |
| 404 | 资源不存在 |
| 409 | 冲突（如引导版本冲突） |
| 413 | 文件过大 |
| 422 | 无法处理（如 OCR 识别失败 / 参数校验失败） |
| 500 | 服务器内部错误 |
| 502 | 上游服务（Dify / TCN）异常 |
| 503 | 服务暂不可用（如 TCN 用户哈希未初始化） |

---

## 1. 账号认证 (Auth) — `/api/v1/auth`

### 1.1 注册

```
POST /api/v1/auth/register
```

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `email` | string | ✓ | 邮箱地址 |
| `password` | string | ✓ | 密码 |
| `nickname` | string | ✓ | 用户昵称，默认 `"新用户"` |
| `username` | string | | 可选用户名 |
| `verification_code` | string | | 邮箱验证码（可选） |

**成功响应** (200)：

```json
{
  "id": 1,
  "email": "user@example.com",
  "nickname": "用户昵称",
  "phone": null,
  "gender": null,
  "signature": null,
  "tags": null,
  "username": null,
  "is_active": true,
  "created_at": "2025-01-01T00:00:00",
  "access_token": "7f1d8c4a9b2e6f0135a7c9d0e2b4f681",
  "token_type": "bearer",
  "message": "注册成功"
}
```

---

### 1.2 登录

```
POST /api/v1/auth/token
```

> `username` 字段可传邮箱或手机号，密码通过 `password` 字段传入。

**请求 Body**（`application/x-www-form-urlencoded`）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `username` | string | ✓ | 邮箱或手机号 |
| `password` | string | ✓ | 密码 |

**成功响应** (200)：

```json
{
  "access_token": "7f1d8c4a9b2e6f0135a7c9d0e2b4f681",
  "token_type": "bearer",
  "expires_in": 604800
}
```

**失败响应**：

- `404`：账号不存在，返回 `{ "detail": "账号不存在，请先注册" }`。
- `401`：账号存在但密码不匹配，返回 `{ "detail": "账号或密码错误" }`。

---

### 1.3 刷新 Token

```
POST /api/v1/auth/refresh-token
```

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `refresh_token` | string | ✓ | 旧的 access_token |

**成功响应** (200)：

```json
{
  "access_token": "b5c4a3d2e1f09876543210abcdef9876",
  "token_type": "bearer",
  "expires_in": 604800,
  "message": "Token 刷新成功"
}
```

刷新成功后旧 Token 立即失效，新 Token 的有效期重新按 7 天计算。

---

### 1.4 获取当前用户信息

```
GET /api/v1/auth/users/me
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "id": 1,
  "email": "user@example.com",
  "phone": null,
  "nickname": "用户昵称",
  "gender": null,
  "signature": null,
  "tags": null,
  "username": null,
  "is_active": true,
  "created_at": "2025-01-01T00:00:00",
  "plan_info": {
    "level": 1,
    "name": "基础版",
    "daily_api_limit": 100,
    "monthly_token_limit": 10000,
    "kb_limit": 10,
    "available_models": [],
    "concurrent_limit": 1,
    "expires_at": "2026-01-01T00:00:00",
    "days_remaining": 153
  }
}
```

---

### 1.5 获取当前用户完整套餐信息

```
GET /api/v1/auth/users/me/plan
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "id": 1,
  "email": "user@example.com",
  "plan_level": 1,
  "api_limit_daily": 100,
  "token_limit_monthly": 10000,
  "knowledge_base_limit": 10,
  "model_access": "gpt-3.5-turbo",
  "concurrent_limit": 1,
  "expires_at": "2026-01-01T00:00:00",
  "days_remaining": 153,
  "plan_details": {
    "level": 1,
    "name": "基础版",
    "price_monthly": 0,
    "api_limit_daily": 100,
    "token_limit_monthly": 10000,
    "knowledge_base_limit": 10,
    "model_access": "gpt-3.5-turbo",
    "concurrent_limit": 1
  }
}
```

---

### 1.6 检查用户 API 配额

```
GET /api/v1/auth/users/me/quota
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "has_quota": true,
  "plan_level": 1,
  "plan_name": "基础版",
  "api_limit_daily": 100,
  "expires_at": "2026-01-01T00:00:00",
  "days_remaining": 153
}
```

---

### 1.7 升级套餐

```
POST /api/v1/auth/users/me/upgrade-plan
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `plan_level` | int | ✓ | 目标套餐等级 |
| `months` | int | | 购买月数，默认 1 |

**成功响应** (200)：

```json
{
  "message": "套餐升级成功",
  "new_plan_level": 2
}
```

---

### 1.8 发送验证码

```
POST /api/v1/auth/send-verification
```

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `email` | string | ✓ | 邮箱地址或手机号（字段名历史原因命名为 email） |

**成功响应** (200)：

```json
{
  "message": "验证码已发送至 user@example.com",
  "expires_in": 300
}
```

---

### 1.9 验证邮箱

```
POST /api/v1/auth/verify-email
```

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `email` | string | ✓ | 邮箱地址 |
| `code` | string | ✓ | 验证码 |

**成功响应** (200)：

```json
{
  "message": "邮箱验证成功",
  "email": "user@example.com",
  "is_email_verified": true
}
```

---

### 1.10 检查邮箱验证状态

```
GET /api/v1/auth/check-email-verification/{email}
```

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `email` | string | ✓ | 要查询的邮箱地址 |

**成功响应** (200)：

```json
{
  "email": "user@example.com",
  "is_email_verified": true,
  "email_verified_at": "2025-01-01T00:00:00"
}
```

---

### 1.11 忘记密码（发送重置邮件）

```
POST /api/v1/auth/forgot-password
```

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `email` | string | ✓ | 注册邮箱 |

**成功响应** (200)：

```json
{
  "message": "密码重置邮件已发送",
  "expires_in": 600
}
```

---

### 1.12 重置密码

```
POST /api/v1/auth/reset-password
```

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `reset_token` | string | ✓ | 邮件中的重置 Token |
| `new_password` | string | ✓ | 新密码 |

**成功响应** (200)：

```json
{
  "message": "密码重置成功",
  "email": "user@example.com"
}
```

---

### 1.13 修改密码

```
POST /api/v1/auth/change-password
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `old_password` | string | ✓ | 旧密码 |
| `new_password` | string | ✓ | 新密码 |

**成功响应** (200)：

```json
{
  "message": "密码修改成功，请使用新密码重新登录其他设备",
  "email": "user@example.com"
}
```

修改成功后该账号的全部现有 Token 立即失效，需要重新登录。

---

### 1.14 更新个人资料

```
PATCH /api/v1/auth/users/me
```

**需要鉴权**：是

**请求 Body**（所有字段均为可选，仅白名单内的字段会被更新）：

| 字段 | 类型 | 必填 | 校验规则 |
|------|------|:---:|------|
| | `phone` | string | | 空字符串可清除；非空必须是 11 位中国大陆手机号（`1` 开头纯数字）。无效 → 422 |
| | `nickname` | string | | 昵称 |
| | `gender` | string | | 空字符串可清除；非空仅接受 `"男"` 或 `"女"`。无效 → 422 |
| | `signature` | string | | 个性签名 |
| | `tags` | string | | JSON 字符串数组，如 `"[\"python\",\"ai\"]"` |

**成功响应** (200)：

```json
{
  "message": "资料更新成功",
  "updated_fields": ["nickname", "signature"]
}
```

**422 校验失败**（字段错误可由客户端通过 `loc` 稳定定位）：

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "phone"],
      "msg": "Value error, phone 必须是 11 位中国大陆手机号（1 开头）",
      "input": "12345"
    }
  ]
}
```

**409 冲突**（手机号已被其他账号绑定）：

```json
{
  "detail": "该手机号已被其他账号绑定"
}
```

---

### 1.15 退出登录

```
POST /api/v1/auth/logout
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "message": "已退出登录"
}
```

退出成功后当前请求使用的 Token 立即失效。

---

### 1.16 注销账号

```
DELETE /api/v1/auth/account
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "message": "账号已注销"
}
```

数据库关联数据、账号记录和全部持久化会话在同一事务内删除。事务提交失败时会回滚并保留账号、现有 Token 与外部 Dify 知识库；提交成功后再以非阻断方式清理旧内存会话和外部 Dify 知识库。

---

### 1.17 Token 调试接口

```
GET /api/v1/auth/test-token-info
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "status": "验证成功",
  "message": "欢迎回来，user@example.com！",
  "server_time": "2025-01-01T00:00:00",
  "your_user_id": 1,
  "hint": "如果你能看到这条消息，说明持久化 Token 会话可用。"
}
```

---

## 2. 用户套餐 (Plan) — `/api/v1/plan`

### 2.1 获取所有可用套餐

```
GET /api/v1/plan/
```

**成功响应** (200)：

```json
[
  {
    "level": 1,
    "name": "基础版",
    "price_monthly": 0.0,
    "api_limit_daily": 100,
    "token_limit_monthly": 10000,
    "knowledge_base_limit": 10,
    "model_access": "gpt-3.5-turbo",
    "concurrent_limit": 1
  },
  {
    "level": 2,
    "name": "高级版",
    "price_monthly": 29.9,
    "api_limit_daily": 500,
    "token_limit_monthly": 100000,
    "knowledge_base_limit": 50,
    "model_access": "gpt-4,gpt-3.5-turbo",
    "concurrent_limit": 3
  }
]
```

---

### 2.2 获取当前用户套餐及升级选项

```
GET /api/v1/plan/my-plan
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "current_plan": {
    "level": 1,
    "name": "基础版",
    "api_limit_daily": 100,
    "token_limit_monthly": 10000,
    "expires_at": "2026-01-01T00:00:00"
  },
  "available_upgrades": [
    {
      "level": 2,
      "name": "高级版",
      "price_monthly": 29.9,
      "api_limit_daily": 500,
      "token_limit_monthly": 100000,
      "knowledge_base_limit": 50,
      "model_access": "gpt-4,gpt-3.5-turbo",
      "concurrent_limit": 3
    }
  ]
}
```

---

## 3. 新用户引导 (Onboarding) — `/api/v1/onboarding`

### 3.1 获取引导状态

```
GET /api/v1/onboarding/state
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "should_show": true,
  "reason": "新用户首次引导",
  "state": {
    "guide_version": 1,
    "revision": 1,
    "status": "in_progress",
    "current_step": "channel",
    "steps": {
      "channel": "pending",
      "upload": "pending",
      "profile": "pending",
      "tags": "pending",
      "help": "pending"
    },
    "channel": null,
    "profile": null,
    "tags": []
  }
}
```

| `state` 字段 | 类型 | 说明 |
|------|------|------|
| `guide_version` | int | 引导版本号 |
| `revision` | int | 当前进度版本号（用于并发控制） |
| `status` | string | 引导状态：`pending` / `in_progress` / `completed` / `skipped` |
| `current_step` | string\|null | 当前步骤标识 |
| `steps` | dict | 各步骤状态映射 |
| `channel` | object\|null | 渠道信息 |
| `profile` | object\|null | 用户画像信息 |
| `tags` | array | 用户标签，每项为 `{id,name}` |

响应只输出当前结构化契约。历史账号中无法可靠映射的自由文本 `profile_answer`
降级为 `profile: null`，旧字符串标签数组降级为 `tags: []`；引导的 `status`/`revision`
和步骤终态保持不变，避免历史答案使客户端无法读取整个账号状态。

---

### 3.2 提交引导步骤

```
POST /api/v1/onboarding/step
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `expected_revision` | int | ✓ | 期望的版本号（乐观锁） |
| `step` | string | ✓ | 步骤标识（如 `channel`、`profile`、`tags`） |
| `action` | string | ✓ | 操作：`completed` / `skipped` |
| `answer` | object | | 步骤答案数据（JSON） |

**`answer` 示例**（profile 步骤）：

```json
{
  "identity_code": "student",
  "identity_other": null,
  "major_field": "计算机科学",
  "use_purposes": ["learning"],
  "function_preferences": ["knowledge_base", "practice"],
  "daily_usage": "30_60_minutes",
  "personalization_consent": true
}
```

**成功响应** (200)：同 [3.1 获取引导状态](#31-获取引导状态) 中的 `state` 字段。

**错误响应** (409)：

```json
{
  "detail": {
    "code": "onboarding_revision_conflict",
    "message": "引导进度已在其他设备更新。",
    "latest": 3
  }
}
```

---

### 3.3 完成引导

```
POST /api/v1/onboarding/complete
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `expected_revision` | int | ✓ | 期望的版本号（乐观锁） |
| `action` | string | ✓ | `completed`（全部完成）或 `skip_remaining`（跳过剩余） |

**成功响应** (200)：同 [3.1 获取引导状态](#31-获取引导状态) 中的 `state` 字段。

---

### 3.4 重新开始引导

```
POST /api/v1/onboarding/restart
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `expected_revision` | int | ✓ | 期望的版本号 |
| `mode` | string | ✓ | 固定值 `"all"` |
| `preserve_answers` | bool | ✓ | 是否保留已有答案 |

**成功响应** (200)：同 [3.1 获取引导状态](#31-获取引导状态) 中的 `state` 字段。

**错误响应** (409)：

```json
{
  "detail": {
    "code": "onboarding_already_in_progress",
    "message": "账号已经重新进入引导。",
    "latest": 2
  }
}
```

---

## 4. 智能聊天 (Chat) — `/api/v1/chat`

### 4.0 聊天服务信息

```
GET /api/v1/chat
```

> 无需鉴权，返回聊天服务的端点信息。

**成功响应** (200)：

```json
{
  "service": "chat",
  "endpoints": {
    "send": "POST /api/v1/chat",
    "history": "GET /api/v1/chat/history?session_id=xxx",
    "sessions": "GET /api/v1/chat/sessions",
    "delete_session": "DELETE /api/v1/chat/sessions/{session_id}"
  }
}
```

---

### 4.1 发送对话消息

```
POST /api/v1/chat
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `content` | string | ✓ | 用户消息内容 |
| `session_id` | string | | 会话 ID，不传则自动创建新会话 |
| `stream` | bool | | 是否 SSE 流式返回，默认 `false` |
| `collection_id` | string | | 知识库分区 ID（可选） |
| `mode` | string | | 对话模式：`"qa"`（默认）、`"learning"`、`"classroom_note"`、`"verify"`。无效值 → 400 |
| `tc_node_id` | string | | TCN 知识节点 ID（可选） |
| `tc_user_action` | string | | TCN 用户动作：`correct` / `incorrect`（可选） |
| `tc_domain_id` | string | | TCN 领域 ID（可选） |

**非流式成功响应** (200)：

```json
{
  "session_id": "abc123",
  "session_title": "用户消息前40字...",
  "role": "assistant",
  "content": "这是 AI 的回复内容...",
  "created_at": "2025-01-01T00:00:00",
  "citations": [
    {
      "doc_id": "doc_001",
      "segment_id": "seg_001",
      "title": "文档名称.pdf",
      "char_start": 0,
      "char_end": 200,
      "snippet": "引用的原文片段..."
    }
  ]
}
```

**流式响应** (SSE)：

当 `stream: true` 时，返回 `text/event-stream`：

```
event: message
data: {"session_id":"abc123","role":"assistant","content":"你"}
event: message
data: {"session_id":"abc123","role":"assistant","content":"好"}
event: message
data: {"session_id":"abc123","role":"assistant","content":"！"}
event: message
data: {"session_id":"abc123","role":"assistant","content":"","citations":[...]}
event: message
data: {"session_id":"abc123","role":"system","content":"","lvr":0.85,"diagnosis":"mastered"}
```

流式数据字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 会话 ID |
| `role` | string | `assistant` / `system` |
| `content` | string | 本次片段文本 |
| `reasoning_content` | string | 推理过程（可选，仅推理模型） |
| `tool_name` | string | 工具调用名称（可选） |
| `citations` | array | 引用溯源（最后一条非空消息时附带） |
| `lvr` | float | TCN 学习价值评分（可选，system 消息附带） |
| `diagnosis` | string | TCN 诊断结果（可选，system 消息附带） |

---

### 4.2 获取聊天历史

```
GET /api/v1/chat/history?session_id={session_id}
```

**需要鉴权**：是

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `session_id` | string | ✓ | 会话 ID |

**成功响应** (200)：

```json
[
  {
    "role": "user",
    "content": "什么是机器学习？",
    "created_at": "2025-01-01T10:00:00"
  },
  {
    "role": "assistant",
    "content": "机器学习是人工智能的一个分支...",
    "created_at": "2025-01-01T10:00:05"
  }
]
```

---

### 4.3 获取会话列表

```
GET /api/v1/chat/sessions
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "sessions": [
    {
      "id": "abc123",
      "title": "什么是机器学习？",
      "created_at": "2025-01-01T10:00:00",
      "updated_at": "2025-01-01T10:05:00",
      "message_count": 6
    }
  ]
}
```

---

### 4.4 删除聊天会话

```
DELETE /api/v1/chat/sessions/{session_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `session_id` | string | ✓ | 会话 ID |

**成功响应** (200)：

```json
{
  "message": "Chat session deleted"
}
```

---

## 5. 知识库管理 (KB) — `/api/v1/kb`

> 知识库分区有两种 URL 路径可用：`/collections` 和 `/categories`，功能完全等价。

### 5.1 列出知识库分区

```
GET /api/v1/kb/collections
GET /api/v1/kb/categories
```

**需要鉴权**：是

**成功响应** (200)：

```json
[
  {
    "id": "col_001",
    "name": "机器学习",
    "description": "机器学习相关文档",
    "document_count": 5,
    "created_at": "2025-01-01T00:00:00"
  }
]
```

---

### 5.2 创建知识库分区

```
POST /api/v1/kb/collections
POST /api/v1/kb/categories
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `name` | string | ✓ | 分区名称 |
| `description` | string | | 分区描述 |

**成功响应** (201)：

```json
{
  "id": "col_002",
  "name": "深度学习",
  "description": "深度学习相关文档",
  "document_count": 0,
  "created_at": "2025-01-01T00:00:00"
}
```

---

### 5.3 更新知识库分区

```
PATCH /api/v1/kb/collections/{collection_id}
PATCH /api/v1/kb/categories/{collection_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `collection_id` | string | ✓ | 分区 ID |

**请求 Body**（至少提供一个字段）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `name` | string | | 新名称 |
| `description` | string | | 新描述 |

**成功响应** (200)：分区对象

---

### 5.4 删除知识库分区

```
DELETE /api/v1/kb/collections/{collection_id}
DELETE /api/v1/kb/categories/{collection_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `collection_id` | string | ✓ | 分区 ID |

**成功响应** (200)：

```json
{
  "message": "分区已删除"
}
```

---

### 5.5 上传文档

```
POST /api/v1/kb/upload
```

**需要鉴权**：是

**Content-Type**：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `file` | file | ✓ | 上传的文件 |
| `collection_id` | string | | 目标分区 ID |

支持的格式：txt、md、csv、json、html、pdf、docx 及图片 OCR

**成功响应** (200)：

```json
{
  "document_id": "doc_001",
  "batch_id": "batch_abc123",
  "filename": "机器学习入门.pdf",
  "status": "indexing",
  "file_size": 1048576,
  "collection_id": "col_001"
}
```

---

### 5.6 列出文档

```
GET /api/v1/kb/documents?page=1&limit=20&collection_id=col_001
```

**需要鉴权**：是

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `page` | int | | 页码，从 1 开始，默认 1 |
| `limit` | int | | 每页条数，默认 20 |
| `collection_id` | string | | 按分区过滤（可选） |

**成功响应** (200)：

```json
{
  "documents": [
    {
      "id": "doc_001",
      "filename": "机器学习入门.pdf",
      "file_size": 1048576,
      "status": "completed",
      "segment_count": 15,
      "collection_id": "col_001",
      "created_at": "2025-01-01T00:00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20
}
```

---

### 5.7 查询文档索引进度

```
GET /api/v1/kb/documents/{batch_id}/status
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `batch_id` | string | ✓ | 上传返回的 batch_id 或 document_id |

**成功响应** (200)：

```json
{
  "batch_id": "batch_abc123",
  "status": "completed",
  "error_message": null,
  "completed_segments": 15,
  "total_segments": 15
}
```

---

### 5.8 删除文档

```
DELETE /api/v1/kb/documents/{doc_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `doc_id` | string | ✓ | 文档 ID（支持 documents.id 或 dify_document_id） |

**成功响应** (200)：

```json
{
  "message": "文档已删除",
  "document_id": "doc_001"
}
```

---

### 5.9 获取文档内容预览

```
GET /api/v1/kb/documents/{doc_id}/content
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `doc_id` | string | ✓ | 文档 ID |

**成功响应** (200)：

```json
{
  "document_id": "doc_001",
  "filename": "机器学习入门.pdf",
  "content": "解析后的文本内容...",
  "segment_count": 15,
  "has_file": true
}
```

---

### 5.10 下载/预览原始文件

```
GET /api/v1/kb/documents/{doc_id}/file
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `doc_id` | string | ✓ | 文档 ID |

**成功响应** (200)：返回文件流（`application/pdf` 等），或 FileResponse。

---

### 5.11 列出文档分段

```
GET /api/v1/kb/documents/{doc_id}/segments
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `doc_id` | string | ✓ | 文档 ID |

**成功响应** (200)：

```json
{
  "segments": [
    {
      "id": "seg_001",
      "document_id": "doc_001",
      "content": "分段内容...",
      "char_start": 0,
      "char_end": 500,
      "page_number": 1
    }
  ]
}
```

---

### 5.12 按页码平铺文档

```
GET /api/v1/kb/documents/{doc_id}/pages
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `doc_id` | string | ✓ | 文档 ID |

**成功响应** (200)：

```json
{
  "pages": [
    {
      "page_number": 1,
      "content": "该页文本内容...",
      "segment_count": 2
    }
  ]
}
```

---

### 5.13 获取单页详情

```
GET /api/v1/kb/documents/{doc_id}/pages/{page_number}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `doc_id` | string | ✓ | 文档 ID |
| `page_number` | int | ✓ | 页码 |

**成功响应** (200)：

```json
{
  "page_number": 1,
  "content": "该页完整文本内容...",
  "segments": [
    {"id": "seg_001", "content": "分段1..."}
  ]
}
```

---

### 5.14 查询知识库配置

```
GET /api/v1/kb/config
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "rag_backend": "local",
  "use_oss": false,
  "max_upload_size": 10485760,
  "max_upload_size_display": "10.0 MB",
  "supported_extensions": ["txt", "md", "csv", "json", "html", "pdf", "docx", "png", "jpg", "jpeg"]
}
```

---

## 6. 题目 (Questions) — `/api/v1/questions`

### 6.1 生成题目（从文档/分段）

```
POST /api/v1/questions/generate
```

**需要鉴权**：是

**请求 Body**（`document_id` 与 `segment_ids` 至少提供一个）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `document_id` | string | | 目标文档 ID |
| `segment_ids` | string[] | | 目标分段 ID 列表 |

**成功响应** (200)：

```json
{
  "document_id": "doc_001",
  "question_gen_status": "completed",
  "questions_created": 5,
  "questions_reused": 2,
  "total_questions": 7
}
```

---

### 6.2 列出题目

```
GET /api/v1/questions?document_id=doc_001&collection_id=col_001
```

**需要鉴权**：是

**Query 参数**（可选过滤）：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `document_id` | string | | 按文档过滤 |
| `collection_id` | string | | 按分区过滤 |

**成功响应** (200)：

```json
{
  "questions": [
    {
      "id": "q_001",
      "stem": "什么是监督学习？",
      "question_type": "single_choice",
      "options": [
        {"key": "A", "text": "有标签数据训练"},
        {"key": "B", "text": "无标签数据训练"}
      ],
      "answer": "A",
      "explanation": "监督学习使用带标签的数据进行训练...",
      "tags": ["机器学习", "监督学习"],
      "source_type": "ai_generated",
      "document_id": "doc_001",
      "collection_id": "col_001",
      "created_at": "2025-01-01T00:00:00",
      "user_answer_status": "correct",
      "attempt_count": 1
    }
  ],
  "total": 1,
  "document_id": "doc_001",
  "collection_id": "col_001",
  "answered_count": 1,
  "correct_count": 1,
  "wrong_count": 0,
  "unknown_count": 0
}
```

---

### 6.3 获取单个题目详情

```
GET /api/v1/questions/{question_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `question_id` | string | ✓ | 题目 ID |

**成功响应** (200)：

```json
{
  "id": "q_001",
  "stem": "什么是监督学习？",
  "question_type": "single_choice",
  "options": [
    {"key": "A", "text": "有标签数据训练"},
    {"key": "B", "text": "无标签数据训练"}
  ],
  "answer": "A",
  "explanation": "监督学习使用带标签的数据进行训练...",
  "tags": ["机器学习", "监督学习"],
  "source_type": "ai_generated",
  "document_id": "doc_001",
  "collection_id": "col_001",
  "created_at": "2025-01-01T00:00:00",
  "user_answer_status": "correct",
  "attempt_count": 1,
  "provenance": [
    {
      "id": "prov_001",
      "document_id": "doc_001",
      "segment_id": "seg_001",
      "excerpt": "监督学习是一种机器学习方法..."
    }
  ]
}
```

---

### 6.4 删除指定文档的题目引用

```
DELETE /api/v1/questions?document_id=doc_001
```

**需要鉴权**：是

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `document_id` | string | ✓ | 文档 ID |

**成功响应** (200)：

```json
{
  "deleted_count": 5,
  "document_id": "doc_001",
  "collection_id": null
}
```

---

### 6.5 批量删除题目引用

```
DELETE /api/v1/questions/bulk
```

**需要鉴权**：是

**请求 Body**（至少提供一个过滤条件）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `document_id` | string | | 按文档 |
| `collection_id` | string | | 按分区 |
| `question_ids` | string[] | | 按题目 ID 列表 |

**成功响应** (200)：

```json
{
  "deleted_count": 3,
  "document_id": null,
  "collection_id": null
}
```

---

### 6.6 从选中页 AI 出题（模式 B）

```
POST /api/v1/questions/generate-from-pages
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `document_id` | string | ✓ | 文档 ID |
| `page_numbers` | int[] | ✓ | 页码列表 |
| `questions_per_page` | int | | 每页出题数，默认 3 |

**成功响应** (200)：

```json
{
  "document_id": "doc_001",
  "page_numbers": [1, 2, 3],
  "mode": "generate",
  "question_gen_status": "completed",
  "questions_created": 9,
  "questions_reused": 0,
  "total_questions": 9
}
```

---

### 6.7 从选中页提取教材题目（模式 A）

```
POST /api/v1/questions/extract-from-pages
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `document_id` | string | ✓ | 文档 ID |
| `page_numbers` | int[] | ✓ | 页码列表 |

**成功响应** (200)：

```json
{
  "document_id": "doc_001",
  "page_numbers": [1, 2],
  "mode": "extract",
  "question_gen_status": "completed",
  "questions_created": 4,
  "questions_reused": 0,
  "total_questions": 4
}
```

---

## 7. 刷题 (Quiz) — `/api/v1/quiz`

### 7.1 创建刷题会话

```
POST /api/v1/quiz/sessions
```

**需要鉴权**：是

**请求 Body**（`document_id`、`collection_id`、`question_ids` 至少提供一个）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `document_id` | string | | 按文档选题 |
| `collection_id` | string | | 按分區选题 |
| `question_ids` | string[] | | 指定题目 ID 列表 |
| `title` | string | | 会话标题 |

**成功响应** (201)：

```json
{
  "id": "sess_001",
  "title": "机器学习练习",
  "status": "in_progress",
  "document_id": "doc_001",
  "collection_id": null,
  "total_questions": 10,
  "answered_count": 0,
  "started_at": "2025-01-01T10:00:00",
  "finished_at": null,
  "questions": [
    {
      "question_id": "q_001",
      "order_index": 1,
      "stem": "什么是监督学习？",
      "question_type": "single_choice",
      "options": [
        {"key": "A", "text": "有标签数据训练"},
        {"key": "B", "text": "无标签数据训练"}
      ]
    }
  ]
}
```

---

### 7.2 获取刷题会话

```
GET /api/v1/quiz/sessions/{session_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `session_id` | string | ✓ | 会话 ID |

**成功响应** (200)：同 [7.1 创建刷题会话](#71-创建刷题会话) 响应结构，含已答题进度（不含答案）。

---

### 7.3 提交答案

```
POST /api/v1/quiz/sessions/{session_id}/answers
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `session_id` | string | ✓ | 会话 ID |

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `question_id` | string | ✓ | 题目 ID |
| `user_answer` | string | | 用户答案（如 "A"） |
| `status` | string | | 答题状态，`unknown` 表示"我不会" |
| `time_spent_seconds` | int | | 答题耗时（秒） |

**成功响应** (200)：

```json
{
  "question_id": "q_001",
  "status": "correct",
  "correct_answer": "A",
  "explanation": "监督学习使用带标签的数据进行训练...",
  "citation": {
    "doc_id": "doc_001",
    "segment_id": "seg_001",
    "title": "机器学习入门.pdf",
    "char_start": 100,
    "char_end": 300,
    "snippet": "原文引用片段..."
  },
  "answered_count": 1,
  "total_questions": 10,
  "session_status": "in_progress"
}
```

---

### 7.4 获取刷题结果汇总

```
GET /api/v1/quiz/sessions/{session_id}/results
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `session_id` | string | ✓ | 会话 ID |

**成功响应** (200)：

```json
{
  "session_id": "sess_001",
  "status": "finished",
  "total_questions": 10,
  "correct_count": 7,
  "wrong_count": 2,
  "unknown_count": 1,
  "items": [
    {
      "question_id": "q_001",
      "stem": "什么是监督学习？",
      "user_answer": "A",
      "status": "correct",
      "correct_answer": "A",
      "explanation": "监督学习使用带标签的数据进行训练...",
      "citation": {
        "doc_id": "doc_001",
        "segment_id": "seg_001",
        "title": "机器学习入门.pdf",
        "char_start": 100,
        "char_end": 300,
        "snippet": "原文引用片段..."
      }
    }
  ]
}
```

---

## 8. 辅导 (Tutor) — `/api/v1/tutor`

### 8.1 创建辅导会话

```
POST /api/v1/tutor/sessions
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `question_id` | string | ✓ | 题目 ID |
| `quiz_session_id` | string | | 刷题会话 ID（可选） |
| `quiz_answer_id` | string | | 答题记录 ID（可选） |

**成功响应** (201)：

```json
{
  "id": "tutor_sess_001",
  "question_id": "q_001",
  "document_id": "doc_001",
  "segment_id": "seg_001",
  "quiz_answer_id": null,
  "status": "in_progress",
  "question_stem": "什么是监督学习？",
  "segment_context": {
    "segment_id": "seg_001",
    "title": "第一章 绪论",
    "snippet": "监督学习是机器学习的一种方法..."
  },
  "messages": [],
  "created_at": "2025-01-01T10:00:00",
  "updated_at": "2025-01-01T10:00:00"
}
```

---

### 8.2 获取辅导会话

```
GET /api/v1/tutor/sessions/{session_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `session_id` | string | ✓ | 辅导会话 ID |

**成功响应** (200)：同 [8.1 创建辅导会话](#81-创建辅导会话) 响应结构，含对话历史。

---

### 8.3 发送辅导消息

```
POST /api/v1/tutor/sessions/{session_id}/messages
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `session_id` | string | ✓ | 辅导会话 ID |

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `content` | string | ✓ | 用户消息内容 |
| `stream` | bool | | 是否 SSE 流式返回，默认 `false` |

**非流式成功响应** (200)：

```json
{
  "role": "assistant",
  "content": "让我们来理解一下监督学习...",
  "created_at": "2025-01-01T10:00:05"
}
```

**流式响应** (SSE)：返回 `text/event-stream`，格式与 [4.1 发送对话消息](#41-发送对话消息) 流式类似。

---

## 9. 知识追踪 (KT) — `/api/v1/kt`

> 需要 TCN 服务就绪。所有 KT 端点增加了前置 TCN 可用性检查，引擎不可达时统一返回 503。

### 9.1 推荐学习路径

```
POST /api/v1/kt/learning-path
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `top_k` | int | | 推荐节点数，默认 5 |

**成功响应** (200)：

```json
{
  "recommendations": [
    {
      "skill_id": "sk_001",
      "skill_name": "线性回归",
      "mastery": 0.35,
      "priority": "high",
      "reason": "当前掌握度较低，建议优先复习"
    }
  ]
}
```

---

### 9.2 查询节点先修关系

```
POST /api/v1/kt/prerequisites
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `skill_id` | string | ✓ | 技能节点 ID |

**成功响应** (200)：

```json
{
  "skill": {
    "id": "sk_001",
    "name": "线性回归"
  },
  "prerequisites": [],
  "dependents": [
    {"id": "sk_002", "name": "逻辑回归"}
  ]
}
```

---

### 9.3 获取技能图谱

```
GET /api/v1/kt/skill-graph
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "nodes": [
    {"id": "sk_001", "name": "线性回归", "mastery": 0.85, "group": "supervised_learning"}
  ],
  "edges": [
    {"source": "sk_001", "target": "sk_002", "relation": "prerequisite"}
  ]
}
```

---

### 9.4 获取技能掌握状态

```
GET /api/v1/kt/states
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "sk_001": 0.85,
  "sk_002": 0.45,
  "sk_003": 0.92
}
```

---

### 9.5 知识状态摘要（System Prompt 注入用）

```
GET /api/v1/kt/summary
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "summary": "该用户已掌握监督学习基础...",
  "overall_mastery": 0.72,
  "strong_areas": ["线性回归", "决策树"],
  "weak_areas": ["支持向量机", "神经网络"],
  "last_updated": "2025-01-01T00:00:00"
}
```

---

### 9.6 先修断层查询

```
GET /api/v1/kt/gaps?limit=50&threshold=0.6
```

**需要鉴权**：是

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `limit` | int | | 最大返回数，范围 1-200，默认 50 |
| `threshold` | float | | 掌握度阈值，范围 0.0-1.0，默认 0.6 |

**成功响应** (200)：

```json
{
  "gaps": [
    {
      "skill_id": "sk_005",
      "skill_name": "支持向量机",
      "missing_prerequisites": ["sk_003", "sk_004"],
      "current_mastery": 0.25,
      "recommended_action": "先学习数学基础"
    }
  ]
}
```

---

### 9.7 认知脆弱点（伪掌握）预警

```
GET /api/v1/kt/vulnerabilities?limit=50
```

**需要鉴权**：是

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `limit` | int | | 最大返回数，范围 1-200，默认 50 |

**成功响应** (200)：

```json
{
  "vulnerabilities": [
    {
      "skill_id": "sk_002",
      "skill_name": "逻辑回归",
      "displayed_mastery": 0.75,
      "actual_mastery": 0.40,
      "risk_level": "high"
    }
  ]
}
```

---

### 9.8 LVR 预警状态

```
GET /api/v1/kt/lvr-alert?limit=10
```

**需要鉴权**：是

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `limit` | int | | 最大返回数，范围 1-50，默认 10 |

**成功响应** (200)：

```json
{
  "alerts": [
    {
      "skill_id": "sk_003",
      "skill_name": "KNN 算法",
      "lvr": 0.92,
      "diagnosis": "high_risk_forgetting",
      "backtrack_suggestions": ["sk_001"]
    }
  ]
}
```

---

## 10. 学习分析 (Analytics) — `/api/v1/analytics`

### 10.1 获取学习统计

```
GET /api/v1/analytics/stats
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "documents": {
    "total": 10,
    "indexed": 8,
    "processing": 1,
    "failed": 1,
    "study_zone": 5,
    "with_questions": 4
  },
  "questions": {
    "total": 50,
    "answered": 30,
    "correct": 22,
    "wrong": 6,
    "unknown": 2,
    "accuracy_rate": 73
  },
  "document_progress": [
    {
      "document_id": "doc_001",
      "document_name": "机器学习入门.pdf",
      "question_total": 10,
      "answered_count": 8,
      "correct_count": 6,
      "wrong_count": 2,
      "unknown_count": 0,
      "accuracy_rate": 75
    }
  ],
  "recent_sessions": [
    {
      "id": "sess_001",
      "document_id": "doc_001",
      "document_name": "机器学习入门.pdf",
      "status": "finished",
      "total_questions": 10,
      "answered_count": 10,
      "started_at": "2025-01-01T10:00:00",
      "finished_at": "2025-01-01T10:30:00"
    }
  ],
  "recent_answers": [
    {
      "question_id": "q_001",
      "stem": "什么是监督学习？",
      "status": "correct",
      "document_id": "doc_001",
      "document_name": "机器学习入门.pdf",
      "answered_at": "2025-01-01T10:05:00"
    }
  ]
}
```

---

### 10.2 按标签与题型统计错题

```
GET /api/v1/analytics/tag-stats
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "by_tag": [
    {
      "tag": "机器学习",
      "question_type": "all",
      "correct_count": 15,
      "wrong_count": 5,
      "unknown_count": 2,
      "total_attempts": 22,
      "accuracy_rate": 68
    }
  ],
  "by_question_type": [
    {
      "tag": "all",
      "question_type": "single_choice",
      "correct_count": 20,
      "wrong_count": 3,
      "unknown_count": 1,
      "total_attempts": 24,
      "accuracy_rate": 83
    }
  ]
}
```

---

### 10.3 生成 LLM 学习报告（别名路由）

```
POST /api/v1/analytics/learning-report
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "report": {
    "id": "report_001",
    "title": "2025年第1周学习报告",
    "content_md": "# 学习报告\n...",
    "collection_id": null,
    "note_type": "report",
    "created_at": "2025-01-07T00:00:00"
  },
  "saved_to_notes": true
}
```

---

## 11. 学习报告 (Reports) — `/api/v1/reports`

### 11.1 生成学习报告

```
POST /api/v1/reports/generate
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "report": {
    "id": "report_001",
    "title": "2025年第1周学习报告",
    "content_md": "# 学习报告\n\n## 概览\n...",
    "collection_id": null,
    "note_type": "report",
    "created_at": "2025-01-07T00:00:00"
  },
  "saved_to_notes": true
}
```

---

### 11.2 列出历史学习报告

```
GET /api/v1/reports
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "reports": [
    {
      "id": "report_001",
      "title": "2025年第1周学习报告",
      "content_md": "# 学习报告\n...",
      "collection_id": null,
      "note_type": "report",
      "created_at": "2025-01-07T00:00:00"
    }
  ],
  "total": 1
}
```

---

### 11.3 获取最新学习报告

```
GET /api/v1/reports/latest
```

**需要鉴权**：是

**成功响应** (200)：

```json
{
  "id": "report_001",
  "title": "2025年第1周学习报告",
  "content_md": "# 学习报告\n...",
  "collection_id": null,
  "note_type": "report",
  "created_at": "2025-01-07T00:00:00"
}
```

---

### 11.4 获取指定学习报告

```
GET /api/v1/reports/{report_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `report_id` | string | ✓ | 报告 ID |

**成功响应** (200)：同 [11.3 获取最新学习报告](#113-获取最新学习报告) 结构。

---

## 12. 针对训练 (Training) — `/api/v1/training`

### 12.1 启动针对训练

```
POST /api/v1/training/targeted/start
```

**需要鉴权**：是

> Agent 制定训练计划：选题 + rationale，并创建刷题会话。支持 `report_id` 与恢复未完成会话。

**请求 Body**（均为可选）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `report_id` | string | | 学习报告 ID |
| `force_new` | bool | | 是否强制新建（跳过未完成会话恢复），默认 `false` |

**成功响应** (201)：

```json
{
  "session": {
    "id": "sess_002",
    "title": "针对训练 - 机器学习薄弱项",
    "status": "in_progress",
    "document_id": null,
    "collection_id": null,
    "total_questions": 5,
    "answered_count": 0,
    "started_at": "2025-01-01T11:00:00",
    "finished_at": null,
    "questions": [...]
  },
  "weak_tags": [
    {"tag": "神经网络", "wrong_count": 3, "correct_count": 1, "accuracy_rate": 25}
  ],
  "question_ids": ["q_010", "q_011", "q_012"],
  "report_id": "report_001",
  "rationale": "根据最近学习报告，神经网络是最薄弱的知识点，建议优先练习。",
  "agent_session_id": "agent_sess_001"
}
```

---

### 12.2 查询报告下未完成的训练会话

```
GET /api/v1/training/targeted/reports/{report_id}/active-session
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `report_id` | string | ✓ | 学习报告 ID |

**成功响应** (200)：

```json
{
  "session_id": "sess_002",
  "report_id": "report_001",
  "answered_count": 2,
  "total_questions": 5,
  "agent_session_id": "agent_sess_001",
  "status": "in_progress"
}
```

> 若无未完成会话，返回 `null`。

---

### 12.3 恢复针对训练会话

```
GET /api/v1/training/targeted/sessions/{session_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `session_id` | string | ✓ | 训练会话 ID |

**成功响应** (200)：同 [12.1 启动针对训练](#121-启动针对训练) 响应结构。

---

### 12.4 针对训练 AI 辅导

```
POST /api/v1/training/targeted/tutor/{agent_session_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `agent_session_id` | string | ✓ | Agent 会话 ID（从启动训练返回） |

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `content` | string | ✓ | 用户消息内容 |
| `stream` | bool | | 是否 SSE 流式返回，默认 `true` |

**非流式成功响应** (200)：

```json
{
  "role": "assistant",
  "content": "针对神经网络这个知识点...",
  "agent_session_id": "agent_sess_001"
}
```

**流式响应** (SSE)：返回 `text/event-stream`，每条 SSE 事件格式为：

```
event: message
data: {"agent_session_id":"agent_sess_001","role":"assistant","content":"..."}
```

---

## 13. 笔记系统 (Notes) — `/api/v1/notes`

> 笔记删除采用**软删除 + 7 天回收站**方案。删除后笔记移入回收站保留 7 天，
> 期间可恢复；到期后服务端自动物理清理。删除和恢复均基于 `expected_revision`
> 乐观锁，冲突返回 409。列表和详情默认排除已删除笔记。

### 13.1 列出笔记

```
GET /api/v1/notes?page=1&limit=100&note_type=manual
```

**需要鉴权**：是

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| | `page` | int | | 页码（≥1），默认 1 |
| | `limit` | int | | 每页条数（1-200），默认 100 |
| | `note_type` | string | | 笔记类型：`manual` / `report` 等（可选过滤） |

> 默认排除已删除（`deleted_at IS NOT NULL`）的笔记。

**成功响应** (200)：

```json
[
  {
    "id": "note_001",
    "title": "学习笔记 - 监督学习",
    "content_md": "# 监督学习\n\n监督学习是...",
    "note_type": "manual",
    "collection_id": "col_001",
    "revision": 1,
    "created_at": "2025-01-01T10:00:00",
    "updated_at": "2025-01-01T10:30:00"
  }
]
```

`revision` 是笔记的稳定整数版本令牌：创建时为 `1`，每次成功的 `PATCH`、
`DELETE` 或 `POST /restore` 恰好递增 `1`。列表、详情、创建和更新响应均
返回它，客户端应把该值持久化为离线 outbox 操作的基线。

`created_at` / `updated_at` 仅用于展示。历史 SQLite 数据可能为 `null`，且当前服务
沿用无偏移量的 UTC ISO 8601 表示；客户端不得根据时间戳精度、时区或空值推导版本。

---

### 13.2 获取单条笔记

```
GET /api/v1/notes/{note_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| | `note_id` | string | ✓ | 笔记 ID |

**成功响应** (200)：同 [13.1 列出笔记](#131-列出笔记) 中的单条结构。

---

### 13.3 创建笔记

```
POST /api/v1/notes
```

**需要鉴权**：是

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| | `title` | string | ✓ | 笔记标题 |
| | `content_md` | string | | Markdown 内容，默认 `""` |
| | `collection_id` | string | | 所属知识库分区 ID（可选） |
| | `note_type` | string | | 笔记类型，默认 `"manual"` |

**成功响应** (201)：同 [13.1 列出笔记](#131-列出笔记) 中的单条结构。

---

### 13.4 更新笔记

```
PATCH /api/v1/notes/{note_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| | `note_id` | string | ✓ | 笔记 ID |

**请求 Body**（`expected_revision` 必填；其他字段可选，传 `null` 表示不更新）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| | `expected_revision` | int | ✓ | 客户端最后读取到的稳定版本，必须 ≥ 1 |
| | `title` | string | | 新标题 |
| | `content_md` | string | | 新 Markdown 内容 |
| | `collection_id` | string | | 新分区 ID |
| | `note_type` | string | | 新笔记类型 |

**成功响应** (200)：同 [13.1 列出笔记](#131-列出笔记) 中的单条结构。

**版本冲突** (409)：当该用户的笔记已被其他成功写入推进版本时，服务不会写入请求
内容，也不会回传最新笔记正文、标题或标签。响应固定只含错误码、可展示说明和当前
版本元数据：

```json
{
  "detail": {
    "code": "note_revision_conflict",
    "detail": "笔记已被更新，请使用最新版本重试",
    "current_revision": 2
  }
}
```

`note_id` 不存在或不属于当前用户时仍返回普通 `404`，不返回 `current_revision`，
避免通过冲突接口探测其他用户资源。

> 已软删除（`deleted_at IS NOT NULL`）的笔记不能通过 PATCH 更新，需先恢复。

---

### 13.5 删除笔记（软删除）

```
DELETE /api/v1/notes/{note_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| | `note_id` | string | ✓ | 笔记 ID |

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| | `expected_revision` | int | ✓ | 客户端记录的 revision（≥1） |

**成功响应** (200)：

```json
{
  "message": "笔记已移入回收站",
  "revision": 3
}
```

笔记软删除后：
- 从普通列表和详情中消失（默认过滤 `WHERE deleted_at IS NULL`）
- 进入回收站，7 天内可通过 [13.7 恢复笔记](#137-恢复笔记) 恢复
- `revision` 仍递增 `1`
- 重复删除已移入回收站的笔记为**幂等操作**，返回相同结果

**版本冲突** (409)：同 [13.4 更新笔记](#134-更新笔记) 的冲突格式。

---

### 13.6 回收站列表

```
GET /api/v1/notes/trash/items?page=1&limit=50
```

**需要鉴权**：是

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| | `page` | int | | 页码（≥1），默认 1 |
| | `limit` | int | | 每页条数（1-200），默认 50 |

**成功响应** (200)：

```json
[
  {
    "id": "note_001",
    "title": "已删除的笔记",
    "note_type": "manual",
    "revision": 3,
    "deleted_at": "2025-01-01T12:00:00",
    "deleted_by_revision": 1
  }
]
```

> `revision` 是删除后的当前版本号，用于恢复时的乐观锁；`deleted_by_revision`
> 是触发删除时的 revision（可审计用途）。

---

### 13.7 恢复笔记

```
POST /api/v1/notes/{note_id}/restore
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| | `note_id` | string | ✓ | 笔记 ID |

**请求 Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| | `expected_revision` | int | ✓ | 回收站中记录的 revision（≥1） |

**成功响应** (200)：同 [13.1 列出笔记](#131-列出笔记) 中的单条结构，
`revision` 递增 `1`，`deleted_at` 恢复为 `null`。

恢复后笔记重新出现在普通列表中，并从回收站消失。

**错误响应**：

- `404`：笔记不存在、不属于当前用户或不在回收站中
- `409`：revision 冲突（同 [13.4 更新笔记](#134-更新笔记) 格式）
- 重复恢复已恢复的笔记为**幂等操作**，返回 200

---

### 13.8 软删除与回收站说明

| 行为 | 说明 |
|------|------|
| 保留期 | 删除后服务端保留 7 天，到期自动物理清理 |
| 并发安全 | 删除和恢复均基于 `expected_revision` 原子条件写入（`UPDATE ... WHERE revision=:expected`） |
| 跨账号隔离 | 所有回收站操作均按 `user_id` 过滤，用户 A 无法查看或操作用户 B 的已删除笔记 |
| 幂等性 | 重复删除已删除笔记 → 200；重复恢复已恢复笔记 → 200 |
| 编辑限制 | 已删除笔记不能通过 PATCH 更新，必须先恢复 |
| 迁移 | 新增 `deleted_at`（DateTime）和 `deleted_by_revision`（Integer）可空列；SQLite 回滚使用 batch mode |
| 客户端注意 | 当前后端负责 7 天清理，客户端不应自行计算和展示"剩余恢复天数"计时器 |

### 13.9 上传附件

```
POST /api/v1/notes/{note_id}/attachments
```

**需要鉴权**：是
**Content-Type**：`multipart/form-data`

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `note_id` | string | ✓ | 笔记 ID |

**表单字段**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `file` | file | ✓ | 图片或音频文件 |

> 支持 SHA-256 去重：相同文件重复上传不会重复占用存储空间，直接复用已有文件。
> 单文件上限：图片 10 MB、音频 20 MB；单笔记附件上限 20 个。

**成功响应** (201)：

```json
{
  "id": "att_3f8a7b2c",
  "note_id": "note_001",
  "media_type": "image",
  "mime_type": "image/png",
  "file_size": 245760,
  "checksum": "a1b2c3d4e5f6...",
  "original_filename": "screenshot.png",
  "width": null,
  "height": null,
  "duration_seconds": null,
  "uploaded_at": "2025-01-01T15:00:00"
}
```

**错误响应**：

- `404`：笔记不存在或不属于当前用户
- `400`：文件类型不支持 / 超过大小限制 / 附件数量达上限

### 13.10 下载/预览附件

```
GET /api/v1/notes/attachments/{attachment_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `attachment_id` | string | ✓ | 附件 ID |

**成功响应** (200)：返回文件流（`image/png`、`audio/mp4` 等），响应头包含：

```
Cache-Control: private, max-age=3600
Accept-Ranges: bytes
```

支持 HTTP `Range` 请求（206 Partial Content），客户端可按需分段加载音频。

**错误响应**：

- `404`：附件不存在、不属于当前用户或物理文件丢失

### 13.11 删除附件

```
DELETE /api/v1/notes/attachments/{attachment_id}
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `attachment_id` | string | ✓ | 附件 ID |

**成功响应** (200)：

```json
{
  "message": "附件已删除"
}
```

> 删除 DB 记录同时清理物理文件；若其他记录引用同一文件（去重场景），则仅删除记录不删除文件。

### 13.12 列出笔记附件

```
GET /api/v1/notes/{note_id}/attachments
```

**需要鉴权**：是

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `note_id` | string | ✓ | 笔记 ID |

**成功响应** (200)：

```json
[
  {
    "id": "att_3f8a7b2c",
    "note_id": "note_001",
    "media_type": "image",
    "mime_type": "image/png",
    "file_size": 245760,
    "checksum": "a1b2c3d4e5f6...",
    "original_filename": "screenshot.png",
    "width": null,
    "height": null,
    "duration_seconds": null,
    "uploaded_at": "2025-01-01T15:00:00"
  }
]
```

### 13.13 附件说明

| 行为 | 说明 |
|------|------|
| 支持类型 | 图片：png / jpeg / gif / webp / svg；音频：mp4 / mpeg / ogg / wav / webm |
| 去重 | 基于 SHA-256 校验和，同一用户相同文件只存一份 |
| 孤儿清理 | 上传后若笔记未保存，超过 60 分钟的未挂载附件会被自动物理清理 |
| 生命周期 | 附件随笔记软删除进入回收站，笔记物理删除时附件不自动清理（需手动删除或依赖孤儿机制） |
| 安全 | 下载时检查 `user_id` 匹配；图片不内联返回原始二进制，统一使用 `Content-Disposition: inline` |
| 迁移 | 新增 `note_attachments` 表；SQLite 回滚使用 batch mode |

---

## 14. 独立知识搜索 (Search) — `/api/v1/search`

### 14.1 关键词搜索

```
GET /api/v1/search?q=中国近代史&scope=all&page=1&limit=20&collection_id=col_001
```

**需要鉴权**：是

这是独立的关键词检索接口，不调用 LLM、Dify 或 embedding 向量检索。所有查询都先按
当前 Bearer 用户隔离，再使用词法子串匹配；因此 embedding 模型不可用时，精确关键词
仍可稳定命中。

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `q` | string | ✓ | 非空关键词；空字符串或仅空白返回 422 |
| `scope` | string | | `all`（默认）、`notes` 或 `documents`；其他值返回 422 |
| `page` | int | | 页码，范围 ≥ 1，默认 `1` |
| `limit` | int | | 每页条数，范围 1-100，默认 `20` |
| `collection_id` | string | | 可选；仅检索当前用户该分区内的资料和笔记 |

**成功响应** (200)：

```json
{
  "query": "中国近代史",
  "items": [
    {
      "id": "note_001",
      "type": "note",
      "title": "复习安排",
      "subtitle": "本周复习中国近代史的关键事件。",
      "updated_at": "2026-08-02T10:00:00",
      "collection_id": "col_001",
      "match_source": "content",
      "indexing_status": null
    },
    {
      "id": "doc_001",
      "type": "document",
      "title": "历史课程资料.pdf",
      "subtitle": "中国近代史从鸦片战争开始。",
      "updated_at": "2026-08-02T09:30:00",
      "collection_id": "col_001",
      "match_source": "content",
      "indexing_status": "completed"
    }
  ],
  "total": 2,
  "page": 1,
  "limit": 20,
  "partial": false,
  "pending_document_count": 0
}
```

`items` 字段说明：

| 字段 | 说明 |
|------|------|
| `type` | `note` 或 `document` |
| `subtitle` | 笔记摘要、资料标题说明或命中正文片段 |
| `match_source` | `title` 表示笔记标题/资料名命中；`content` 表示笔记正文或允许检索的资料片段命中 |
| `indexing_status` | 资料的当前索引状态；笔记为 `null` |

笔记始终只匹配当前用户的 `title` 与 `content_md`。资料名 `display_name` 可以直接匹配；
只有同时满足 `zone=study`、`segment_status=completed`、`indexing_status=completed` 的资料，
其分段正文才会以 `match_source=content` 返回。处理中的资料若资料名匹配，仍可作为
`title` 命中返回，但不会被宣称为正文可检索。

`scope=all` 或 `scope=documents` 时，`pending_document_count` 统计当前用户及可选分区内、
尚未完成分段或索引的学习区资料；大于 0 时 `partial=true`，表示资料正文搜索可能不完整。
`scope=notes` 时这两个字段固定为 `0` / `false`。无命中是正常的 `200` 与空 `items`。

---

## 15. 首页建议 (Dashboard) — `/api/v1/dashboard`

### 15.1 获取个性化学习建议

```
GET /api/v1/dashboard/suggestions
```

**需要鉴权**：是

> 根据用户知识库文档列表，调用 LLM 生成 2-3 条个性化学习建议（每条不超过 30 字）。若知识库为空，返回默认引导建议。

**成功响应** (200)：

```json
{
  "suggestions": [
    "复习《机器学习入门》的核心概念",
    "整理神经网络相关的学习笔记",
    "尝试向 Tina 提问'梯度下降的原理'"
  ]
}
```

---

## 16. 系统/测试接口

### 16.1 健康检查与部署契约

```
GET /health
```

**成功响应** (200)：

```json
{
  "status": "ok",
  "skills_count": 128,
  "model_loaded": true,
  "llm_ready": true,
  "tcn_status": "ok",
  "question_generation": {
    "ready": true,
    "status": "available"
  },
  "api_contract": {
    "status": "ok",
    "required_paths": [
      "/api/v1/onboarding/complete",
      "/api/v1/onboarding/restart",
      "/api/v1/onboarding/state",
      "/api/v1/onboarding/step"
    ],
    "missing_paths": []
  }
}
```

`status=degraded` 可能仅表示 TCN 不可达；部署必须同时检查
`api_contract.status=ok`。若必需路由缺失，`missing_paths` 会列出差异，Windows
启动脚本将停止刚启动的进程并以失败退出。

---

### 16.2 测试套餐查询

```
GET /test-plan-query/{user_id}
```

**说明**：开发调试用接口，查询指定用户套餐详情。

**路径参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `user_id` | int | ✓ | 用户 ID |

**成功响应** (200)：

```json
{
  "id": 1,
  "email": "user@example.com",
  "plan_level": 1,
  "plan_name": "基础版",
  "api_limit_daily": 100,
  "expires_at": "2026-01-01T00:00:00",
  "days_remaining": 153
}
```

---

> **文档版本**: v2.5 · **更新时间**: 2026-08-05 · **维护团队**: 知拾 (Zhishi) 后端组
