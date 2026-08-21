# 新用户首次引导后端联调说明

> 发送对象：后端同学
>
> 状态：待后端确认并补齐契约
>
> 更新日期：2026-07-31

## 1. 结论与目标

已确认产品决策：**新账号首次登录是否进入新手引导，必须以后端保存的 onboarding 状态为准。** 前端不再以浏览器本地状态、环境变量或“注册成功”这一单一事件判断，也不会在每次登录时盲调重启接口。

当前线上 Web 的实际行为是：注册成功并拿到 Token 后直接进入工作区，不会出现新手引导。原因不是注册请求失败，而是正式环境的 Onboarding 客户端在缺少远端契约时被设计为 `blocked`，门禁会自动放行。

本说明的目标是让后端提供一套可查询、可提交、可完成、可重启且可处理多端冲突的正式契约，使前端能够安全实现：

1. 新账号首次登录自动进入引导。
2. 未完成账号从首个未处理步骤恢复。
3. 已完成、已跳过和历史账号正常进入工作区。
4. 后端支持历史账号显式重置正式引导状态，且不删除业务数据。
5. 多端修改不会静默覆盖进度或答案。

需要特别区分：当前 Web 设置页的“重新体验完整引导”是一次性会话重播，不修改账号正式 onboarding 状态，也不会重新触发首次登录门禁；后端 `restart` 则是正式账号状态重置。前端是否把现有设置页操作切换为 `restart`，需要产品单独确认，不能仅因接口存在而自动替换。

## 2. 已复现的问题

### 2.1 最小复现

前端以浏览器 mock 模拟以下成功链路：

```text
POST /api/v1/auth/register -> 200，响应含 access_token
GET  /api/v1/auth/users/me -> 200，新用户资料
```

结果：浏览器最终 URL 为 `/`，页面显示“你好，新用户”，没有跳转到 `/onboarding`；网络记录中没有任何 `/api/v1/onboarding/*` 请求。

### 2.2 当前前端链路

```text
注册成功
  -> AuthContext 保存 Token 并读取 /auth/users/me
  -> LoginPage 跳转原目标路径（默认 /）
  -> ProtectedRoute 放行
  -> OnboardingGate 读取 OnboardingClient
  -> 正式环境得到 mode = blocked
  -> 直接渲染工作区
```

对应代码证据：

- `src/features/auth/LoginPage.tsx`：注册响应含 `access_token` 时直接导航到默认工作区。
- `src/lib/auth/AuthContext.tsx`：注册后只保存 Token、读取当前用户并置为已登录。
- `src/lib/onboarding/client.ts`：只有 `development + VITE_ONBOARDING_LOCAL_ACCEPTANCE=true` 才创建本地引导客户端；其余环境返回 `blocked`。
- `src/components/onboarding/OnboardingGate.tsx`：只有本地客户端的 `not_started` 或 `in_progress` 才跳转 `/onboarding`；`blocked` 直接放行。

因此，前端需要一个可在鉴权完成后立即读取的正式状态接口，而不是仅靠注册接口或重启接口推断。

## 3. 现有后端接口及其边界

以下信息来自本次提供的后端说明，尚需以部署环境真实响应和 OpenAPI 为准：

```http
POST /api/v1/onboarding/restart
Authorization: Bearer <token>
```

请求要求 `expected_revision`、`mode = all` 和 `preserve_answers`。成功时返回引导状态；存在 `onboarding_already_in_progress` 与 `onboarding_revision_conflict` 两种 409 语义。

该接口对“用户主动重新开始引导”是必要的，但**不能单独承担首次登录门禁**，原因如下：

1. 前端首次进入不知道当前 `revision`，无法安全填写必填的 `expected_revision`。
2. 对每次登录调用 `restart` 会把已完成或进行中的账号回退到第一步，破坏进度。
3. 新账号若已由注册流程创建为 `in_progress`，再次调用会得到 `409 onboarding_already_in_progress`，它不是状态查询的替代品。
4. 当前只公开重启接口，前端没有正式方式读取状态、提交单步、跳过步骤或完成引导。
5. 409 示例中的 `latest` 只有部分字段，无法让前端恢复完整步骤和已填写答案。

## 4. 必须明确的生命周期规则

### 4.1 新账号

建议在创建用户的同一事务中初始化 onboarding 记录，初始值为：

```text
status       = in_progress
current_step = channel
revision     = 1
steps        = channel/upload/profile/tags/help 全部 pending
```

前端拿到 Token 后调用状态查询接口；若返回未完成状态，就跳转 `/onboarding`。注册接口是否附带 onboarding 状态均可，但不能替代状态查询，因为登录、刷新 Token 和跨设备恢复同样需要这一能力。

注册接口不返回 Token 的部署模式也必须成立：用户随后正常登录后，状态查询仍应得到相同的未完成记录。

