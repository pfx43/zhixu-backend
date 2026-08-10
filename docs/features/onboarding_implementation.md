# 新用户首次引导实施说明

> 状态：已实现全部接口（state / step / complete / restart）
>
> 更新日期：2026-07-31

## 1. 背景与业务目标

新用户注册完成后，系统需要引导其快速完成首次使用准备，提升后续进入知识库、题库、学习计划等能力的体验。当前版本已实现完整的引导生命周期：新用户注册时自动初始化引导状态，前端可查询状态、逐步提交/跳过步骤、完成或跳过整个引导，以及旧账号主动重置引导。

### 业务目标

- 让新用户在注册后进入一次明确的首次引导流程（注册时自动初始化 `onboarding_state`）。
- 让旧账号在需要时重新进入引导，而不影响已有业务数据。
- 使用统一的 onboarding 记录，保存当前步骤、答案、标签和版本信息。
- 为前端提供稳定的引导状态响应，便于展示当前步骤和错误提示。
- 支持多端并发安全，通过 revision 乐观锁防止静默覆盖。

---

## 2. 当前已实现接口

当前版本已完整实现以下四个接口。

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/v1/onboarding/state` | 查询当前引导状态（含 should_show 判定） |
| `POST` | `/api/v1/onboarding/step` | 提交或跳过单个步骤 |
| `POST` | `/api/v1/onboarding/complete` | 完成或跳过整个引导流程 |
| `POST` | `/api/v1/onboarding/restart` | 重置引导流程（历史账号也可用） |

所有接口均需 Bearer Token 鉴权。

### 2.1 查询引导状态

- 请求地址：`GET /api/v1/onboarding/state`
- 认证：需要 Bearer Token
- 请求体：无

成功响应（200）—— 新账号 / 进行中：

```json
{
  "should_show": true,
  "reason": "in_progress",
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
    "tags": null
  }
}
```

成功响应（200）—— 历史无记录账号：

```json
{
  "should_show": false,
  "reason": "legacy_without_state",
  "state": null
}
```

字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| should_show | boolean | 前端是否应展示引导界面 |
| reason | string | 判定原因 |
| state | object 或 null | 完整引导状态；历史无记录时为 null |
| state.guide_version | integer | 引导版本号 |
| state.revision | integer | 当前 revision（乐观锁用） |
| state.status | string | pending / in_progress / completed / skipped |
| state.current_step | string 或 null | 当前待处理步骤，全部完成时为 null |
| state.steps | object | 各步骤状态映射 |
| state.channel | any 或 null | 渠道答案 |
| state.profile | any 或 null | 画像答案 |
| state.tags | any 或 null | 用户标签 |

---

### 2.2 提交或跳过单个步骤

- 请求地址：`POST /api/v1/onboarding/step`
- 认证：需要 Bearer Token
- 请求体：

```json
{
  "expected_revision": 1,
  "step": "channel",
  "action": "completed",
  "answer": {
    "channel": "friend",
    "channel_remark": "同学推荐"
  }
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| expected_revision | integer | 是 | 前端期望的当前 revision，用于冲突检测 |
| step | string | 是 | 步骤 ID：channel / upload / profile / tags / help |
| action | string | 是 | completed 或 skipped |
| answer | object | 否 | 步骤答案，按步骤类型不同而异 |

业务规则：

- 成功提交后 revision 自动 +1，current_step 自动推进到下一个 pending 步骤。
- 当所有步骤均为 completed 或 skipped 时，status 自动变为 completed。
- answer 会持久化到对应的 channel_answer / profile_answer / tags 字段（仅 channel / profile / tags 三个步骤）。
- upload 和 help 步骤仅记录完成/跳过状态，不存储答案内容。

成功响应（200）：返回完整 OnboardingStateOut（字段同 2.1 中的 state）。

失败响应：

- 409 onboarding_revision_conflict：expected_revision 与当前 revision 不匹配
- 422：未知步骤 / 不支持的 action / 参数校验失败

---

### 2.3 完成或跳过整个引导

- 请求地址：`POST /api/v1/onboarding/complete`
- 认证：需要 Bearer Token
- 请求体：

全部已处理时完成：
```json
{ "expected_revision": 5, "action": "completed" }
```

跳过剩余步骤：
```json
{ "expected_revision": 5, "action": "skip_remaining" }
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| expected_revision | integer | 是 | 前端期望的当前 revision |
| action | string | 是 | completed（仅在全部步骤已处理时可用）或 skip_remaining（将剩余 pending 步骤标记为 skipped） |

成功响应（200）：返回完整 OnboardingStateOut。

失败响应：

- 409 onboarding_revision_conflict：revision 不匹配
- 422：action=completed 但仍有步骤未处理 / 不支持的动作

---

### 2.4 重启首次引导

- 请求地址：`POST /api/v1/onboarding/restart`
- 认证：需要 Bearer Token
- 请求体：

```json
{ "expected_revision": 7, "mode": "all", "preserve_answers": true }
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| expected_revision | integer | 是 | 前端期望的当前引导 revision |
| mode | string | 是 | 当前版本固定为 all |
| preserve_answers | boolean | 是 | 是否保留已填写的答案 |

成功响应（200）：返回完整 OnboardingStateOut。

失败响应（409）—— 已经在引导中：

```json
{
  "detail": {
    "code": "onboarding_already_in_progress",
    "message": "账号已经重新进入引导。",
    "latest": {
      "guide_version": 1, "revision": 2, "status": "in_progress",
      "current_step": "channel", "steps": {}, "channel": null, "profile": null, "tags": null
    }
  }
}
```

失败响应（409）—— 版本冲突：

```json
{
  "detail": {
    "code": "onboarding_revision_conflict",
    "message": "引导进度已在其他设备更新。",
    "latest": {
      "guide_version": 1, "revision": 5, "status": "completed",
      "current_step": null, "steps": {}, "channel": null, "profile": null, "tags": null
    }
  }
}
```

其他错误：

- 401：未登录 / Token 失效
- 422：请求参数校验失败

---

## 3. 业务流程时序

### 3.1 新用户注册到引导完成完整链路

```
POST /api/v1/auth/register
  -> 系统创建用户账号
  -> 同一事务中初始化 onboarding_state（status=in_progress, current_step=channel, revision=1）
  -> 返回 Token

GET /api/v1/onboarding/state
  -> 返回 should_show=true, reason="in_progress", 完整状态
  -> 前端跳转 /onboarding

POST /api/v1/onboarding/step  (x5 次)
  -> 依次完成 channel -> upload -> profile -> tags -> help
  -> 每次返回最新完整状态，revision 递增

POST /api/v1/onboarding/complete
  -> action="completed"，status 变为 completed

后续登录：
  GET /api/v1/onboarding/state
  -> should_show=false，正常进入工作区
```

### 3.2 历史账号重置流程

```
POST /api/v1/onboarding/restart
  -> 无记录则自动创建，有记录则校验 revision
  -> 重置为 in_progress / channel / 全部 pending
  -> 前端进入引导
```

### 3.3 多端冲突处理

```
设备 A: POST /step (expected_revision=3) -> 成功，revision 变为 4
设备 B: POST /step (expected_revision=3) -> 409 revision_conflict
设备 B: GET /state -> 刷新最新状态，重新渲染
```

---

## 4. 业务数据模型说明

### 4.1 onboarding_state 表

表名：onboarding_state

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| user_id | INTEGER | 用户 ID，唯一，关联 users 表 |
| guide_version | INTEGER | 当前引导版本号，默认 1 |
| revision | INTEGER | 当前引导修订版本，用于多端冲突检测 |
| status | VARCHAR(32) | 状态：pending / in_progress / completed / skipped |
| current_step | VARCHAR(32) | 当前步骤：channel / upload / profile / tags / help |
| steps | JSON | 各步骤状态集合，键值如 pending / completed / skipped |
| channel_answer | JSON | 渠道类回答 |
| profile_answer | JSON | 用户画像类回答 |
| tags | JSON | 用户标签 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 最后更新时间 |

### 4.2 字段设计说明

- user_id 采用唯一约束，保证每个用户只有一条 onboarding 记录。
- revision 用于乐观锁式冲突检测，避免多端同时修改造成状态覆盖。
- steps 适合前端展示当前步骤完成度。
- channel_answer、profile_answer、tags 用于保存用户填写的引导答案。
- 新用户注册时自动创建记录，历史账号无记录时查询返回 legacy_without_state 而不自动创建。

---

## 5. 业务规则与边界场景

### 5.1 新用户首次进入

- 注册时在同一数据库事务中初始化 onboarding_state。
- 前端获取 Token 后调用 GET /state，should_show=true 则跳转引导页。

### 5.2 历史无记录账号

- GET /state 返回 should_show=false, reason="legacy_without_state"，前端不拦截。
- 历史账号可通过 POST /restart 主动触发引导。

### 5.3 重复提交

- 状态为 in_progress 时调用 restart 返回 409 onboarding_already_in_progress。

### 5.4 版本冲突

- step、complete、restart 均校验 expected_revision，不匹配返回 409。
- 409 响应的 latest 包含完整状态，前端可直接用于恢复渲染。

### 5.5 保留答案

- restart 的 preserve_answers=true 时保留 channel/profile/tags 数据。

### 5.6 步骤自动推进

- POST /step 成功后 current_step 自动指向下一个 pending 步骤。
- 所有步骤完成后 status 自动变为 completed。

---

## 6. 前后端联调注意事项

### 6.1 鉴权

所有接口都要求携带 Bearer Token：

```
Authorization: Bearer <token>
```

收到 401 时前端应清除会话并回到登录页。

### 6.2 请求路径

```
GET  /api/v1/onboarding/state
POST /api/v1/onboarding/step
POST /api/v1/onboarding/complete
POST /api/v1/onboarding/restart
```

### 6.3 前端建议处理

- 登录/注册后立即调用 GET /state，根据 should_show 决定是否跳转 /onboarding。
- 成功时：直接将返回的 state 渲染到当前步骤。
- 遇到 409 冲突时调用 GET /state 获取最新状态并重新渲染。
- answer 字段按步骤类型传入，前端 adapter 负责字段映射。

### 6.4 数据库联调建议

- 确认 onboarding_state 表已存在且 alembic_version 已记录当前迁移。
- SQLite 环境注意单写锁场景。

### 6.5 当前实现范围

- 新用户注册时自动初始化 onboarding 记录
- 引导状态查询（含 should_show / legacy_without_state 判定）
- 单步提交/跳过（自动推进、revision 递增）
- 整体完成/跳过剩余步骤
- 引导重启/重置（含 revision 冲突检测、答案保留）
- 409 冲突响应含完整 latest 状态

---

## 7. 接口返回值字段说明

| 字段 | 说明 |
|------|------|
| should_show | 前端是否应展示引导界面（仅 GET /state） |
| reason | 判定原因（仅 GET /state） |
| guide_version | 当前引导版本 |
| revision | 当前引导修订版本号（乐观锁） |
| status | 当前状态：pending / in_progress / completed / skipped |
| current_step | 当前待处理步骤，全部完成时为 null |
| steps | 所有步骤状态集合（pending / completed / skipped） |
| channel | 渠道类回答（任意 JSON） |
| profile | 用户画像类回答（任意 JSON） |
| tags | 用户标签（任意 JSON） |

---

## 8. 结论

本次 onboarding 实施已完整实现"注册初始化 -> 状态查询 -> 单步推进 -> 整体完成/跳过 -> 历史账号重置"的首次引导全生命周期。后端提供稳定的 revision 乐观锁机制防止多端冲突，409 响应携带完整状态便于前端恢复。前端可基于这四个接口完成首次引导的完整交互流程。
