# 知序 v1 前端逐步实现计划

> **给执行代理：** 按任务逐项执行本计划，使用复选框（`- [ ]`）追踪进度。

**目标：** 按 `docs/zhishi-v1.md` 的 v1 学习教练闭环，基于当前 Vite + React + TypeScript 实现，逐步完成前端侧的知识库分区、分区对话、引用来源、自动出题、刷题、答错讲解、掌握度图谱和笔记真实化。

**执行状态（2026-07-08）：** 已在当前工作区按阶段提交 任务 1-8；任务 9 作为体验/错误态审查完成；任务 10 进入文档回写与全量验证。本计划保留原始清单 作为审计轨迹，具体已提交范围以 Git 提交记录为准。

**架构：** 继续使用现有工作台骨架 `AppShell`、`Sidebar`、`Topbar`、`RightPanel`。普通请求全部收敛到 `src/lib/api` 的领域封装，SSE 走 `apiStream`，页面只消费领域 hook / 适配后的前端模型。`src/data` 只保留 demo、默认空状态和开发兜底，不作为真实业务数据源。

**技术栈：** Vite 7, React 19, TypeScript 5.9, React Router 6, Tailwind CSS token, Radix/shadcn 风格组件, lucide-react, Vitest.

## 全局约束

- 只做 Web 前端相关任务；后端、数据库、Dify、机构端、学校端不纳入本计划实现范围。
- 新 API 先更新 `docs/4.API接口文档.md`，再更新 `src/lib/api`。
- 页面不得直接写裸 `fetch`；普通请求走 `apiRequest`，流式请求走 `apiStream` 或领域封装。
- 鉴权状态归 `src/lib/auth`；`UIContext` 只处理布局 UI 状态。
- 新页面同步 `src/routes/index.tsx`、`src/data/nav.ts`、`src/components/layout/Topbar.tsx`。
- 创建、删除、移动或重命名 `src/` 或 `tests/` 文件时，同步更新 `docs/6.文件树与目录结构.md`。
- UI 保持当前工作台风格，不做营销页式 Hero；优先使用 `bg-bg`、`bg-surface`、`text-ink-primary`、`border-line-soft`、`text-primary` 等现有 token。
- 图标优先使用 `lucide-react`，图标按钮必须有 `aria-label` 或 `title`。
- 类型导入使用 `import type`；路径别名使用 `@/*`。
- 验证优先级：API 客户端改动跑 `npm run test`；UI/页面改动跑 `npm run lint`，必要时跑 `npm run build`；路由改动跑 `npm run build`。

---

## 0. 当前事实

### 0.1 v1 计划中的目标能力

`docs/zhishi-v1.md` 将 v1 定位为“用户上传学习资料后，系统能自动出题、让他刷题、答错了有人教”的学习教练闭环。前端相关目标包括：

- 知识库分区：学习区、生活区、笔记区。
- 上传资料时选择分区，知识库页按分区筛选。
- 聊天页选择分区，对话只检索当前分区。
- AI 回复展示结构化引用来源。
- 对学习区文档生成题目。
- 新增 `/practice` 刷题页。
- 答错后展示解析，并提供 “我不会，让 Tina 教教我” 的流式讲解面板。
- 知识图谱展示真实学习掌握度。
- 笔记页改为真实 CRUD，聊天回答可保存为笔记。

### 0.2 当前前端已有能力

- `ChatPage` 已调用 `sendChatStream()` / `sendChat()`，支持会话列表、历史会话、删除会话和课堂笔记保存。
- `ChatMessage` 只支持 `refs?: string[]`，还不是结构化引用。
- `ChatRequest` 目前只有 `content`、`session_id`、`stream`、预留 `note_id`、预留 `context`，没有 `mode` / `category_id`。
- `ChatStreamChunk` 目前只有 `session_id`、`role`、`content`、`reasoning_content`、`tool_name`，没有引用 payload。
- `KnowledgeBasePage` 已调用 `listDocuments()`、`getKbConfig()`、`getDocumentContent()`、`deleteDocument()`，但只有文件名本地过滤，没有分区。
- `UploadPage` 已调用 `getKbConfig()`、`uploadDocument(file)`、`getDocumentStatus()`，但上传 FormData 只包含 `file`，没有 `category_id`。
- `KnowledgeGraphPage` 已调用 `getSkillGraph()`、`getSkillStates()`、`correctState()`，可作为掌握度图谱增强基础。
- `NotesPage`、`NoteEditorPage` 仍使用 `src/lib/demo/store` 的本地 demo 数据。
- `createNote()` 只覆盖课堂笔记保存到 `/api/v1/notes`，且在 demo store 开启时会本地兜底；没有 list/update/delete notes API 封装。
- 目前没有 `PracticePage`、`/practice` 路由、questions API 封装或题库类型。

