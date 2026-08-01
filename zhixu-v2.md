# zhixu-v2 融合方案：项目落地执行计划

> **版本**：v1.0  
> **日期**：2026-07-15  
> **基线文档**：  
> - `后端能力补齐清单.md`（2026-07-04 审核的 21 项后端缺口）  
> - `SYSTEM_ARCHITECTURE_BRIEF.md`（TCN 引擎层职责边界，2026-07-13 v1.1）  
> - `zhishi-master/backend` 当前实际代码（2026-07-15 审计）  
> 
> **合作模式**：TCN 引擎层（算法团队）封装全部知识追踪算法为 REST API（port 8001），我方软件层负责用户系统、对话编排、知识库、画像存储和前端展示。

---

## 目录

- [一、当前状态基线](#一当前状态基线)
- [二、TCN 引擎层接口清单](#二tcn-引擎层接口清单)
- [三、软件层补齐计划](#三软件层补齐计划)
  - [迭代 0：TCN 对接基础设施](#迭代-0tcn-对接基础设施)
  - [迭代 1：P0 个人端最小闭环](#迭代-1p0-个人端最小闭环)
  - [迭代 2：P1 知识追踪与页面入口](#迭代-2p1-知识追踪与页面入口)
  - [迭代 3：P2 推理模式 + 前端可视化](#迭代-3p2-推理模式--前端可视化)
- [四、数据模型设计](#四数据模型设计)
- [五、API 路由规划](#五api-路由规划)
- [六、迭代依赖与时间规划](#六迭代依赖与时间规划)
- [七、技术选型与架构](#七技术选型与架构)

---

## 一、当前状态基线

### 1.1 zhishi-master/backend 现有模块（已就绪，不在补齐范围）

| 领域 | 已有接口 | 状态 |
|------|---------|------|
| 账号认证 | 注册/登录/密码重置/邮箱验证/Token刷新/注销/资料更新 | ✅ 完成 |
| 用户套餐 | Plan CRUD/我的套餐/升级/套餐列表 | ✅ 完成 |
| 基础聊天 | POST /chat（SSE流式+非流式）/ 会话列表/历史/删除 | ✅ 完成 |
| 知识库管理 | 分区CRUD/上传/文档列表/索引进度/删除/预览/分段/翻页 | ✅ 完成 |
| 首页建议 | GET /dashboard/suggestions（基于KB文档LLM生成） | ✅ 完成 |
| KT 基础算法 | correct/evaluate/learning-path/prerequisites/skill-graph（前端传states） | ✅ 完成 |
| 刷题系统 | 题目/quiz会话/答题流程 | ✅ 完成 |
| 辅导 | tutor 会话创建/苏格拉底式对话/历史 | ✅ 完成 |
| 学习分析 | stats/tag-stats/learning-report | ✅ 完成 |
| 学习报告 | generate/list/latest/detail | ✅ 完成 |
| 针对训练 | start/resume/active-session/tutor | ✅ 完成 |
| 笔记 | 模型+CRUD已有，路由未注册 | ⚠️ 部分 |
| 健康检查 | GET /health | ✅ 完成 |

### 1.2 后端能力补齐清单 — 原 21 项缺口对照

| 编号 | 能力项 | 优先级 | 原清单要求 | TCN合作后变化 |
|------|--------|--------|-----------|-------------|
| 2.1 | 三层产品模式与权益 | P0 | 自建模式字段+开关+降级 | **保持** — 软件层负责，TCN不管 |
| 2.2 | Chat模式/知识库范围/引用 | P0 | 扩展Chat请求/响应 | **保持** — 软件层负责编排 |
| 2.3 | 个人知识库检索/画像资料选择 | P0 | 自建检索接口+资料标记 | **保持** — 软件层RAG服务 |
| 2.4 | 音频上传与转写 | P0 | 自建音频处理 | **保持** — 软件层调用Whisper |
| 2.5 | 画像构建任务 | P0 | 自建画像构建流程 | **保持** — 软件层Profile Service |
| 2.6 | 个人画像图谱 | P0 | 自建画像节点体系 | **保持** — 软件层Profile Service |
| 2.7 | 普通模式先修提示 | P0 | 自建"识别知识点→先修提示" | **改为依赖TCN gaps接口** |
| 2.8 | 本地优先与一次性云端迁移 | P0 | 自建迁移系统 | **简化为云端同步**（架构文档建议） |
| 3.1 | 用户持久化认知状态 | P1 | 自建认知状态存储 | **改为调用TCN predict+report** |
| 3.2 | 带用户状态的知识追踪图谱 | P1 | 自建图谱叠加 | **改为TCN report叠加到skill-graph** |
| 3.3 | 先修断层定位 | P1 | 自建断层诊断 | **改为TCN gaps + LLM解释** |
| 3.4 | 学习路径任务生命周期 | P1 | 自建路径CRUD+状态机 | **保持** — 软件层负责 |
| 3.5 | 错题归因拆解 | P1 | 自建归因接口 | **改为TCN gaps + LLM解释** |
| 3.6 | LVR实时监控与学习历史 | P1 | 自建LVR追踪 | **改为TCN lvr_alert + 学习事件落库** |
| 3.7 | 笔记系统 | P1 | 补全笔记路由+搜索+AI生成 | **保持** — 软件层负责 |
| 3.8 | 提醒系统 | P1 | 自建提醒CRUD | **保持** — 软件层负责 |
| 3.9 | 通知中心 | P1 | 自建通知系统 | **保持** — 软件层负责 |
| 3.10 | 顶栏统一搜索 | P1 | 自建跨域搜索 | **保持** — 软件层负责 |
| P2 | 推理模式 | P2 | 自建风险审查/推理链验证 | **改为TCN vulnerabilities+gaps + LLM编排** |

> **关键变化**：3.1、3.2、3.3、3.5、3.6、P2 共 6 项从"自建"变为"调用TCN+LLM编排"，大幅降低软件层算法开发成本。

---

## 二、TCN 引擎层接口清单

### 2.1 已提供的接口（可直接对接）

| 接口 | 端点 | 用途 |
|------|------|------|
| 更新用户知识状态 | `POST /v1/user/predict` | 用户答题后更新掌握度，返回 node_mastery + lvr + vs |
| 获取用户认知画像摘要 | `GET /v1/user/profile/{user_hash}` | 返回 global_lvr、total_steps、已追踪节点数 |
| 获取用户完整掌握报告 | `GET /v1/user/report/{user_hash}` | 所有节点掌握度(0–1) + 先修父节点状态 |
| 健康检查 | `GET /health` | 引擎状态、节点数、图版本 |

### 2.2 需要推动TCN新增的接口（我方需排期时提出需求）

| 编号 | 接口名 | 建议端点 | 返回内容 | 优先级 | 依赖的补齐项 |
|------|-------|---------|---------|--------|------------|
| T1 | 用户状态结构化摘要 | `GET /v1/user/summary/{user_hash}` | 掌握节点数、LVR均值、最活跃节点、最薄弱领域 | **P0** | I1-11先修提示、所有模式LLM System Prompt注入 |
| T2 | 先修断层查询 | `GET /v1/user/gaps/{user_hash}` | 掌握度低+先修违反的节点列表，按严重度排序 | **P1** | I1-11先修提示、I2-3断层定位、I2-5错题归因 |
| T3 | 认知脆弱点查询 | `GET /v1/user/vulnerabilities/{user_hash}` | LVR贡献高但掌握度偏高的伪掌握节点列表 | **P1** | I3-1推理模式、I2-6 LVR预警 |
| T4 | LVR预警状态 | `GET /v1/user/lvr_alert/{user_hash}` | 当前global_lvr + 预警级别(正常/注意/警告) + 违反最严重前5个先修边 | **P1** | I2-6 LVR监控、前端预警Banner |
| T5 | 学习历史持久化 | TCN内部DB落库 | 掌握度变化时间序列 | **P2** | I2-7 成长曲线 |

### 2.3 TCN 调用规则

1. **每次用户交互必须调用 predict**，不调用则 TCN 无法更新掌握状态
2. **拉取上下文时序**：先调 summary+gaps+vulnerabilities → 组装 System Prompt → 再发起 LLM 请求
3. **三种模式对 TCN 透明**：三种模式（普通/知识追踪/推理）对 TCN 接口调用完全相同，TCN 约束模式由服务端启动时统一配置为 dynamic（CABR），软件层无需传模式参数
4. **新用户冷启动**：TCN 支持新用户直接调用 predict，初始掌握度默认 0.5
5. **user_hash 生成**：由软件层生成并维护（如 `sha256(uid + secret_salt)`），确保跨设备一致

---

## 三、软件层补齐计划

### 迭代 0：TCN 对接基础设施

> **目标**：打通与 TCN 引擎层的通信链路，为所有后续功能提供数据基础。  
> **工期**：2-3 天  
> **无 TCN 新增接口依赖**（仅使用已提供的 predict/profile/report）

| 编号 | 任务 | 涉及文件 | 说明 |
|------|------|---------|------|
| S1 | TCN 客户端封装 | `app/services/tcn_client.py`（新建） | 封装 predict/profile/report 调用，user_hash 生成规则（sha256），超时 5s 重试 2 次，优雅降级 |
| S2 | User 模型扩展 | `app/models/models.py` | 新增字段：`user_hash VARCHAR(64) UNIQUE`、`product_mode VARCHAR(30) DEFAULT 'basic_normal'`、`mode_features JSON`（画像/追踪/推理能力开关） |
| S3 | TCN 健康探活 | `app/core/tcn_health.py`（新建） | 启动事件中检测 TCN `/health` 端点，不可达时记录 WARNING 并降级 |
| S4 | 数据库迁移脚本 | `app/core/migrations/` | User 表新增字段的 Alembic 迁移 |
| S5 | 用户注册时生成 user_hash | `app/services/auth_service.py` | 注册时自动生成 `user_hash = sha256(f"{user_id}:{SECRET_KEY}")` |

### 迭代 1：P0 个人端最小闭环

> **目标**：完成三层产品模式、Chat增强、知识库检索、音频、画像系统，让个人用户可完整使用基础功能。  
> **工期**：2-3 周  
> **TCN 依赖**：T1（summary）— 需并行推动

#### 1.1 三层产品模式与权益

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I1-1 | 模式查询接口 | `GET /api/v1/user/mode` | 返回当前模式+可用模式列表+不可用原因 |
| I1-2 | 模式切换接口 | `POST /api/v1/user/mode` | 验证权限后切换 product_mode，返回新模式+能力开关 |
| I1-3 | Chat/各接口返回模式信息 | 修改 `ChatResponse` 等 | 增加 `product_mode`、`downgrade_reason`、`upgrade_hint` 字段 |

**数据模型**：
```json
// User.mode_features 字段
{
  "profile_graph": true,      // 画像图谱
  "knowledge_tracking": false, // 知识追踪
  "reasoning_review": false    // 推理审查
}
```

#### 1.2 Chat 模式与引用增强

| 编号 | 任务 | 说明 |
|------|------|------|
| I1-4 | ChatRequest 扩展 | 新增字段：`mode`（basic/profile_confirm/knowledge_tracking/reasoning）、`kb_scope`（{collection_ids, tag_ids, doc_ids}）、`profile_enabled` |
| I1-5 | Chat SSE 响应扩展 | 已有 `citations/reasoning_content/tool_name`，新增：`mode_used`、`capabilities_used`（{profile, kb, kt, reasoning}）、`downgrade_reason` |
| I1-6 | Chat 降级逻辑 | 权益不足或 TCN/Profile 不可用时，返回降级原因并自动切换到可用模式 |

#### 1.3 个人知识库检索与画像资料选择

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I1-7 | 知识库检索 | `POST /api/v1/kb/search` | 支持 query（关键词+语义）、filters（collection_id/doc_type/tag），返回 doc+segment+match_reason+similarity+is_citable |
| I1-8 | 画像资料标记 | `PATCH /api/v1/kb/documents/{doc_id}/profile` | 标记/取消文档参与画像构建 |
| I1-9 | 画像资料列表 | `GET /api/v1/kb/profile-documents` | 列出已标记为画像构建资料的文档 |

#### 1.4 音频上传与转写

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I1-10 | 音频上传 | 扩展 `POST /api/v1/kb/upload` | 支持 mp3/wav/m4a，max_size=100MB |
| I1-11 | 转写状态查询 | `GET /api/v1/kb/documents/{doc_id}/transcript` | status: transcribing→transcribed→error，返回 transcribed_text+segments |
| I1-12 | 异步转写任务 | `app/services/transcription_service.py` | 后台调用 Whisper API，写回 documents 表 |

#### 1.5 个人画像系统

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I1-13 | Profile 存储模型 | 新建 `user_profiles` 表 | uid, learning_style, communication_style, preferred_explanation, known_interests, onboarding_completed, profile_confidence, last_updated |
| I1-14 | 画像查询 | `GET /api/v1/profile` | 返回当前 Profile |
| I1-15 | 画像构建任务创建 | `POST /api/v1/profile/build` | 绑定资料范围 → 后台调用 LLM 生成确认问题 → 返回 task_id |
| I1-16 | 画像构建任务状态 | `GET /api/v1/profile/tasks/{task_id}` | 返回 status + 待确认问题列表 |
| I1-17 | 画像确认回答 | `POST /api/v1/profile/tasks/{task_id}/confirm` | 保存用户对确认问题的回答/否认/修正 → 重新计算 Profile |
| I1-18 | 画像图谱 | `GET /api/v1/profile/graph` | 返回画像节点+边+可信度+依据来源+确认时间和状态 |
| I1-19 | 画像节点反馈 | `POST /api/v1/profile/nodes/{node_id}/feedback` | 提交节点不准确反馈，触发重新确认 |

#### 1.6 普通模式先修提示

| 编号 | 任务 | 说明 |
|------|------|------|
| I1-20 | Chat 先修提示编排 | Chat 普通模式下，对话前调用 TCN `summary`+`gaps` → LLM 转化为"你可能需要先了解X"的非阻断自然语言提示，不作为硬拦截 |

#### 1.7 换机数据同步

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I1-21 | 数据导出 | `POST /api/v1/sync/export` | 导出加密包到对象存储，返回 download_url |
| I1-22 | 数据恢复 | `POST /api/v1/sync/restore` | 从云端恢复 Profile + KB 索引 + 文件引用（TCN 数据自动还原） |
| I1-23 | 云端副本清除 | `DELETE /api/v1/sync/cloud-backup` | 下载确认后清除云端副本 |

### 迭代 2：P1 知识追踪与页面入口

> **目标**：补全知识追踪的持久化状态、学习路径管理、笔记/提醒/通知/搜索等页面入口功能。  
> **工期**：2-3 周  
> **TCN 依赖**：T2（gaps）、T3（vulnerabilities）、T4（lvr_alert）— 需推动新增

#### 2.1 认知状态与图谱

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I2-1 | 认知状态查询 | `GET /api/v1/user/cognitive-state` | 调用 TCN `report`，包装为用户认知状态快照 |
| I2-2 | KT 图谱增强 | 增强 `GET /api/v1/kt/skill-graph` | 叠加 TCN `report` 的用户掌握度、可信度、最近更新时间到每个节点 |
| I2-3 | 认知状态保存 | 每次 `POST /api/v1/user/predict` 后 | 异步保存 TCN 返回的 `node_mastery` 到本地快照表 |

#### 2.2 先修断层定位

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I2-4 | 断层诊断 | `POST /api/v1/kt/diagnose-gaps` | 接收题目/错误回答 → 调用 TCN `predict` 模拟 → 调用 TCN `gaps` 定位根因 → LLM 组织诊断报告（断层节点+原因+追溯路径+修复建议） |

#### 2.3 学习路径生命周期

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I2-5 | 学习路径模型 | 新建 `learning_paths` + `learning_path_steps` 表 | path_id, user_id, title, status, created_at; step_id, path_id, node_id, order, status, recommendation_reason, completed_at |
| I2-6 | 创建学习路径 | `POST /api/v1/learning-path` | 基于 TCN `gaps` + LLM 生成学习路径 |
| I2-7 | 路径列表 | `GET /api/v1/learning-path` | 用户所有学习路径 |
| I2-8 | 步骤状态更新 | `PATCH /api/v1/learning-path/{id}/steps/{step_id}` | 标记 start/complete/skip/postpone |
| I2-9 | 路径重排 | `POST /api/v1/learning-path/{id}/reorder` | 手动或自动（调用 TCN `report` 最新掌握度）重排 |
| I2-10 | 路径历史 | `GET /api/v1/learning-path/history` | 已完成的学习路径记录 |

#### 2.4 错题归因拆解

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I2-11 | 错题归因 | `POST /api/v1/kt/error-attribution` | 接收错题+用户回答 → 调用 TCN `gaps` 定位 → LLM 生成"为什么会错/从哪断掉/下一步建议" |

#### 2.5 LVR 实时监控与学习历史

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I2-12 | LVR 趋势 | `GET /api/v1/user/lvr-trend` | 调用 TCN `lvr_alert` + 本地历史快照 → 返回 LVR 变化曲线数据（时间序列） |
| I2-13 | 学习事件记录 | 新建 `learning_events` 表 | 每次 `predict` 调用后异步落库：user_id, node_id, mastery_before, mastery_after, lvr, timestamp, trigger_source |
| I2-14 | 学习活动流 | `GET /api/v1/user/activity` | 分页返回学习事件流，供前端时间线展示 |

#### 2.6 笔记系统

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I2-15 | 笔记路由注册 | `POST/GET/PATCH/DELETE /api/v1/notes` | 已有 `UserNote` 模型，注册到 router.py |
| I2-16 | 笔记搜索 | `GET /api/v1/notes/search` | 全文搜索，按标题+内容匹配 |
| I2-17 | AI 生成笔记 | `POST /api/v1/notes/from-chat` | 从 AI 回答/资料片段/学习事件 LLM 生成笔记 |

#### 2.7 提醒系统

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I2-18 | 提醒模型 | 新建 `reminders` 表 | id, user_id, title, description, rrule, next_trigger, status, linked_type+linked_id, created_at/updated_at |
| I2-19 | 提醒 CRUD | `POST/GET/PATCH/DELETE /api/v1/reminders` | 支持重复规则(RRULE)、完成、延后、关闭 |
| I2-20 | 关联能力 | `linked_type` + `linked_id` | 提醒可关联资料/知识节点/学习路径/笔记 |

#### 2.8 通知中心

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I2-21 | 通知模型 | 新建 `notifications` 表 | id, user_id, type, title, content, is_read, linked_type+linked_id, created_at |
| I2-22 | 通知列表 | `GET /api/v1/notifications` | 分页+分类(type)+未读筛选 |
| I2-23 | 单条已读 | `PATCH /api/v1/notifications/{id}/read` | — |
| I2-24 | 全部已读 | `PATCH /api/v1/notifications/read-all` | — |
| I2-25 | 未读数量 | `GET /api/v1/notifications/unread-count` | 返回未读总数 |
| I2-26 | 通知触发 | 各业务模块写入 | KB索引完成、转写完成、画像构建完成、提醒到期时创建通知 |

#### 2.9 统一搜索

| 编号 | 任务 | 接口 | 说明 |
|------|------|------|------|
| I2-27 | 统一搜索 | `GET /api/v1/search` | query + type 过滤（kb_doc/kb_segment/note/tag/knowledge_node），返回类型+跳转地址+高亮摘要 |

### 迭代 3：P2 推理模式 + 前端可视化

> **目标**：完成 Dynamic-ε/CABR 驱动的推理模式，前端知识图谱可视化。  
> **工期**：1-2 周  
> **TCN 依赖**：T1/T2/T3/T4 全部就绪

#### 3.1 推理模式 System Prompt 编排

| 编号 | 任务 | 说明 |
|------|------|------|
| I3-1 | 推理专用 System Prompt | Chat 推理模式下，调用 TCN `summary`+`vulnerabilities`+`gaps`+`lvr_alert` → 组装推理专用 Prompt（含风险节点、脆弱点、违反边）→ LLM 逐步校验+每步说明"为什么需要先掌握X" |
| I3-2 | 高置信风险识别 | TCN `vulnerabilities` 返回的伪掌握节点 → LLM 在对话中主动预警："你在X节点掌握度虽高0.81，但逻辑一致性存在风险" |
| I3-3 | 多步推理链验证 | LLM 逐步拆解用户解题过程，每步调 TCN `predict` 模拟校验 |
| I3-4 | 跨域推理降级 | 图中无先修关系时，LLM 自动降级为"相关性引导"而非硬拦截 |

#### 3.2 前端知识图谱可视化

| 编号 | 任务 | 说明 |
|------|------|------|
| I3-5 | 节点掌握度可视化 | 颜色按掌握度渐变（0→红，0.5→黄，1→绿），数据源 TCN `report` |
| I3-6 | 节点可信度圆圈 | 边框颜色编码 confidence 字段，百分比数字叠加 |
| I3-7 | LVR 预警 Banner | 顶部三级颜色（绿/黄/红），数据源 TCN `lvr_alert`，超过阈值时触发 LLM 干预 |
| I3-8 | 成长曲线折线图 | X轴时间，Y轴平均掌握度，数据源 `learning_events` 表 + TCN 历史 |
| I3-9 | 断层边高亮 | 图谱上高亮显示 gaps 返回的断层边，点击"建议先学X" |

---

## 四、数据模型设计

### 4.1 User 模型扩展

```sql
-- 在现有 users 表新增字段
ALTER TABLE users ADD COLUMN user_hash VARCHAR(64) UNIQUE;
ALTER TABLE users ADD COLUMN product_mode VARCHAR(30) DEFAULT 'basic_normal';
ALTER TABLE users ADD COLUMN mode_features JSON DEFAULT '{"profile_graph":true,"knowledge_tracking":false,"reasoning_review":false}';
```

### 4.2 新增表

```sql
-- 认知状态快照（每次 predict 后异步更新）
CREATE TABLE cognitive_snapshots (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    node_id VARCHAR(100) NOT NULL,
    mastery DECIMAL(5,4) NOT NULL,
    confidence DECIMAL(5,4),
    lvr DECIMAL(5,4),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, node_id)
);

-- 学习事件
CREATE TABLE learning_events (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    node_id VARCHAR(100),
    mastery_before DECIMAL(5,4),
    mastery_after DECIMAL(5,4),
    lvr DECIMAL(5,4),
    event_type VARCHAR(30),  -- predict/correct/incorrect
    trigger_source VARCHAR(50), -- chat/quiz/tutor
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_learning_events_user_time ON learning_events(user_id, created_at);

-- 个人画像
CREATE TABLE user_profiles (
    uid INTEGER PRIMARY KEY REFERENCES users(id),
    learning_style VARCHAR(50),
    communication_style VARCHAR(50),
    preferred_explanation VARCHAR(50),
    known_interests JSON,       -- ["数学","物理"]
    onboarding_completed BOOLEAN DEFAULT FALSE,
    profile_confidence DECIMAL(5,4) DEFAULT 0,
    dialogue_history_summary TEXT,
    last_updated TIMESTAMP DEFAULT NOW()
);

-- 画像构建任务
CREATE TABLE profile_tasks (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(30) DEFAULT 'pending', -- pending/generating_questions/awaiting_confirmation/completed/error
    document_scope JSON,        -- 绑定的资料范围
    questions JSON,             -- LLM生成的确认问题列表
    answers JSON,               -- 用户回答
    result JSON,                -- 构建结果
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 画像节点
CREATE TABLE profile_nodes (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    node_name VARCHAR(100) NOT NULL,
    node_type VARCHAR(30),      -- trait/interest/habit/preference
    confidence DECIMAL(5,4),
    source_doc_ids JSON,        -- 依据资料ID列表
    confirmed_by_user BOOLEAN DEFAULT FALSE,
    last_confirmed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_profile_nodes_user ON profile_nodes(user_id);

-- 学习路径
CREATE TABLE learning_paths (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'active', -- active/completed/abandoned
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE learning_path_steps (
    id VARCHAR(36) PRIMARY KEY,
    path_id VARCHAR(36) NOT NULL REFERENCES learning_paths(id) ON DELETE CASCADE,
    node_id VARCHAR(100) NOT NULL,
    sort_order INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'pending', -- pending/in_progress/completed/skipped/postponed
    recommendation_reason TEXT,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_learning_path_steps_path ON learning_path_steps(path_id);

-- 提醒
CREATE TABLE reminders (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    rrule VARCHAR(500),         -- 重复规则(RRULE格式)
    next_trigger TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active', -- active/completed/snoozed/closed
    linked_type VARCHAR(30),    -- document/knowledge_node/learning_path/note
    linked_id VARCHAR(36),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_reminders_user_next ON reminders(user_id, next_trigger);

-- 通知
CREATE TABLE notifications (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    type VARCHAR(30) NOT NULL,  -- kb_indexed/transcription_complete/profile_built/reminder_due/system
    title VARCHAR(255) NOT NULL,
    content TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    linked_type VARCHAR(30),
    linked_id VARCHAR(36),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_notifications_user_read ON notifications(user_id, is_read, created_at);
```

### 4.3 文档表扩展

```sql
-- 补充音频转写和画像标记字段
ALTER TABLE documents ADD COLUMN file_type VARCHAR(20);  -- text/pdf/audio/image
ALTER TABLE documents ADD COLUMN transcription_status VARCHAR(30); -- none/transcribing/transcribed/error
ALTER TABLE documents ADD COLUMN transcribed_text TEXT;
ALTER TABLE documents ADD COLUMN used_for_profile BOOLEAN DEFAULT FALSE;
```

---

## 五、API 路由规划

### 5.1 最终路由汇总

```python
# app/api/v1/router.py 最终版本
api_router.include_router(auth.router,        prefix="/auth",        tags=["账号认证"])
api_router.include_router(plan.router,        prefix="/plan",        tags=["用户套餐"])
api_router.include_router(chat.router,        prefix="/chat",        tags=["智能聊天"])
api_router.include_router(kt.router,          prefix="/kt",          tags=["知识追踪"])
api_router.include_router(kb.router,          prefix="/kb",          tags=["知识库管理"])
api_router.include_router(questions.router,   prefix="/questions",   tags=["题目"])
api_router.include_router(quiz.router,        prefix="/quiz",        tags=["刷题"])
api_router.include_router(tutor.router,       prefix="/tutor",       tags=["辅导"])
api_router.include_router(dashboard.router,   prefix="/dashboard",   tags=["首页建议"])
api_router.include_router(analytics.router,   prefix="/analytics",   tags=["学习分析"])
api_router.include_router(reports.router,     prefix="/reports",     tags=["学习报告"])
api_router.include_router(training.router,    prefix="/training",    tags=["针对训练"])
# ─── 迭代1新增 ───
api_router.include_router(profile.router,     prefix="/profile",     tags=["个人画像"])       # I1-14~I1-19
api_router.include_router(sync.router,        prefix="/sync",         tags=["数据同步"])       # I1-21~I1-23
# ─── 迭代2新增 ───
api_router.include_router(notes.router,       prefix="/notes",        tags=["笔记系统"])       # I2-15~I2-17
api_router.include_router(reminders.router,   prefix="/reminders",    tags=["提醒系统"])       # I2-19
api_router.include_router(notifications.router, prefix="/notifications", tags=["通知中心"])   # I2-22~I2-25
api_router.include_router(search.router,      prefix="/search",       tags=["统一搜索"])       # I2-27
api_router.include_router(learning_path.router, prefix="/learning-path", tags=["学习路径"])    # I2-6~I2-10
```

### 5.2 关键接口速查表

| 方法 | 路径 | 迭代 | 说明 |
|------|------|------|------|
| GET | `/api/v1/user/mode` | 1 | 查询当前产品模式+可用模式 |
| POST | `/api/v1/user/mode` | 1 | 切换产品模式 |
| POST | `/api/v1/chat` | 1 | 增强：mode/kb_scope/profile_enabled |
| POST | `/api/v1/kb/search` | 1 | 知识库检索 |
| PATCH | `/api/v1/kb/documents/{id}/profile` | 1 | 标记文档参与画像构建 |
| POST | `/api/v1/kb/upload` | 1 | 扩展：支持音频文件 |
| GET | `/api/v1/kb/documents/{id}/transcript` | 1 | 转写状态与结果 |
| GET | `/api/v1/profile` | 1 | 查询个人画像 |
| POST | `/api/v1/profile/build` | 1 | 创建画像构建任务 |
| GET | `/api/v1/profile/tasks/{id}` | 1 | 画像任务状态+确认问题 |
| POST | `/api/v1/profile/tasks/{id}/confirm` | 1 | 提交画像确认回答 |
| GET | `/api/v1/profile/graph` | 1 | 画像图谱 |
| POST | `/api/v1/profile/nodes/{id}/feedback` | 1 | 画像节点反馈 |
| POST | `/api/v1/sync/export` | 1 | 数据导出 |
| POST | `/api/v1/sync/restore` | 1 | 数据恢复 |
| GET | `/api/v1/user/cognitive-state` | 2 | 认知状态快照（TCN report） |
| POST | `/api/v1/kt/diagnose-gaps` | 2 | 先修断层诊断 |
| POST | `/api/v1/kt/error-attribution` | 2 | 错题归因拆解 |
| GET | `/api/v1/user/lvr-trend` | 2 | LVR 变化趋势 |
| GET | `/api/v1/user/activity` | 2 | 学习活动流 |
| POST | `/api/v1/learning-path` | 2 | 创建学习路径 |
| PATCH | `/api/v1/learning-path/{id}/steps/{step_id}` | 2 | 步骤状态更新 |
| POST/GET/PATCH/DELETE | `/api/v1/notes` | 2 | 笔记 CRUD |
| POST/GET/PATCH/DELETE | `/api/v1/reminders` | 2 | 提醒 CRUD |
| GET/PATCH | `/api/v1/notifications` | 2 | 通知中心 |
| GET | `/api/v1/search` | 2 | 统一搜索 |

---

## 六、迭代依赖与时间规划

### 6.1 甘特图（简化）

```
Week    1  2  3  4  5  6  7  8  9  10 11
──────────────────────────────────────────
迭代0   ██░                              TCN对接基础设施
TCN侧   ████████████████░░░░            并行新增4个接口
迭代1      ██████████████░░              个人端最小闭环
迭代2                     ██████████████  KT+页面入口
迭代3                                ████ 推理+可视化
──────────────────────────────────────────
```

### 6.2 关键依赖链

```
迭代0（S1-S5）
  ├── S1/S3 → 所有 TCN 相关功能
  └── S2 → 迭代1 I1-1~I1-3（三层模式）

TCN 侧（与我方迭代0并行）
  └── T1(summary) → 迭代1 I1-20（先修提示）、迭代3 I3-1（推理Prompt）
  └── T2(gaps) → 迭代1 I1-20、迭代2 I2-4/I2-11
  └── T3(vulnerabilities) → 迭代2 I2-6、迭代3 I3-2
  └── T4(lvr_alert) → 迭代2 I2-12、迭代3 I3-7

迭代1
  ├── I1-1~I1-3（三层模式）← 无TCN依赖，可先行
  ├── I1-4~I1-6（Chat增强）← 无TCN依赖
  ├── I1-7~I1-9（KB检索）← 无TCN依赖
  ├── I1-10~I1-12（音频）← 无TCN依赖
  ├── I1-13~I1-19（画像）← 无TCN依赖
  ├── I1-20（先修提示）← 依赖 TCN T1/T2
  └── I1-21~I1-23（同步）← 无TCN依赖

迭代2
  ├── I2-1~I2-3（认知状态）← 依赖TCN已有接口
  ├── I2-4（断层）← 依赖 TCN T2
  ├── I2-5~I2-10（学习路径）← 依赖 TCN T2
  ├── I2-11（错题归因）← 依赖 TCN T2
  ├── I2-12~I2-14（LVR监控）← 依赖 TCN T4
  ├── I2-15~I2-17（笔记）← 无TCN依赖
  ├── I2-18~I2-20（提醒）← 无TCN依赖
  ├── I2-21~I2-26（通知）← 无TCN依赖
  └── I2-27（搜索）← 无TCN依赖

迭代3
  └── 全部依赖 TCN T1/T2/T3/T4
```

### 6.3 总工期预估

| 阶段 | 工期 | 可并行 |
|------|------|--------|
| 迭代 0（TCN 对接基础） | 2-3 天 | 与 TCN 侧并行 |
| TCN 侧（4 个新接口 + 历史持久化） | 2-3 周 | 与迭代 0/1 并行 |
| 迭代 1（P0 个人端最小闭环） | 2-3 周 | 大部分无 TCN 依赖 |
| 迭代 2（P1 KT + 页面入口） | 2-3 周 | 笔记/提醒/通知/搜索 无 TCN 依赖 |
| 迭代 3（P2 推理 + 可视化） | 1-2 周 | 需 TCN 全部就绪 |
| **总计** | **7-11 周** | |

---

## 七、技术选型与架构

### 7.1 整体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                     zhishi-master/backend (FastAPI)                    │
│                                                                       │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ 对话引擎    │  │ 个人画像服务  │  │ 知识库服务    │  │ TCN 客户端   │ │
│  │ (LLM API)  │  │ (Profile Svc)│  │ (RAG+向量DB)  │  │ (port 8001) │ │
│  └─────┬─────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
│        │               │                 │                  │        │
│        └───────────────┴─────────────────┴──────────────────┘        │
│                                  │                                    │
│                          PostgreSQL + ChromaDB                        │
└──────────────────────────────────┼───────────────────────────────────┘
                                   │
                           ┌───────▼────────┐
                           │   TCN 引擎层    │
                           │   (port 8001)  │
                           │   LEKT推理      │
                           │   LVR/CABR     │
                           │   UserMask存储  │
                           └───┬───┬────────┘
                               │   │
                     ┌─────────▼┐ ┌▼─────────┐
                     │  Redis   │ │ PostgreSQL│
                     │（热存储） │ │（冷存储） │
                     └──────────┘ └──────────┘
```

### 7.2 技术栈

| 组件 | 当前 | 建议 |
|------|------|------|
| 后端框架 | FastAPI | 保持 |
| 数据库 | PostgreSQL | **保持**（TCN 架构也建议 PostgreSQL） |
| 向量存储 | ChromaDB（本地） | **保持**（已有 local RAG 模式） |
| LLM | tina 封装的多模型 | 保持，通过 System Prompt 编排 |
| 音频转写 | — | **新增** Whisper API |
| 文件存储 | 本地 storage/ + OSS | 保持 |
| 前端 | React (zhishi-web) | 保持 |

### 7.3 与 TCN 的交互时序（标准对话流程）

```
用户发送消息
    │
    ▼
软件层 Chat API 收到请求
    │
    ├─1─→ TCN GET /v1/user/summary/{user_hash}     ← 获取知识状态摘要
    ├─2─→ TCN GET /v1/user/gaps/{user_hash}         ← 获取先修断层
    ├─3─→ TCN GET /v1/user/vulnerabilities/{user_hash} ← 获取认知脆弱点
    ├─4─→ TCN GET /v1/user/lvr_alert/{user_hash}    ← 获取LVR预警状态
    ├─5─→ Profile Service 查询用户画像
    ├─6─→ KB RAG 检索相关文档片段
    │
    ├─7─→ 组装 System Prompt ─→ 调用 LLM
    │
    ├─8─→ 返回 SSE 流式响应（含 mode/capabilities/citations/downgrade）
    │
    └─9─→ 异步调用 TCN POST /v1/user/predict        ← 根据用户回答更新掌握状态
```

---

## 附录 A：与原后端能力补齐清单的映射

| 原清单编号 | 本方案对应 | 变化说明 |
|-----------|-----------|---------|
| 2.1 三层产品模式 | I1-1~I1-3 + S2 | 保持自建 |
| 2.2 Chat模式/引用 | I1-4~I1-6 | 保持自建，增加mode/kb_scope |
| 2.3 KB检索/画像资料 | I1-7~I1-9 | 保持自建 |
| 2.4 音频上传转写 | I1-10~I1-12 | 保持自建 |
| 2.5 画像构建任务 | I1-13~I1-19 | 保持自建 |
| 2.6 个人画像图谱 | I1-18~I1-19 | 保持自建 |
| 2.7 先修提示 | I1-20 | **改为依赖 TCN T1/T2 + LLM 编排** |
| 2.8 换机迁移 | I1-21~I1-23 | **简化为云端同步** |
| 3.1 持久化认知状态 | I2-1~I2-3 | **改为调用 TCN predict+report** |
| 3.2 带状态的KT图谱 | I2-2 | **改为 TCN report 叠加到 skill-graph** |
| 3.3 断层定位 | I2-4 | **改为 TCN gaps + LLM 解释** |
| 3.4 学习路径生命周期 | I2-5~I2-10 | 保持自建 |
| 3.5 错题归因 | I2-11 | **改为 TCN gaps + LLM 解释** |
| 3.6 LVR监控历史 | I2-12~I2-14 | **改为 TCN lvr_alert + 学习事件落库** |
| 3.7 笔记系统 | I2-15~I2-17 | 保持自建（补路由+AI生成） |
| 3.8 提醒系统 | I2-18~I2-20 | 保持自建 |
| 3.9 通知中心 | I2-21~I2-26 | 保持自建 |
| 3.10 统一搜索 | I2-27 | 保持自建 |
| P2 推理模式 | I3-1~I3-4 | **改为 TCN vulnerabilities+gaps+lvr_alert + LLM 编排** |

## 附录 B：文件结构变更

```
zhishi-master/backend/
├── app/
│   ├── api/v1/
│   │   ├── router.py          # [修改] 新增路由注册
│   │   ├── profile.py         # [新建] 个人画像
│   │   ├── notes.py           # [新建] 笔记系统
│   │   ├── reminders.py       # [新建] 提醒系统
│   │   ├── notifications.py   # [新建] 通知中心
│   │   ├── search.py          # [新建] 统一搜索
│   │   ├── learning_path.py   # [新建] 学习路径
│   │   └── sync.py            # [新建] 数据同步
│   ├── models/
│   │   ├── models.py          # [修改] User 扩展 user_hash/product_mode/mode_features
│   │   ├── profile.py         # [新建] UserProfile/ProfileTask/ProfileNode
│   │   ├── note.py            # [已有] UserNote
│   │   ├── reminder.py        # [新建] Reminder
│   │   ├── notification.py    # [新建] Notification
│   │   ├── learning_path.py   # [新建] LearningPath/LearningPathStep
│   │   └── cognitive.py       # [新建] CognitiveSnapshot/LearningEvent
│   ├── schemas/
│   │   ├── schemas.py         # [修改] ChatRequest/ChatResponse 扩展
│   │   ├── profile.py         # [新建]
│   │   ├── reminder.py        # [新建]
│   │   ├── notification.py    # [新建]
│   │   ├── search.py          # [新建]
│   │   └── learning_path.py   # [新建]
│   ├── crud/
│   │   ├── note.py            # [已有]
│   │   ├── profile.py         # [新建]
│   │   ├── reminder.py        # [新建]
│   │   ├── notification.py    # [新建]
│   │   └── learning_path.py   # [新建]
│   ├── services/
│   │   ├── tcn_client.py      # [新建] TCN 引擎层客户端
│   │   ├── profile_service.py # [新建] 画像构建与管理
│   │   ├── transcription_service.py # [新建] 音频转写
│   │   ├── reminder_service.py     # [新建] 提醒到期检测
│   │   └── notification_service.py # [新建] 通知生成与推送
│   └── core/
│       └── tcn_health.py      # [新建] TCN 健康检查
```

---

*本文档随开发进度持续更新。迭代 0 可立即启动实施。*