### 4.2 历史账号

历史账号没有 onboarding 记录时，**默认进入工作区，不能被状态查询自动创建为新用户并强制拦截**。这是已确认的产品规则。

后端需要在状态查询中明确区分：

| 场景 | 前端期望 |
| --- | --- |
| 新注册账号，已初始化记录 | `should_show = true`，返回完整未完成状态 |
| 已完成或已跳过账号 | `should_show = false`，返回完整终态或可识别终态 |
| 历史账号，无记录 | `should_show = false`，标识为 `legacy_without_state` 或等价语义 |
| 历史账号主动发起正式状态重置 | `restart` 创建或重置记录后，返回 `should_show = true` 的完整状态 |

推荐由后端在注册时初始化记录，并在状态查询响应中显式提供 `should_show`。若不新增该字段，也必须提供等价且稳定的规则，保证前端不会把“无记录”误当成“新账号待引导”。

### 4.3 用户主动重启与当前重播的边界

`POST /restart` 只能由明确的用户操作调用，不能挂在普通登录、刷新页面或路由门禁上。

当前产品实现中，老账号“重新体验完整引导”仍使用独立会话重播，不调用 `restart`。若产品后续确认要把它改为“重置账号正式引导状态”，前端才会接入 `restart`，并需要在界面中明确说明该操作会重置引导进度、不会删除业务数据。

调用前，前端先读取状态并携带当前 `revision`。若账号没有历史记录，后端需要明确创建时的 revision 规则，例如是否接受 `expected_revision = 0`；不要要求前端猜测该值。

`preserve_answers = true` 时至少应保留渠道、画像和标签。上传步骤是否保留关联文档、仅保留步骤状态，还是一律回到待处理，需要后端明确。

## 5. 建议补齐的 API 契约

以下为前端所需的建议契约，不代表当前已发布接口。后端可调整路径或字段，但需一次性在 OpenAPI 和真实响应中固定。

### 5.1 查询状态

```http
GET /api/v1/onboarding/state
Authorization: Bearer <token>
```