### 0.3 与长期文档的差异

- `docs/4.API接口文档.md` 目前没有 `kb/categories`、`questions/*`、`chat mode/category_id`、结构化 citation、笔记 list/update/delete 等 v1 契约。
- `docs/前端功能补齐清单.md` 的旧最小闭环更偏“画像构建”；`docs/zhishi-v1.md` 的新闭环更偏“资料 -> 出题 -> 刷题 -> 讲解”。本计划按 v1 执行，但保留个人画像/图谱作为学习掌握度展示的承接面。

## 1. 先澄清的歧义

以下问题需要和产品/后端对齐。为避免计划停摆，每项都给出前端默认口径；如果用户确认不同口径，实施前先更新本计划。

| 歧义 | 需要确认的问题 | 默认口径 |
| --- | --- | --- |
| v1 文档里的 `✅` | 是“目标态已设计完成”，还是“当前代码/后端已完成”？ | 视为目标态，不视为当前实现事实。 |
| API 真相源 | `zhishi-v1.md` 新端点是否已经在后端存在？还是先由前端补契约？ | 先更新 `docs/4.API接口文档.md` 为前端目标契约，再用封装和测试锁定请求形状。 |
| 分区模型 | `学习区/生活区/笔记区` 是固定内置，还是用户可自由创建？ | 三个内置分区为默认项，允许用户新增；删除内置分区前端先禁用。 |
| 未分区资料 | 老文档或上传未选分区时如何显示？ | 前端展示“未分区”，上传默认选“学习区”，知识库可筛“全部/未分区”。 |
| 独立 AI 知识库 | “每个分区有独立 AI 知识库” 是 `category_id` 过滤，还是独立 `dataset_id`？ | 前端只依赖 `category_id`；如后端返回 `dataset_id`，仅作为说明信息展示。 |
| Chat 参数 | `/api/v1/chat` 的 `mode` 值和 `category_id` 字段名是否确定？ | `mode: "qa" | "learning" | "classroom_note" | "verify"`；`category_id: string | null`。 |
| 引用来源 | 引用是随 SSE 增量返回，还是最终消息一次性返回？ | 支持两种：`ChatStreamChunk.citations` 可追加/覆盖，非流式 `ChatResponse.citations` 一次性返回。 |
| 引用预览 | 点击引用打开哪个原文？ | 使用现有 `GET /api/v1/kb/documents/{doc_id}/content` 预览；若有 `chunk_id`，前端先滚动/高亮片段。 |
| 题型 | v1 是否只做选择题？ | v1 前端只做单选题，选项 A/B/C/D；多选、填空、主观题留后续。 |
| 生成题目入口 | 是对单文档生成，还是对整个学习区生成？ | 第一版支持单文档“生成题目”，Practice 页支持按分区拉题。 |
| 去重反馈 | 后端去重后前端如何提示？ | 生成结果返回 `created_count`、`duplicate_count`，前端明确展示新增和已存在数量。 |
| 答题判分 | 前端是否本地判分？ | 不本地判分，提交 `/questions/{id}/answer` 后使用后端结果展示。 |
| “我不会”讲解 | 是一次性讲解，还是可追问对话？ | 第一版为同一题内的 SSE 讲解线程，支持继续追问但仍挂在当前题上下文。 |
| 图谱掌握度 | mastery 来源是答题记录还是 KT states？ | 第一版使用 `/api/v1/kt/states` + `/api/v1/kt/skill-graph`，后端后续把答题记录汇入 states。 |
| 笔记 CRUD | v1 是否要完整编辑器真实落库？ | v1 做 list/create/update/delete/search；高级标签筛选和版本历史不做。 |
| 付费 gating | 自动出题/刷题是否受套餐限制？ | 前端先展示免费可用；若后端返回 403/配额错误，用统一错误态和升级入口承接。 |

## 2. 需求与设计对齐

### 2.1 推荐产品口径

v1 前端主线按下面的用户路径落地：

```text
登录
-> 上传学习资料并选择“学习区”
-> 知识库页按“学习区”看到文档
-> 对文档生成题目
-> 刷题页按“学习区”练习
-> 答错后看解析和原文引用
-> 需要时打开 Tina 讲解面板
-> 回到聊天页选择“学习区”追问
-> AI 回复展示引用来源
-> 有价值回答保存为笔记
-> 图谱页看到掌握度变化
```

### 2.2 推荐信息架构

- `知识库`：管理资料、分区筛选、文档预览、删除、生成题目。
- `上传资料`：选择资料、选择分区、查看上传/索引状态。
- `AI 对话`：选择当前任务、选择当前分区、查看引用来源、保存课堂笔记。
- `刷题`：新增主导航入口，展示分区题库、答题反馈、讲解面板。
- `知识图谱`：展示 KT 图谱和掌握度，支持分区过滤。
- `笔记`：真实列表、搜索、新建、编辑、删除；聊天保存结果进入笔记。

