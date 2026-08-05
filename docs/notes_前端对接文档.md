# 笔记系统 Flutter 前端对接文档

> **后端版本**: v2.4 (2026-08-05)
> **适用范围**: Flutter 客户端 — 笔记模块 & 个人资料模块
> **前置阅读**: `docs/API.md` 第 13 章、第 1.14 节

---

## 目录

- [1. 概述](#1-概述)
- [2. Breaking Change 警告](#2-breaking-change-警告)
- [3. 接口变更汇总](#3-接口变更汇总)
- [4. KS-PILOT-0003 — 个人资料校验](#4-ks-pilot-0003--个人资料校验)
- [5. KS-PILOT-0004 — 笔记回收站](#5-ks-pilot-0004--笔记回收站)
- [6. KS-PILOT-0006 — 笔记附件](#6-ks-pilot-0006--笔记附件)
- [7. 数据模型变更](#7-数据模型变更)
- [8. 错误处理约定](#8-错误处理约定)
- [9. Flutter 迁移检查清单](#9-flutter-迁移检查清单)

---

## 1. 概述

本次后端合同冻结涉及三个 Issue，共新增/修改 **13 个 API 端点**，覆盖个人资料校验、笔记软删除与回收站、笔记附件上传下载三大模块。

| Issue | 模块 | 类型 | 影响范围 |
|---|---|---|---|
| KS-PILOT-0003 | 个人资料 | 字段校验加强 | 资料编辑页 |
| KS-PILOT-0004 | 笔记 | 软删除 + 回收站 + 恢复 | 笔记列表 / 删除操作 |
| KS-PILOT-0006 | 笔记 | 附件上传 / 下载 / 管理 | 编辑器图片 & 录音 |

---

## 2. Breaking Change 警告

> ⚠️ **DELETE /api/v1/notes/{note_id} 接口已变更。**

| 旧行为 | 新行为 |
|---|---|
| `DELETE /notes/{id}` 无 body，直接硬删除 | 必须携带 `{"expected_revision": N}` body，改为软删除 |
| 返回 `{"message": "笔记已删除"}` | 返回 `{"message": "笔记已移入回收站", "revision": N+1}` |
| 笔记立即消失 | 笔记进入回收站，7 天内可恢复 |

**不兼容影响**：所有未适配的 Flutter 客户端调用 DELETE 时将收到 **422 Unprocessable Entity**。

---

## 3. 接口变更汇总

### 3.1 新增端点

| 方法 | 路径 | Issue |
|---|---|---|
| `GET` | `/api/v1/notes/trash/items?page=1&limit=50` | 0004 回收站列表 |
| `POST` | `/api/v1/notes/{note_id}/restore` | 0004 恢复笔记 |
| `POST` | `/api/v1/notes/{note_id}/attachments` | 0006 上传附件 |
| `GET` | `/api/v1/notes/attachments/{attachment_id}` | 0006 下载附件 |
| `DELETE` | `/api/v1/notes/attachments/{attachment_id}` | 0006 删除附件 |
| `GET` | `/api/v1/notes/{note_id}/attachments` | 0006 列出附件 |

### 3.2 修改端点

| 方法 | 路径 | 变更内容 | Issue |
|---|---|---|---|
| `DELETE` | `/api/v1/notes/{note_id}` | ⚠️ 需要 `expected_revision` body；改为软删除 | 0004 |
| `PATCH` | `/api/v1/auth/users/me` | phone/gender 增加校验；错误返回 422/409 | 0003 |

### 3.3 行为变更（无接口签名变化）

| 影响 | 说明 |
|---|---|
| `GET /notes` | 默认排除已删除笔记（`deleted_at IS NOT NULL`） |
| `GET /notes/{id}` | 已删除笔记返回 404（除非 `?include_deleted=true`） |
| `PATCH /notes/{id}` | 已删除笔记无法更新，返回 409 |

---

## 4. KS-PILOT-0003 — 个人资料校验

### 4.1 变更说明

`PATCH /api/v1/auth/users/me` 新增以下字段校验：

| 字段 | 规则 | 清除方式 |
|---|---|---|
| `phone` | 非空必须是 11 位中国大陆手机号（`1` 开头纯数字） | 传 `""` |
| `gender` | 非空仅接受 `"男"` / `"女"` | 传 `""` |

### 4.2 请求示例

```json
// 正常
PATCH /api/v1/auth/users/me
{ "phone": "13800138000", "gender": "男" }

// 清除 (不公开)
{ "phone": "", "gender": "" }
```

### 4.3 错误处理

**422 — 字段校验失败**：
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
> 客户端可根据 `loc[-1]` 定位到具体字段（`"phone"` / `"gender"`），展示对应错误提示。

**409 — 手机号已被占用**：
```json
{ "detail": "该手机号已被其他账号绑定" }
```

### 4.4 Flutter 适配要点

1. 资料编辑页的 `phone` 输入框增加 11 位数字格式校验（客户端层面拦截）
2. `gender` 改为单选/下拉（`"男"` / `"女"` / `"不公开"`（清空）），不再允许自由文本
3. 提交前做本地校验（与服务端规则一致），减少 422 往返
4. 收到 409 时提示用户"手机号已被其他账号绑定"

---

## 5. KS-PILOT-0004 — 笔记回收站

### 5.1 核心流程

```
正常状态 ──DELETE──▶ 回收站 (7天) ──restore──▶ 正常状态
                         │
                   7天后自动物理删除
```

### 5.2 端点详情

#### 5.2.1 删除笔记（软删除）

```
DELETE /api/v1/notes/{note_id}
Content-Type: application/json

{ "expected_revision": 3 }
```

**响应** (200):
```json
{
  "message": "笔记已移入回收站",
  "revision": 4
}
```

> **关键**：删前必须从笔记对象中取当前 `revision` 值传递。删除成功后 `revision` 会递增 `1`。

#### 5.2.2 回收站列表

```
GET /api/v1/notes/trash/items?page=1&limit=50
Authorization: Bearer <token>
```

**响应** (200):
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

#### 5.2.3 恢复笔记

```
POST /api/v1/notes/{note_id}/restore
Content-Type: application/json

{ "expected_revision": 3 }
```

**响应** (200): 返回完整笔记对象（同 `GET /notes/{id}` 格式），`revision` 递增 `1`。

> ⚠️ `expected_revision` 应使用回收站列表中显示的 `revision` 值，而非删除前的值。

### 5.3 错误处理

| 状态码 | 场景 | 处理 |
|---|---|---|
| 409 | revision 冲突（笔记在删除/恢复前已被其他设备修改） | 拉取最新数据，更新本地 `revision`，提示用户重试 |
| 404 | 笔记不存在或不在回收站中 | 提示"笔记已被永久删除或不存在" |

### 5.4 Flutter 适配要点

1. **`Note` 数据模型必须持久化 `revision` 字段**（创建时=1，每次 PATCH/DELETE/restore 后更新为新值）
2. 删除操作从"弹出确认 → 调 DELETE → 从列表移除"改为：
   - 弹出确认 → 调 DELETE（带 `expected_revision`）→ 从列表移除（后端已自动过滤）
3. 新增回收站页面：
   - 调用 `GET /trash/items` 展示列表
   - 每条显示 `title`、`deleted_at`（可用相对时间如"3 天前"）
   - 点击"恢复"调 `POST /{id}/restore`（带回收站中的 `revision`）
   - **不要展示"剩余 X 天"倒计时**（后端负责清理，前端不应伪造）
4. 笔记列表、详情页不再展示已删除笔记（后端已过滤）
5. 更新笔记前检查 `revision` 冲突（已有 409 处理逻辑）

---

## 6. KS-PILOT-0006 — 笔记附件

### 6.1 核心流程

```
编辑器选文件 ──POST /attachments──▶ 获得 attachment_id + checksum
                                         │
                          写入 content_md: "![](attachment://xxx)"
                                         │
              PATCH /notes/{id} ──▶ 附件挂载到 note_revision
```

### 6.2 端点详情

#### 6.2.1 上传附件

```
POST /api/v1/notes/{note_id}/attachments
Content-Type: multipart/form-data

file: <binary>
```

**响应** (201):
```json
{
  "id": "att_3f8a7b2c",
  "note_id": "note_001",
  "media_type": "image",
  "mime_type": "image/png",
  "file_size": 245760,
  "checksum": "a1b2c3d4e5f67890...",
  "original_filename": "screenshot.png",
  "width": null,
  "height": null,
  "duration_seconds": null,
  "uploaded_at": "2025-01-01T15:00:00"
}
```

**限制**：

| 类型 | 单文件上限 | 单笔记上限 |
|---|---|---|
| 图片 (png/jpeg/gif/webp/svg) | 10 MB | 20 个 |
| 音频 (mp4/mpeg/ogg/wav/webm) | 20 MB | 20 个 |

#### 6.2.2 在 Markdown 中引用附件

Flutter 编辑器使用自定义协议 `attachment://` 引用附件：

```markdown
![图片描述](attachment://att_3f8a7b2c)
```

**客户端渲染时**：将 `attachment://att_3f8a7b2c` 替换为实际下载 URL：
```
GET /api/v1/notes/attachments/att_3f8a7b2c
Authorization: Bearer <token>
```

> ⚠️ **安全约束**：客户端不得将本地绝对路径（如 `/storage/emulated/0/...`）或任意公网 URL 写入 `content_md` 冒充可同步附件。后端不会处理这些引用，跨设备同步将丢失。

#### 6.2.3 下载/预览附件

```
GET /api/v1/notes/attachments/{attachment_id}
Authorization: Bearer <token>
```

响应为文件流，响应头：
```
Cache-Control: private, max-age=3600
Accept-Ranges: bytes
Content-Type: image/png
```

支持 `Range` 请求，音频可分段加载。

#### 6.2.4 删除附件

```
DELETE /api/v1/notes/attachments/{attachment_id}
Authorization: Bearer <token>
```

> 删除后客户端应同时从 `content_md` 中移除对应的 `attachment://xxx` 引用。

#### 6.2.5 列出笔记附件

```
GET /api/v1/notes/{note_id}/attachments
Authorization: Bearer <token>
```

### 6.3 离线占位策略（建议）

在编辑器保存前的流程：

1. 用户选择图片 → 创建本地临时 ID（如 `local_temp_xxx`）
2. 立即在编辑器中显示本地预览，`content_md` 中写入 `![](attachment://local_temp_xxx)`
3. 后台异步上传到 `POST /attachments`
4. 上传成功后获得 `attachment_id`，替换 `content_md` 中的本地临时 ID
5. 若上传失败，保留本地占位符，下次保存时重试

**去重优化**：相同 SHA-256 的文件重复上传不会占额外存储空间。客户端可缓存已上传文件的 checksum，避免重复上传。

### 6.4 Flutter 适配要点

1. **编辑器增加图片插入按钮**：从相册/相机选择 → 上传 → 插入 `attachment://` 链接
2. **编辑器增加录音按钮**：录制 → 上传 → 插入 `attachment://` 链接
3. **Markdown 渲染器**识别 `attachment://` 协议，替换为带 Token 的下载 URL
4. 图片预览使用 `Cache-Control` 响应头做客户端缓存（减少重复下载）
5. 音频播放使用 `Range` 请求实现拖拽进度条
6. **编辑器关闭/保存时清理孤儿附件**：收集当前 `content_md` 中的 `attachment://` 引用列表，与之前的列表对比，未被引用的附件可调 DELETE 删除

---

## 7. 数据模型变更

### 7.1 Note 模型

| 字段 | 类型 | 说明 | 变更类型 |
|---|---|---|---|
| `id` | String | 笔记 ID | 不变 |
| `revision` | int | **必须持久化**。创建=1，每次 PATCH/DELETE/restore 后更新 | 🔴 新要求 |
| `title` / `content_md` / `note_type` / `collection_id` | — | 不变 | 不变 |
| `deleted_at` | DateTime? | 普通列表不返回 | 新增（API 不暴露） |

> **客户端必须将 `revision` 持久化到本地数据库**。这是所有修改操作（PATCH/DELETE/restore）的必要参数。

### 7.2 NoteAttachment 模型（新增）

```dart
class NoteAttachment {
  final String id;
  final String noteId;
  final String mediaType;   // "image" | "audio"
  final String mimeType;    // "image/png", "audio/mp4", ...
  final int fileSize;
  final String checksum;    // SHA-256
  final String originalFilename;
  final int? width;
  final int? height;
  final int? durationSeconds;
  final DateTime? uploadedAt;
}
```

### 7.3 Profile 模型

| 字段 | 变更 |
|---|---|
| `phone` | 客户端输入框增加 11 位数字格式校验 |
| `gender` | 从自由文本改为单选（"男"/"女"/"不公开"（null）） |

---

## 8. 错误处理约定

### 8.1 通用约定

| 状态码 | 含义 | Flutter 处理 |
|---|---|---|
| 200 | 成功 | 正常更新 UI |
| 201 | 创建成功 | 正常 |
| 400 | 参数错误 | 展示 `detail` 消息 |
| 401 | 未登录 | 跳转登录页 |
| 404 | 资源不存在 | "笔记/附件不存在或已被删除" |
| 409 | 版本冲突 | 拉取最新 `revision`，提示用户刷新后重试 |
| 413 | 文件过大 | "文件超过大小限制" |
| 422 | 字段校验失败 | 解析 `detail` 数组，按 `loc[-1]` 定位字段展示提示 |

### 8.2 409 冲突处理流程

```
PATCH /notes/{id} → 409
  ↓
GET /notes/{id} 拉取最新数据（含最新 revision）
  ↓
合并用户修改 + 新 revision → 重新 PATCH
```

### 8.3 422 字段定位示例

```dart
// Flutter 解析示例
if (response.statusCode == 422) {
  final errors = jsonDecode(response.body)['detail'] as List;
  for (final err in errors) {
    final field = (err['loc'] as List).last; // "phone" or "gender"
    final message = err['msg'];
    // 在对应输入框显示错误
  }
}
```

---

## 9. Flutter 迁移检查清单

### 🔴 必须立即完成（否则功能不可用）

- [ ] `Note` 模型增加 `revision` 字段，并持久化到本地数据库
- [ ] `DELETE /notes/{id}` 调用改为携带 `{"expected_revision": revision}`
- [ ] 创建笔记后保存返回的 `revision` 值
- [ ] 更新笔记后保存返回的新 `revision` 值
- [ ] 删除成功后本地缓存状态更新（revision + 从列表移除）

### 🟡 尽快完成（新功能）

- [ ] 新增回收站页面：`GET /trash/items` + 列表渲染
- [ ] 回收站页面添加"恢复"按钮：`POST /{id}/restore` (带 revision)
- [ ] 笔记列表确认已排除已删除笔记（后端已处理，前端移除旧硬删逻辑即可）
- [ ] 资料编辑页 phone 输入增加格式校验
- [ ] 资料编辑页 gender 改为单选控件

### 🟢 后续迭代

- [ ] 编辑器增加图片插入 + 上传功能
- [ ] 编辑器增加录音 + 上传功能
- [ ] Markdown 渲染器支持 `attachment://` 协议
- [ ] 图片/音频预览（带 Range 请求支持）
- [ ] 附件上传有进度显示
- [ ] 去重优化（本地缓存 checksum 避免重复上传）
- [ ] 关闭编辑器时清理未使用的附件

---

> **文档版本**: v1.0 · **更新时间**: 2026-08-05 · **维护团队**: 知拾 (Zhishi) 后端组