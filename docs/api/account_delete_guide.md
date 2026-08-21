# 账号注销接口对接说明（前端同学可直接使用）

## 1. 接口概览

- 接口地址：DELETE /api/v1/auth/account
- 作用：注销当前登录用户账号
- 适用场景：用户主动删除账号、清空账户并结束当前登录会话

---

## 2. 请求说明

### 2.1 请求方法

- Method: DELETE

### 2.2 请求路径

- /api/v1/auth/account

### 2.3 请求头

必须携带登录 Token：

```http
Authorization: Bearer <access_token>
```

### 2.4 请求体

当前接口无需请求体。

---

## 3. 鉴权规则

该接口要求用户已登录，并且 Token 必须有效。

### 3.1 认证要求

- 必须携带有效 Bearer Token
- Token 必须在服务端当前会话缓存中存在
- 用户必须处于活跃状态

### 3.2 认证失败场景

- 未登录：401 Unauthorized
- Token 过期或无效：401 Unauthorized
- 用户状态不活跃：400 Bad Request

---

## 4. 后端执行流程

后端注销流程分为主流程和弱依赖步骤。

### 4.1 主流程（必执行）

1. 识别当前登录用户
   - 从 Authorization 中解析当前登录用户身份

2. 查找该用户账户
   - 根据用户 ID 从数据库中查询用户记录
   - 若用户不存在，返回 404

3. 失效该用户所有旧 Token
   - 清理 Redis 中该用户的所有会话 Token
   - 这样其他设备上的登录态会立即失效

4. 删除与用户相关的业务数据
   - 清理该用户的知识库分区、文档、文档片段等相关记录
   - 避免留下孤儿数据或外键约束问题

5. 删除用户主记录
   - 从 users 表中删除当前账号

6. 返回成功结果
   - 返回注销成功消息

### 4.2 弱依赖步骤（失败不阻断主流程）

- 如果用户绑定了 Dify 知识库，后端会尝试删除对应知识库
- 如果 Dify 删除失败，后端会记录 warning 日志，但不会阻止账号注销继续完成

这意味着：
- 账号注销主体成功是优先级最高的
- 外部知识库资源清理是“弱依赖”步骤

---

## 5. 数据库清理说明

当前后端实现已经对以下常见用户相关数据进行清理：

- 知识库分区：kb_collections
- 文档：documents
- 文档片段：document_segments

此外，当前实现也会尝试清理以下与用户强相关的记录：

- quiz 会话相关数据：quiz_sessions、quiz_session_questions
- quiz 答题记录：quiz_answers
- tutor 会话：tutor_sessions
- 用户问题引用：user_question_refs
- 用户标签：question_tags
- 用户笔记：user_notes
- 培训计划：training_plans
- onboarding 状态：onboarding_states

### 5.1 quiz 相关清理说明

当用户注销账号时，以下与 quiz 相关的数据会一并清理：

- 用户发起的 quiz session
- quiz session 中的题目关联关系
- 用户的回答记录

这意味着用户的学习轨迹、答题记录、会话上下文将不再保留。

### 5.2 tutor 相关清理说明

tutor 相关数据主要包括：

- tutor_sessions
- 与 tutor 会话相关的题目/答案引用

注销账号后，用户在 tutor 场景下产生的会话记录和相关引用会被清理，后续无法继续恢复。

### 5.3 note 相关清理说明

note 相关数据主要包括：

- user_notes

注销账号后，用户的个人笔记内容会被删除，前端不应再尝试从本地或服务端恢复这部分内容。

### 5.4 说明

当前版本更偏向“账号主体删除 + 关联业务数据清理”，而不是完整的数据级联删除。

### 5.5 注意事项

- 如果后续数据库中还存在其他外键引用，可能需要继续补齐清理逻辑
- 前端在交互上应当将“注销账号”视为不可逆操作
- 由于注销后会删除学习记录、答题记录、笔记等内容，产品侧建议在 UI 中明确提示用户

---

## 6. 状态码

| 状态码 | 含义 | 说明 |
|---|---|---|
| 200 | 成功 | 账号注销成功 |
| 400 | 参数/状态错误 | 当前用户状态不活跃 |
| 401 | 未授权 | Token 无效、过期或未提供 |
| 404 | 用户不存在 | 通过当前登录态找到的用户在数据库中不存在 |
| 500 | 服务端错误 | 数据库删除失败或内部异常 |

---

## 7. 成功响应示例

### 7.1 成功

Status: 200 OK

```json
{
  "message": "账号已注销"
}
```

---

## 8. 失败响应示例

### 8.1 未登录 / Token 无效

Status: 401 Unauthorized

```json
{
  "detail": "Session expired"
}
```

### 8.2 用户状态不活跃

Status: 400 Bad Request

```json
{
  "detail": "Inactive user"
}
```

### 8.3 用户不存在

Status: 404 Not Found

```json
{
  "detail": "用户不存在"
}
```

### 8.4 服务端异常

Status: 500 Internal Server Error

```json
{
  "detail": "注销账号失败，请稍后重试"
}
```

---

## 9. 前端收到成功后的操作规范

当前端收到成功响应后，建议按以下顺序处理：

1. 清空本地 Token
   - 删除本地存储中的 access token / refresh token

2. 清空本地用户信息
   - 清空用户资料、登录状态、用户设置等缓存

3. 跳转到登录页或欢迎页
   - 避免用户在注销后仍然看到已登录态页面

4. 关闭当前会话相关弹窗
   - 如账户设置、个人中心、退出登录提示框

### 9.1 推荐提示文案

- “账号已注销，正在跳转到登录页”
- “注销成功，当前设备已退出登录”

---

## 10. 前端调用建议

### 10.1 推荐调用方式

```javascript
async function deleteAccount(accessToken) {
  const res = await fetch('/api/v1/auth/account', {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    }
  });

  if (!res.ok) {
    throw new Error('注销失败');
  }

  return res.json();
}
```

### 10.2 交互建议

- 注销前请做二次确认
- 这是不可逆操作
- 成功后必须清理本地登录状态

---

## 11. 当前实现结论

当前后端的账号注销接口已经具备以下能力：

- 识别当前登录用户
- 失效用户所有旧 Token
- 清理用户关联业务数据
- 删除用户主账号
- 对 Dify 资源删除失败采取弱依赖处理

如果后续需要更彻底的用户数据清理，可以继续扩展到更多关联表。