### 2.3 推荐视觉与交互口径

- 分区选择用 `Select` 或 `SegmentedTabs`，不要做大面积装饰卡片。
- Chat 顶部保留任务 chip，同时新增紧凑的分区选择器；右侧面板显示“正在对话的知识库：学习区”。
- 引用来源用折叠区：按钮文案 `引用来源 (N)`；展开后显示文档名、相似度、片段、预览按钮。
- Practice 页采用工作台布局：顶部分区/状态筛选，中间题目卡，右侧显示进度、错题、当前资料来源。
- ExplainPanel 用 `Dialog` 或 `Sheet`；移动端优先底部抽屉，桌面端右侧面板。
- 图谱节点颜色含义：已掌握绿色、薄弱红色、未学灰色；同时保留百分比文本，避免只靠颜色表达。

## 3. 文件结构计划

### 3.1 API 与类型

- 修改： `docs/4.API接口文档.md`
  增补 v1 前端目标契约：KB categories、questions、chat `mode/category_id/citations`、notes CRUD、KT states 的 mastery 展示字段。
- 修改： `src/lib/api/types.ts`
  增加 `KbCategory`、`ChatCitation`、`Question`、`QuestionOption`、`AnswerQuestionResponse`、`ExplainChunk`、`NoteListResponse` 等 DTO。
- 修改： `src/lib/api/kb.ts`
  扩展分区 API、上传/文档列表的 `category_id` 参数。
- 修改： `src/lib/api/chat.ts`
  扩展 chat 请求/响应类型消费；保持 `apiStream`。
- 新增： `src/lib/api/questions.ts`
  题目生成、题目列表、提交答案、流式讲解。
- 修改： `src/lib/api/notes.ts`
  从“只创建课堂笔记”扩展到 list/create/update/delete。
- 修改： `src/lib/api/adapters.ts`
  增加 category、citation、question、note 的 DTO 到前端模型转换。
- 测试： `tests/unit/lib/api/endpoints.test.ts`
  覆盖新增端点路径、method、query/body。
- 测试： `tests/unit/lib/api/adapters.test.ts`
  覆盖新增适配器。

### 3.2 Knowledge Base / Upload

- 修改： `src/features/knowledge-base/KnowledgeBasePage.tsx`
  增加分区 Tab/Select、文档分区展示、生成题目入口。
- 修改： `src/features/knowledge-base/UploadPage.tsx`
  增加上传分区选择，FormData 写入 `category_id`。
- 新增： `src/features/knowledge-base/hooks/useKbCategories.ts`
  统一加载分区、默认分区、创建分区。
- 修改： `src/components/blocks/DocRow.tsx`
  增加文档分区、生成题目、生成状态展示。

### 3.3 Chat

- 修改： `src/features/chat/ChatPage.tsx`
  增加分区选择；发送时传 `mode` 与 `category_id`；引用预览；保存笔记保持现有体验。
- 修改： `src/features/chat/hooks/useChat.ts`
  收敛与 `ChatPage` 重复的发送、流式、历史加载逻辑；页面优先复用 hook。
- 修改： `src/features/chat/lib/stream.ts`
  支持 `citations` 流式累积/覆盖。
- 修改： `src/components/blocks/ChatMessage.tsx`
  从 `refs: string[]` 升级为结构化引用展示。

### 3.4 Practice

- 新增： `src/features/practice/PracticePage.tsx`
  刷题主页面。
- 新增： `src/features/practice/components/QuestionCard.tsx`
  单题展示、选项、判题反馈。
- 新增： `src/features/practice/components/ExplainPanel.tsx`
  “我不会”流式讲解和追问。
- 新增： `src/features/practice/hooks/usePracticeSession.ts`
  题目加载、当前题、答题提交、进度状态。
- 新增： `src/features/practice/lib/question.ts`
  纯函数：选项排序、正确率、下一题、反馈状态。
- 修改： `src/routes/index.tsx`
  注册 `/practice`。
- 修改： `src/data/nav.ts`
  新增“刷题”导航。
- 修改： `src/components/layout/Topbar.tsx`
  新增 `/practice` 标题。
- 测试： `tests/unit/features/practice/question.test.ts`
- 测试： `tests/features/practice/PracticePage.test.tsx`

### 3.5 Graph / Notes

- 修改： `src/features/knowledge-graph/KnowledgeGraphPage.tsx`
  增加分区过滤和 mastery 状态文案。
- 修改： `src/features/notes/NotesPage.tsx`
  从 demo store 切到 notes API，保留 demo fallback 作为开发模式。