建议成功响应：

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
    "tags": [],
    "created_at": "2026-07-31T00:00:00Z",
    "updated_at": "2026-07-31T00:00:00Z"
  }
}
```

历史无记录账号可返回：

```json
{
  "should_show": false,
  "reason": "legacy_without_state",
  "state": null
}
```

关键要求：前端需要完整 `revision`、`current_step`、全部 `steps` 和可回填答案；不能仅返回 `status`。

### 5.2 提交或跳过单个步骤

```http
POST /api/v1/onboarding/step
Authorization: Bearer <token>
```

建议请求体：

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

`action` 至少支持 `completed` 和 `skipped`，以覆盖每一步的“稍后再做”。每次成功写入应返回完整最新状态，并且 `revision` 只递增一次。

### 5.3 完成或跳过剩余步骤

```http
POST /api/v1/onboarding/complete
Authorization: Bearer <token>
```

建议支持两种明确动作：

```json
{ "expected_revision": 5, "action": "completed" }
```

```json
{ "expected_revision": 5, "action": "skip_remaining" }
```

前者仅在所有步骤已处理后将整体状态设为 `completed`；后者用于用户确认“跳过整个新手引导”，将剩余步骤设为 `skipped`，整体状态设为 `skipped`。两者都应返回完整终态。

### 5.4 重启

保留现有接口：

```http
POST /api/v1/onboarding/restart
Authorization: Bearer <token>
```

建议成功和 409 响应都提供可直接恢复的完整状态。若保留 `latest` 字段，请让它包含完整 `state`，或者确保前端可以立即通过 `GET /state` 获得相同内容。

## 6. 步骤、状态与答案的字段对齐

当前 Web 本地流程与后端说明存在下列差异。前端会通过领域 adapter 转换，但后端需确认最终的正式语义。

| 语义 | 当前 Web 本地模型 | 后端说明 | 需要确认 |
| --- | --- | --- | --- |
| 第二步 ID | `knowledge` | `upload` | 正式接口以 `upload` 为准，前端 adapter 映射 `knowledge -> upload` |
| 单步完成状态 | `completed` | `done` | 建议统一为 `completed`；若保留 `done`，在契约中固定映射 |
| 初始总体状态 | `not_started` | `pending` 或 `in_progress` | 建议新账号初始化后直接使用 `in_progress` |
| 当前步骤字段 | `currentStep` | `current_step` | 后端使用 snake_case，前端 adapter 转换 |
| 步骤状态结构 | `{ status, updatedAt? }` | 字符串状态 | 后端可保持字符串，前端 adapter 补齐内部结构 |
| 渠道答案 | `channel`、`channelRemark` | `channel_answer` | 需明确 JSON schema 和字段命名 |
| 画像答案 | `identity`、`stage`、`field`、`purposes`、`functionPreferences`、`usageFrequency` | `profile_answer` | 需明确 JSON schema 和数组字段命名 |
| 标签 | `string[]` | `tags` | 建议固定为字符串数组，空值返回 `[]` 而非 `null` |
| 帮助步骤 | `viewedArticleSlugs` | 未说明答案字段 | 请确认仅记录步骤完成，还是需要持久化文章标识 |
| 上传步骤 | 文件元数据仅用于本地验收 | `upload` 步骤，无答案字段 | 请确认应关联真实知识库 `document_id`，还是仅在成功上传后标记完成 |

上传文件不能通过 onboarding 接口再次上传。建议继续使用现有知识库上传流程；当文件已被后端接受并得到稳定 `document_id` 后，再由步骤接口写入该步骤的完成状态或关联信息。

## 7. 错误、并发与鉴权要求

### 7.1 鉴权

所有 onboarding 接口必须要求 Bearer Token。前端收到 401 时会清除会话并回到登录页；接口不要以 200 + 业务错误文本伪装鉴权失败。

### 7.2 Revision 冲突

当 `expected_revision` 不匹配时返回：

```text
409 onboarding_revision_conflict
```

前端行为是读取完整最新状态、提示用户状态已在其他设备更新，并重新渲染。为此，冲突响应的 `latest` 必须足够恢复页面，或保证 `GET /state` 在该响应后立即可用。

### 7.3 已在引导中

当 `restart` 遇到 `onboarding_already_in_progress` 时，前端不应再重置；应展示当前进度并提供继续入口。该响应同样需要完整状态，或者可通过 `GET /state` 立即恢复。

### 7.4 参数校验

422 响应请明确到字段级别，尤其是：`expected_revision`、步骤 ID、动作值、渠道枚举、标签数组、画像字段和答案 JSON。前端会把可定位的字段错误展示在对应步骤，不应只收到无法操作的泛化错误。

## 8. 后端验收清单

后端交付前建议逐项验证：

1. 新注册账号在注册事务结束后已有 `in_progress` 记录，第一步为 `channel`。
2. 使用新账号 Token 查询状态能得到完整未完成状态；前端可据此跳转引导。
3. 历史无记录账号查询状态不会被强制进入引导。
4. 历史账号调用 `restart` 后进入引导，且不删除知识库、笔记、学习记录等业务数据；前端是否将现有会话重播改为该操作另行确认。
5. 每一次步骤完成、跳过、整体完成和重启都正确递增 revision 并返回完整状态。
6. 两个设备使用相同旧 revision 提交时，后到请求收到 409，且能取回最新完整状态。
7. `preserve_answers = true` 真实保留已约定的渠道、画像和标签；`false` 的清理范围有明确文档。
8. 所有接口在 OpenAPI 中有请求体、成功响应、401、409、422 的 schema 和示例。
9. 使用真实环境做一次完整链路：注册 -> 查询状态 -> 五步处理/跳过 -> 完成 -> 重新登录放行 -> 设置页重启 -> 继续引导。

## 9. 需要后端确认的事项

1. 注册接口是否已在同一事务内创建 onboarding 记录？若否，计划由哪个接口和时机创建？
2. `GET /state` 对历史无记录账号返回什么，如何保证不误触发首次引导？
3. 无记录时 `restart.expected_revision` 的合法值是什么？是否允许 `0`，还是由服务端忽略？
4. 正式步骤状态使用 `done` 还是 `completed`？是否支持 `skipped`？
5. `channel_answer`、`profile_answer`、`tags`、帮助步骤和上传步骤的正式 JSON schema 分别是什么？
6. 上传步骤与现有知识库上传的关系是什么，是否需要持久化 `document_id`？
7. 409 中是否提供完整 `latest`，还是前端统一改用 `GET /state` 恢复？
8. `guide_version` 升级后，已完成用户是否需要重新进入新版引导；若需要，后端如何表达迁移规则？
9. 后端 `restart` 是否只作为预留的正式状态重置能力，还是期望替换当前 Web 的一次性会话重播？后者需要产品确认后再接入。

## 10. 前端接入前置条件

在以下内容确认并部署前，前端不会把当前本地验收客户端替换为正式 API：

1. `GET /api/v1/onboarding/state` 的真实响应和 OpenAPI。
2. 单步提交、跳过剩余步骤和完成语义。
3. `restart` 的创建规则、完整 409 恢复信息和答案保留规则。
4. 步骤 ID、状态枚举和答案 JSON schema 的最终定义。

接口到位后，前端会先更新 `docs/4.API接口文档.md`，再新增 `src/lib/api` 的领域封装和 DTO adapter，并补充“注册/登录 -> 状态读取 -> 引导门禁”的集成测试。