- 修改： `src/features/notes/NoteEditorPage.tsx`
  编辑、保存、删除走 notes API；失败时保留重试。
- 修改： `src/features/notes/hooks/useNoteEditor.ts`
  从 `updateDemoNote` 迁移到 `updateNote`，开发模式再 fallback。

## 4. 任务 1: 契约基线与默认分区模型

**文件：**

- 修改： `docs/4.API接口文档.md`
- 修改： `src/lib/api/types.ts`
- 修改： `src/lib/api/kb.ts`
- 修改： `src/lib/api/adapters.ts`
- 修改： `tests/unit/lib/api/endpoints.test.ts`
- 修改： `tests/unit/lib/api/adapters.test.ts`

**接口：**

- 产出： `KbCategory`
- 产出： `listKbCategories(): Promise<KbCategory[]>`
- 产出： `createKbCategory(payload: { name: string; type?: "learning" | "life" | "note" | "custom" }): Promise<KbCategory>`
- 产出： `deleteKbCategory(id: string): Promise<MessageResponse>`
- 产出： `uploadDocument(file: File, options?: { category_id?: string | null }): Promise<KbUploadResponse>`
- 产出： `listDocuments(params?: { page?: number; limit?: number; category_id?: string | null }): Promise<KbDocumentList>`

**步骤：**

- [ ] 在 `docs/4.API接口文档.md` 增补 KB 分区接口契约：`GET /api/v1/kb/categories`、`POST /api/v1/kb/categories`、`DELETE /api/v1/kb/categories/{id}`。
- [ ] 在 `docs/4.API接口文档.md` 更新 `POST /api/v1/kb/upload`，声明可选 `category_id` FormData 字段。
- [ ] 在 `docs/4.API接口文档.md` 更新 `GET /api/v1/kb/documents`，声明可选 `category_id` query。
- [ ] 在 `src/lib/api/types.ts` 增加 `KbCategory`，并给 `KbDocument`、`KbUploadResponse` 增加可选 `category_id` / `category_name`。
- [ ] 在 `src/lib/api/kb.ts` 增加分区 API，并扩展 `uploadDocument()`、`listDocuments()` 参数。
- [ ] 在 `src/lib/api/adapters.ts` 让 `mapKbDocument()` 输出前端 `KnowledgeDoc.category`。
- [ ] 更新 `tests/unit/lib/api/endpoints.test.ts`，断言 categories 路径、上传 FormData 包含 `category_id`、文档列表 query 正确。
- [ ] 更新 `tests/unit/lib/api/adapters.test.ts`，断言文档分区字段被保留。
- [ ] 运行 `npm run test -- tests/unit/lib/api/endpoints.test.ts tests/unit/lib/api/adapters.test.ts`，预期 PASS。
- [ ] 运行 `npm run build`，预期 PASS。

## 5. 任务 2: 知识库分区 UI 与上传分区

**文件：**

- 新增： `src/features/knowledge-base/hooks/useKbCategories.ts`
- 修改： `src/features/knowledge-base/KnowledgeBasePage.tsx`
- 修改： `src/features/knowledge-base/UploadPage.tsx`
- 修改： `src/components/blocks/DocRow.tsx`
- 修改： `docs/6.文件树与目录结构.md`

**接口：**

- 消费： `listKbCategories()`
- 消费： `listDocuments({ category_id })`
- 消费： `uploadDocument(file, { category_id })`
- 产出： category selector state shared by KnowledgeBase and Upload pages.

**步骤：**

- [ ] 创建 `useKbCategories()`，封装 loading、error、categories、selectedCategoryId、defaultLearningCategory。
- [ ] `KnowledgeBasePage` 顶部增加分区筛选：`全部`、`学习区`、`生活区`、`笔记区`、`未分区`、自定义分区。
- [ ] 切换分区时重新调用 `listDocuments({ page: 1, limit: 50, category_id })`，不要只做前端过滤。
- [ ] `DocRow` 展示分区徽标；分区为空时展示“未分区”。
- [ ] `UploadPage` 增加分区选择，默认选 `学习区`；上传时调用 `uploadDocument(file, { category_id })`。
- [ ] 上传成功后任务描述中展示目标分区。
- [ ] 对 categories API 失败提供轻量错误态：允许上传，但明确展示“分区读取失败，本次将上传到未分区/默认区”。
- [ ] 更新 `docs/6.文件树与目录结构.md`，加入新 hook 文件并更新 `src/` 文件数。
- [ ] 运行 `npm run lint`，预期 PASS。
- [ ] 运行 `npm run build`，预期 PASS。

## 6. 任务 3: Chat 分区对话与结构化引用

**文件：**

- 修改： `docs/4.API接口文档.md`
- 修改： `src/lib/api/types.ts`
- 修改： `src/lib/api/chat.ts`
- 修改： `src/features/chat/ChatPage.tsx`
- 修改： `src/features/chat/hooks/useChat.ts`
- 修改： `src/features/chat/lib/stream.ts`
- 修改： `src/components/blocks/ChatMessage.tsx`
- 修改： `src/types/index.ts`
- 修改： `tests/unit/lib/api/endpoints.test.ts`
- 修改： `tests/unit/features/chat/classroomNote.test.ts` or create `tests/unit/features/chat/stream.test.ts`

**接口：**

- 产出： `ChatMode = "qa" | "learning" | "classroom_note" | "verify"`
- 产出： `ChatCitation = { document_id: string; document_name: string; score?: number; snippet: string; chunk_id?: string | null }`
- 扩展： `ChatRequest` with `mode?: ChatMode` and `category_id?: string | null`
- 扩展： `ChatResponse` and `ChatStreamChunk` with `citations?: ChatCitation[]`

**步骤：**

- [ ] 在 API 文档声明 chat 请求新增 `mode`、`category_id`，响应新增 `citations`。
- [ ] 在 `src/lib/api/types.ts` 增加 `ChatCitation` 和 `ChatMode`。
- [ ] 将前端 `ChatMessage.refs?: string[]` 替换为 `citations?: ChatCitation[]`；临时兼容旧 `refs` 只在 adapter 内处理。
- [ ] 更新 `applyStreamChunk()`：chunk 有 `citations` 时合并到 assistant 消息；同一 `document_id + chunk_id` 去重。
- [ ] `ChatPage` 顶部增加分区选择器，发送时带 `mode` 和 `category_id`。
- [ ] 右侧面板把“知识库范围：当前账号知识库”改为真实选中分区，例如“正在对话的知识库：学习区”。
- [ ] `ChatMessage` 增加 `引用来源 (N)` 折叠按钮；展开显示文档名、相似度、片段和“预览原文”。
- [ ] 预览原文复用 `getDocumentContent(document_id)`，用 `Dialog` 展示，片段命中时高亮片段。
- [ ] 收敛 `ChatPage` 与 `useChat` 的重复逻辑：优先让 `ChatPage` 通过 hook 发送/加载/刷新会话，避免两套聊天状态继续分叉。
- [ ] 更新聊天流处理测试，覆盖 content 增量、reasoning、toolName、citations 去重。
- [ ] 运行 `npm run test -- tests/unit/features/chat`，预期 PASS。
- [ ] 运行 `npm run lint`，预期 PASS。
- [ ] 运行 `npm run build`，预期 PASS。

## 7. 任务 4: 题库 API 封装与生成题目入口

**文件：**

- 修改： `docs/4.API接口文档.md`
- 修改： `src/lib/api/types.ts`
- 新增： `src/lib/api/questions.ts`
- 修改： `src/features/knowledge-base/KnowledgeBasePage.tsx`
- 修改： `src/components/blocks/DocRow.tsx`
- 修改： `tests/unit/lib/api/endpoints.test.ts`
- 修改： `docs/6.文件树与目录结构.md`

**接口：**

- 产出： `generateQuestions(payload: { document_id: string; category_id?: string | null; count?: number }): Promise<QuestionGenerateResponse>`
- 产出： `listQuestions(params?: { category_id?: string | null; document_id?: string; limit?: number; cursor?: string }): Promise<QuestionListResponse>`
- 产出： `answerQuestion(questionId: string, payload: { selected_option_id: string }): Promise<AnswerQuestionResponse>`
- 产出： `explainQuestion(questionId: string, payload: ExplainQuestionRequest, onChunk: (chunk: ExplainChunk) => void): Promise<void>`

**步骤：**

- [ ] 在 API 文档新增 questions 章节：generate、list、answer、explain SSE。
- [ ] 在 `src/lib/api/types.ts` 增加 `Question`、`QuestionOption`、`QuestionGenerateResponse`、`AnswerQuestionResponse`、`ExplainChunk`。
- [ ] 创建 `src/lib/api/questions.ts`，所有端点使用 `apiRequest` / `apiStream`。
- [ ] `DocRow` 增加“生成题目”图标按钮，带 `aria-label`。
- [ ] `KnowledgeBasePage` 处理生成题目动作，展示 loading、成功新增数量、重复数量、失败错误。
- [ ] 生成成功后提供跳转 `/practice?category_id=...&document_id=...`。
- [ ] 更新 API endpoint 测试，覆盖 questions 端点和 SSE explain 请求体。
- [ ] 更新 `docs/6.文件树与目录结构.md`，加入 `src/lib/api/questions.ts`。
- [ ] 运行 `npm run test -- tests/unit/lib/api/endpoints.test.ts`，预期 PASS。
- [ ] 运行 `npm run lint`，预期 PASS。

## 8. 任务 5: `/practice` 刷题页面

**文件：**

- 新增： `src/features/practice/PracticePage.tsx`
- 新增： `src/features/practice/components/QuestionCard.tsx`
- 新增： `src/features/practice/hooks/usePracticeSession.ts`
- 新增： `src/features/practice/lib/question.ts`
- 修改： `src/routes/index.tsx`
- 修改： `src/data/nav.ts`
- 修改： `src/components/layout/Topbar.tsx`
- 新增： `tests/unit/features/practice/question.test.ts`
- 新增： `tests/features/practice/PracticePage.test.tsx`
- 修改： `docs/6.文件树与目录结构.md`

**接口：**

- 消费： `listQuestions()`
- 消费： `answerQuestion()`
- 产出： `/practice` route.
- 产出： selected answer state, answer feedback state, progress summary.

**步骤：**

- [ ] 创建 `question.ts` 纯函数：`getOptionLabel(index)`、`isAnswered(state)`、`nextQuestionIndex(current, total)`、`getAccuracy(correct, total)`。
- [ ] 为 `question.ts` 写单元测试，覆盖 A/B/C/D、最后一题、0 题准确率。
- [ ] 创建 `usePracticeSession()`，封装 category/document query、题目加载、当前题、提交答案、下一题。
- [ ] 创建 `QuestionCard`：展示题干、A/B/C/D 选项、提交后显示绿色正确/红色错误、正确答案、解析、原文引用。
- [ ] 创建 `PracticePage`：顶部分区选择和题库状态；中间题目卡；右侧进度、正确率、当前来源。
- [ ] 空题库时展示上传/生成题目的入口：去知识库或去上传。
- [ ] 在 `src/routes/index.tsx` 注册 `/practice`，使用 `ProtectedRoute`。
- [ ] 在 `src/data/nav.ts` 的学习分组新增“刷题”。
- [ ] 在 `Topbar.titleMap` 增加 `/practice`: `刷题`。
- [ ] 更新 `docs/6.文件树与目录结构.md`，加入新增 practice 文件和测试文件。
- [ ] 运行 `npm run test -- tests/unit/features/practice/question.test.ts tests/features/practice/PracticePage.test.tsx`，预期 PASS。
- [ ] 运行 `npm run build`，预期 PASS。

## 9. 任务 6: 答错讲解 ExplainPanel

**文件：**

- 新增： `src/features/practice/components/ExplainPanel.tsx`
- 修改： `src/features/practice/PracticePage.tsx`
- 修改： `src/features/practice/hooks/usePracticeSession.ts`
- 修改： `src/lib/api/questions.ts`
- 新增： `tests/unit/features/practice/explainStream.test.ts`
- 修改： `docs/6.文件树与目录结构.md`

**接口：**

- 消费： `explainQuestion(questionId, payload, onChunk)`
- 产出： question-scoped explanation thread.
- 默认 payload： `{ selected_option_id, category_id, document_id, user_message }`

**步骤：**

- [ ] `QuestionCard` 在答错或用户点击“我不会，让 Tina 教教我”时开放 ExplainPanel。
- [ ] `ExplainPanel` 使用 `Sheet` / `Dialog`：桌面右侧，移动端底部。
- [ ] 初始打开时自动请求 explain SSE，逐段追加 Tina 讲解。
- [ ] 支持用户继续追问，追问仍带当前 `question_id`、已选答案、分区和文档上下文。
- [ ] SSE 失败时展示错误和“重试讲解”按钮，不伪造成功。
- [ ] 讲解区展示引用来源，复用 Chat 引用组件或同一结构。
- [ ] 写 explain stream 纯函数测试：chunk 追加、完成态、错误态。
- [ ] 更新 `docs/6.文件树与目录结构.md`。
- [ ] 运行 `npm run test -- tests/unit/features/practice/explainStream.test.ts`，预期 PASS。
- [ ] 运行 `npm run lint`，预期 PASS。

## 10. 任务 7: 图谱掌握度与刷题结果联动

**文件：**

- 修改： `src/lib/api/types.ts`
- 修改： `src/lib/api/kt.ts`
- 修改： `src/lib/api/adapters.ts`
- 修改： `src/features/knowledge-graph/KnowledgeGraphPage.tsx`
- 修改： `src/features/knowledge-graph/GraphCanvas.tsx`
- 修改： `tests/unit/lib/api/adapters.test.ts`

**接口：**

- 消费： `getSkillGraph()`
- 消费： `getSkillStates()`
- 产出： mastery display `{ value: number; status: "mastered" | "weak" | "unseen"; last_practiced_at?: string }`

**步骤：**

- [ ] 确认 `getSkillStates()` 返回仍是 `Record<skill_id, number>`；若后端扩展对象，adapter 兼容两种形状。
- [ ] `mergeGraphWithStates()` 输出 mastery 状态：`>=0.75 mastered`，`>0 && <0.75 weak`，缺失为 `unseen`。
- [ ] `GraphCanvas` 节点颜色按 mastery 状态展示：绿色、红色、灰色，同时保留百分比文本。
- [ ] `KnowledgeGraphPage` 增加分区筛选；如果后端 KT 不支持 category，前端展示“当前为全局图谱”说明。
- [ ] 节点详情增加最近学习时间字段；没有数据时展示“暂无记录”。
- [ ] Practice 页面答题后提供“刷新图谱”入口或跳转 `/graph?category_id=...`。
- [ ] 更新 adapter 测试，覆盖 states 数字形状、对象形状、缺失状态。
- [ ] 运行 `npm run test -- tests/unit/lib/api/adapters.test.ts`，预期 PASS。
- [ ] 运行 `npm run lint`，预期 PASS。

## 11. 任务 8: 笔记真实 CRUD 与聊天保存闭环

**文件：**

- 修改： `docs/4.API接口文档.md`
- 修改： `src/lib/api/types.ts`
- 修改： `src/lib/api/notes.ts`
- 修改： `src/features/notes/NotesPage.tsx`
- 修改： `src/features/notes/NoteEditorPage.tsx`
- 修改： `src/features/notes/hooks/useNoteEditor.ts`
- 修改： `src/features/chat/ChatPage.tsx`
- 修改： `tests/unit/lib/api/endpoints.test.ts`
- 修改： `tests/features/notes/NotesPage.test.tsx`

**接口：**

- 产出： `listNotes(params?: { q?: string; page?: number; limit?: number; tag?: string }): Promise<NoteListResponse>`
- 产出： `createNote(payload: CreateNoteRequest | ManualNoteCreateRequest): Promise<CreateNoteResponse>`
- 产出： `updateNote(id: string, payload: UpdateNoteRequest): Promise<NoteResponse>`
- 产出： `deleteNote(id: string): Promise<MessageResponse>`

**步骤：**

- [ ] 在 API 文档补齐 notes list/update/delete；保留课堂笔记 create + index_to_kb 契约。
- [ ] 扩展 `CreateNoteRequest`，支持 `source: "manual" | "doc" | "ai"`，但课堂笔记仍固定 `index_to_kb: true`。
- [ ] `NotesPage` 改为调用 `listNotes()`，搜索使用 query 请求；后端不支持时才降级本地过滤。
- [ ] `NoteEditorPage` 读取真实笔记详情；保存使用 `updateNote()`；删除使用 `deleteNote()`。
- [ ] `useNoteEditor` 保留自动保存/手动保存状态，失败时展示错误，不丢本地输入。
- [ ] `ChatPage` 课堂笔记保存继续用 `createNote()`，保存成功后提供打开笔记入口。
- [ ] 开发模式 demo store 只在显式 demo 配置开启时生效，不覆盖真实 API 失败。
- [ ] 更新 notes API 和页面测试。
- [ ] 运行 `npm run test -- tests/unit/lib/api/endpoints.test.ts tests/features/notes/NotesPage.test.tsx`，预期 PASS。
- [ ] 运行 `npm run build`，预期 PASS。

## 12. 任务 9: 体验收敛、错误态和权限态

**文件：**

- 修改： `src/components/blocks/Notice.tsx` if needed
- 修改： `src/features/chat/ChatPage.tsx`
- 修改： `src/features/knowledge-base/KnowledgeBasePage.tsx`
- 修改： `src/features/knowledge-base/UploadPage.tsx`
- 修改： `src/features/practice/PracticePage.tsx`
- 修改： `src/features/knowledge-graph/KnowledgeGraphPage.tsx`
- 修改： `src/features/notes/NotesPage.tsx`

**接口：**

- 消费： `ApiError.status`
- 产出： consistent loading、empty、error、quota/permission UI.

**步骤：**

- [ ] 统一 401：让 `ProtectedRoute/AuthContext` 处理重新登录，页面只展示当前操作失败。
- [ ] 统一 403/配额：展示当前能力不可用原因和升级入口，不把付费能力伪装成已生效。
- [ ] 统一 404：文档、题目、笔记不存在时提供返回列表入口。
- [ ] 统一 422：展示字段级或操作级可理解原因。
- [ ] 所有新增图标按钮检查 `aria-label` 或 `title`。
- [ ] 桌面和移动端检查 Chat、Practice、ExplainPanel、KnowledgeBase 的文本不溢出。
- [ ] 运行 `npm run lint`，预期 PASS。
- [ ] 运行 `npm run build`，预期 PASS。

## 13. 任务 10: 文档回写与最终验证

**文件：**

- 修改： `docs/2.技术架构文档.md`
- 修改： `docs/4.API接口文档.md`
- 修改： `docs/6.文件树与目录结构.md`
- 可选修改： `docs/前端功能补齐清单.md`

**接口：**

- 产出： current implementation truth aligned with code.

**步骤：**

- [ ] 更新 `docs/2.技术架构文档.md` 的路由表、页面架构、当前风险与阶段路线。
- [ ] 确认 `docs/4.API接口文档.md` 与 `src/lib/api` 完全一致。
- [ ] 确认 `docs/6.文件树与目录结构.md` 的 `src/` / `tests/` 文件树和数量准确。
- [ ] 如果 `docs/前端功能补齐清单.md` 仍作为参考文档，补充 v1 刷题闭环与旧画像闭环的关系，避免两个计划互相冲突。
- [ ] 运行 `rg --files src tests | sort`，与 `docs/6.文件树与目录结构.md` 抽查一致。
- [ ] 运行 `npm run test`，预期 PASS。
- [ ] 运行 `npm run lint`，预期 PASS。
- [ ] 运行 `npm run build`，预期 PASS。
- [ ] 运行 `git diff --check`，预期无 whitespace error。

## 14. 推荐实施顺序

1. 任务 1：先锁 API/类型契约，不碰页面体验。
2. 任务 2：完成分区在知识库和上传中的闭环。
3. 任务 3：完成 Chat 分区和引用，解决用户“AI 从哪里得出答案”的信任问题。
4. 任务 4：补题库 API 和“生成题目”入口。
5. 任务 5：上线 `/practice` 刷题主路径。
6. 任务 6：补答错讲解，把刷题从判分升级成教练。
7. 任务 7：把答题/KT 状态映射到图谱掌握度。
8. 任务 8：完成笔记真实 CRUD 和聊天保存闭环。
9. 任务 9：统一错误态、权限态、响应式细节。
10. 任务 10：回写文档并跑全量验证。

## 15. 8 天冲刺建议

| 天数 | 前端交付 | 依赖 |
| --- | --- | --- |
| 第 1 天 | 任务 1 契约与类型；确认分区、引用、题目模型 | 产品/后端确认字段 |
| 第 2 天 | 任务 2 知识库分区与上传分区 | categories API 或 mock fallback |
| 第 3 天 | 任务 3 Chat 分区与引用来源 | chat `category_id` / citations |
| 第 4 天 | 任务 4 生成题目入口；questions API 测试 | questions generate/list |
| 第 5 天 | 任务 5 `/practice` 刷题页 | questions list/answer |
| 第 6 天 | 任务 6 ExplainPanel 流式讲解 | questions explain SSE |
| 第 7 天 | 任务 7 图谱掌握度；任务 8 笔记 CRUD 基础 | KT states / notes API |
| 第 8 天 | 任务 9/10 打磨、文档、全量验证 | 完整前端回归 |

## 16. 验收清单

- [ ] 用户能创建/查看分区，并把上传资料放入学习区。
- [ ] 知识库页能按分区筛选文档。
- [ ] 聊天页能选择学习区，右侧面板显示当前对话知识库。
- [ ] 聊天回复能展开结构化引用来源，并可打开原文预览。
- [ ] 学习区文档可以触发生成题目，并展示新增/重复结果。
- [ ] `/practice` 可按分区加载题目并答题。
- [ ] 答题后立即看到对错、正确答案、解析和原文引用。
- [ ] 答错或不会时可以打开 Tina 讲解面板，SSE 逐段显示。
- [ ] 知识图谱节点能按掌握度颜色展示。
- [ ] 笔记列表、搜索、新建、编辑、删除走真实 API 或明确的开发 fallback。
- [ ] 聊天课堂笔记保存成功后可打开笔记。
- [ ] `npm run test`、`npm run lint`、`npm run build`、`git diff --check` 通过。

## 17. 不进入本轮前端范围

- 多选题、填空题、主观题批改。
- 错题归因的完整知识链解释。
- 学习路径任务生命周期。
- LVR 曲线和长期学习历史趋势。
- 推理模式的完整 `Dynamic-e` / `CABR` 风险审查。
- 提醒和通知中心真实后端接入。
- 机构端、学校端、家长端、公益端。

## 18. 执行提示

- 每个任务单独提交，提交信息使用 Conventional Commits，例如 `feat: 接入知识库分区筛选`。
- dirty repo 中不要使用 `git add .`；按任务白名单暂存。
- 如果后端端点未就绪，前端可以保留明确的开发 fallback，但 UI 必须标注为“开发演示/接口未就绪”，不能把它说成真实业务数据。
- 如果产品确认某个默认口径不同，先更新本计划对应的“歧义/默认口径”和相关任务，再实施。
