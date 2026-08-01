# 知拾 — 工程实现指南

> **目标读者**：接手开发的自己 / 协作者  
> **产品方向**：见 [PLAN.md](./PLAN.md)（王晨）  
> **数据模型**：见 [backend/docs/DATABASE.md](../backend/docs/DATABASE.md)  
> **接口契约**：见 [backend/docs/API.md](../backend/docs/API.md)（现有）+ 本文各阶段新增约定

---

## 0. 产品目标（与 PLAN 对齐）

知拾从「第二大脑 / 知识存储 + 通用聊天」转向「**以学习资料驱动的刷题 + 苏格拉底式辅导**」。核心闭环：

1. 用户把资料放进**学习区**知识库 → 自动分段 → 自动/半自动出题  
2. 用户刷题（含「我不会」）→ 答错展示原文与解析 → 可唤起辅导 Agent  
3. 聊天时选择知识库分区，回答带 **citation**，前端可跳转高亮原文  

PLAN 描述「做什么」；本文描述「怎么按依赖顺序做出来」。

---

## 1. 与 PLAN.md 的关系

| 文档 | 职责 |
|------|------|
| `docs/PLAN.md` | 产品动机、用户故事、难点标注 |
| `backend/docs/DATABASE.md` | 表结构、字段、ER、去重与 zone 规则 |
| `backend/docs/API.md` | 已实现接口的契约（auth/chat/kb/kt…） |
| **`docs/DEV_GUIDE.md`** | **开发新功能实操**：models/crud/service/router、前端 api.ts/features 怎么写 |
| **`docs/IMPLEMENTATION.md`（本文）** | 分阶段可执行步骤、文件路径、验收标准 |

> 按 S1–S8 做新能力时：**IMPLEMENTATION 定任务与验收，DEV_GUIDE 定代码写法与范本路径**。

实现时以 **DATABASE.md 为 schema 真源**；新增 REST 端点实现后回写 `API.md`。

---

## 2. 仓库架构

### 2.1 Monorepo 目录职责

```
zhishi/
├── backend/          # FastAPI 服务（端口 8765）
│   ├── server.py     # 入口：lifespan 初始化 DB / LEKT / AgentManager
│   ├── app/
│   │   ├── api/v1/   # 路由层（薄）
│   │   ├── services/ # 业务逻辑
│   │   ├── crud/     # 数据访问（可逐步拆 repository）
│   │   ├── models/   # SQLAlchemy ORM
│   │   ├── schemas/  # Pydantic 请求/响应
│   │   ├── core/     # config / database / redis / security
│   │   └── utils/    # tina_loader 等
│   ├── 3rdParty/tina/ # Tina Agent（勿直接改 sys.path）
│   ├── docs/         # 后端专项文档
│   └── storage/      # 本地文件（gitignore）
├── frontend/         # React + Vite Web 端
│   └── src/
│       ├── lib/api.ts      # HTTP 客户端（待改 VITE_API_BASE）
│       └── features/       # 按页面划分
├── docs/             # 产品 & 工程文档（PLAN / TEAM / 本文）
└── data/             # SQLite 文件等运行时数据（gitignore）
    └── zhishi.db     # 本地默认库路径
```

### 2.2 分层约定

```
HTTP Request
    → router (app/api/v1/*.py)     # 参数校验、鉴权、HTTP 状态码
    → service (app/services/*.py)  # 业务编排、调用 Tina/Dify、事务边界
    → crud/repository              # 单表/多表查询，不含 LLM 逻辑
    → models (app/models/*.py)     # SQLAlchemy 映射
```

**原则**：

- Router 不写 SQL、不直接调 `tina`  
- LLM/Agent **统一**经 `app.utils.tina_loader`（`tina_env_path()` / `tina`）  
- 用户隔离：凡带 `user_id` 的查询必须在 service/crud 层强制过滤  
- 长任务（分段、出题）先落库状态字段，再同步或后台执行（v1 可同步，注意超时）

### 2.3 当前实现状态（截至文档编写时）

| 模块 | 状态 | 说明 |
|------|------|------|
| Auth / Plan / Chat / KT / Dashboard | ✅ 已有 | 见 `router.py` |
| KB 上传/列表/删除 | ✅ 已有 | S2：分区 + DB 去重 + global_documents |
| SQLAlchemy models | ✅ S1 完成 | 13 张表 ORM 已建（含 `global_documents`） |
| Alembic | ⚠️ 待 S1+ | S1 暂用 `init_db()` + `create_all` |
| `kb_collections` CRUD | ✅ S2 完成 | 注册 seed + API |
| 刷题 / 辅导 | ✅ 刷题已实现 / 辅导 S6 完成 | S5–S6 完成 |
| 前端联调 | ⚠️ 部分 | `api.ts` 硬编码公网地址 |

---

## 3. 第一版 MVP 与完整版差异

| 能力 | MVP（最小可验证） | 完整版 |
|------|-------------------|--------|
| 数据库 | SQLite 单文件 `data/zhishi.db` | 团队 MySQL，同一套 models |
| 知识库分区 | 注册时 seed 学习区/生活区；上传必选 collection | 用户自建多个 collection、独立 dataset |
| 文档去重 | 用户级去重（`documents` 表） | + `global_documents` 全局去重 |
| 分段 | Markdown 标题切分 + 定长 fallback | + PDF 结构感知、overlap 调优 |
| 出题 | 每段 1–2 道 LLM 单选题，同步生成 | 提取原书习题 + 扩展题 + `content_hash` 全局去重 |
| 刷题 | 单文档选题、提交、对错、展示 excerpt | 按 collection 组卷、计时、KT 喂数 |
| 辅导 | 「我不会」创建 `tutor_session`，绑定 segment 上下文聊天 | 苏格拉底多轮工具链 + 掌握度回写 |
| Citation | 聊天响应 JSON 字段 `citations[]` | 前端文内 `[1]` 点击高亮 `char_start/end` |
| 前端 | 学习区上传 → 等出题 → 刷题页 | 分区选择器、引用跳转、辅导侧栏 |

**MVP 验收一句话**：注册 → 上传 `.md` 到学习区 → 自动生成题 → 完成一次刷题并看到错题原文 → 「我不会」进入辅导对话。

---

## 4. 阶段依赖与建议顺序

```mermaid
flowchart LR
    S0[S0 环境联调] --> S1[S1 DB 基础]
    S1 --> S2[S2 分区与文档]
    S2 --> S3[S3 分段]
    S3 --> S4[S4 出题]
    S4 --> S5[S5 刷题]
    S5 --> S6[S6 辅导 Agent]
    S2 --> S7[S7 聊天分区+citation]
    S5 --> S8[S8 前端闭环]
    S6 --> S8
    S7 --> S8
```

| 阶段 | 名称 | 前置 | 可并行 |
|------|------|------|--------|
| S0 | 环境联调 | — | — |
| S1 | DB 与 ORM 基础 | S0 | — |
| S2 | 知识库分区 + 文档入库 | S1 | — |
| S3 | 文档分段 | S2 | — |
| S4 | 出题与溯源 | S3 | — |
| S5 | 刷题会话 | S4 | S7 部分 |
| S6 | 辅导 Agent | S5 | — |
| S7 | 聊天 citation | S2, S3 | S5 |
| S8 | 前端联调 | S4+ | — |

---

## 5. 配置与环境变量

### 5.1 后端 `backend/.env`（示例）

```env
# 数据库 — 本地开发推荐 SQLite（与 DATABASE.md 一致）
DATABASE_URL=sqlite:///./data/zhishi.db

# 团队联调可切 MySQL
# DATABASE_URL=mysql+pymysql://user:pass@127.0.0.1:3306/my_ai_app

SECRET_KEY=...
REDIS_URL=redis://127.0.0.1:6379/0
CACHE_BACKEND=redis

DIFY_DATASET_API_KEY=...
DIFY_BASE_URL=https://api.dify.ai/v1

LOCAL_STORAGE_DIR=storage
USE_OSS=false
DEBUG_MAX_UPLOAD_SIZE=10485760
```

### 5.2 SQLite 专项

在 `app/core/database.py` 的 `create_engine` 中对 sqlite 连接加：

```python
connect_args={"check_same_thread": False}
# 并在首次连接执行 PRAGMA foreign_keys=ON
```

`data/` 目录需存在且 gitignore。

### 5.3 前端 `frontend/.env.development`

```env
VITE_API_BASE=http://127.0.0.1:8765
```

`frontend/src/lib/api.ts` 改为：

```typescript
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765"
```

生产 / 穿透环境在 `.env.production` 覆盖即可。

### 5.4 Tina

- 配置文件：`backend/tina.env`  
- 代码入口：`from app.utils.tina_loader import tina, tina_env_path`  
- 禁止在业务文件手写 `sys.path.insert`

---

## 6. 分阶段实现

---

### S0 — 环境联调

**目标**：本机前后端 + Redis 跑通，团队能复现。

**前置依赖**：Python 3.14、Node 18+、Redis（或 `CACHE_BACKEND=memory` 仅本地调试）。

**涉及路径**：

| 操作 | 路径 |
|------|------|
| 后端启动 | `backend/server.py` |
| 依赖 | `backend/requirements.txt` |
| 前端启动 | `frontend/package.json` |
| 环境变量 | `backend/.env`、`frontend/.env.development` |

**实现要点**：

1. `cd backend && uvicorn server:app --host 127.0.0.1 --port 8765`  
2. `curl http://127.0.0.1:8765/health` → `status` 为 `ok` 或 `degraded` 均可  
3. 注册/登录拿 token，调 `/api/v1/auth/test-token-info`  
4. 前端 `VITE_API_BASE` 指向本地，登录页能进 Dashboard  

**验收标准**：

- [ ] 健康检查 200  
- [ ] 注册 → 登录 → `getMe` 成功  
- [ ] 上传 txt → `kb/documents` 列表可见  
- [ ] Chat SSE 能收到流式回复  

**常见坑**：

- README 中 `kt_backend` 已更名为 `backend`，路径以仓库为准  
- MySQL 未装时可先用 SQLite 完成 S0–S4  
- Redis 未起时 chat 会话可能失败；开发可暂用 memory cache（需确认 `app/core/redis.py` 是否支持）

---

### S1 — 数据库与 ORM 基础

**目标**：按 DATABASE.md 建齐 ORM + 迁移机制；默认 SQLite。

**前置依赖**：S0

**新建/修改文件**：

```
backend/app/models/
├── models.py              # 保留 User, PlanTier
├── kb.py                  # kb_collections, documents, global_documents, document_segments
├── quiz.py                # global_questions, question_provenance, user_question_refs
├── quiz_session.py        # quiz_sessions, quiz_session_questions, quiz_answers
└── tutor.py               # tutor_sessions

backend/app/models/__init__.py   # 导出全部 Base 子类

backend/app/core/
├── config.py              # DATABASE_URL 默认改为 sqlite
└── database.py            # sqlite connect_args + FK pragma

backend/alembic/           # 待建（S1 暂用 init_db create_all）
├── env.py
└── versions/001_plan_schema.py

# backend/app/crud/          # S2+ 再建
# ├── kb.py
# ├── quiz.py
# └── tutor.py
```

**实现要点**：

1. UUID 主键统一 `String(36)`，默认值 `str(uuid.uuid4())`  
2. JSON 字段（`tags`, `options`）用 `Text` 存 JSON 字符串，schema 层 pydantic 校验  
3. `init_db()` 仍可调 `create_all`，但**团队以 Alembic 为准**  
4. 迁移脚本 `001_plan_schema.py` 一次建齐 10 张新表（见 DATABASE.md §11）  
5. 注册流程 `auth_service.register` 末尾增加 seed（DATABASE.md §10）：
   - `学习区` `zone=study` `is_default=1`
   - `生活区` `zone=life`

**验收标准**：

- [x] `init_db()` / `create_all` 无报错，`data/zhishi.db` 含全部 13 张表（users + plan_tiers + 10 张新表）
- [ ] `alembic upgrade head` 无报错（S1 暂跳过 Alembic，后续补 `001_plan_schema.py`）
- [x] 新用户注册后 `kb_collections` 有 2 行（S2 注册 seed，见 DATABASE.md §10）
- [x] 外键：`documents.collection_id` → `kb_collections.id` 默认 RESTRICT（未设 `ondelete`）

**S1 完成备注（2026-07-02）**：默认 `DATABASE_URL` 指向项目根 `data/zhishi.db`；models 拆分为 `kb.py` / `quiz.py` / `quiz_session.py` / `tutor.py`；SQLite `check_same_thread=False` + `PRAGMA foreign_keys=ON`。

**常见坑**：

- SQLite 不支持部分 ALTER；表结构大改用新 migration 重建  
- `models.py` 单文件过大可拆分，但 `init_db` 必须 import 到所有 model  
- 现有 MySQL 部署需单独 migration，不要混用两套 schema 文件

---

### S2 — 知识库分区与文档管理

**目标**：`kb_collections` CRUD；上传写入 `documents` + `global_documents`；废弃 `upload_hashes.json`。

**前置依赖**：S1

**新建/修改文件**：

```
backend/app/schemas/kb.py           # CollectionOut, DocumentOut, UploadResponse
backend/app/services/kb_service.py  # 上传编排：hash → global → document → dify
backend/app/services/document_repository.py  # 或 app/crud/kb.py
backend/app/api/v1/kb.py            # 扩展路由
backend/app/api/v1/collections.py   # 新建：/collections
backend/app/api/v1/router.py        # include collections
```

**API 约定（新增，需补进 API.md）**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/kb/collections` | 当前用户的分区列表 |
| POST | `/api/v1/kb/collections` | 创建分区 `{name, zone, description?}` |
| PATCH | `/api/v1/kb/collections/{id}` | 改名、描述 |
| POST | `/api/v1/kb/upload` | **增加** `collection_id`（form 字段）；缺省用默认学习区 |
| GET | `/api/v1/kb/documents` | **增加** `collection_id` 过滤 |

**数据流（上传）**：

```
UploadFile
  → SHA256
  → 查 global_documents by content_hash
      命中: 复用 storage_path, 新建 documents 行
      未命中: storage_service 写全局路径 storage/global/{hash[:2]}/{hash}
  → 解析文本 → parsed 缓存
  → **RAG_BACKEND=local（默认）**：segment → Chroma 索引（`data/chroma/`），不调用 Dify
  → **RAG_BACKEND=dify**：DifyKB.upload（dataset_id = collection.dataset_id or user.dataset_id）
  → documents.indexing_status = processing → completed
  → 若 zone==study: 触发 S3 分段（可先同步调用 segment_service）
```

**验收标准**：

- [x] 上传到学习区与生活区分别可见，`zone` 正确  
- [x] 同用户重复上传同文件 → 400 或返回 duplicate（不重复扣配额）  
- [x] 不同用户同 hash → 共用 `global_documents` 行（完整版）；MVP 可先只做用户级  
- [x] `upload_hashes.json` 不再读写（content 预览保留只读 fallback）

**常见坑**：

- 旧接口返回的 `document_id` 是 Dify ID；新接口应对外统一用 `documents.id`（UUID），内部映射 `dify_document_id`  
- 删除文档：仅删用户 `documents` 引用；`global_documents` 引用计数为 0 再删物理文件  
- `collection.dataset_id` 为空时回退 `users.dataset_id`，与现网行为一致

---

### S3 — 文档分段（document_segments）

**目标**：学习区文档解析后写入分段，供出题与 citation 定位。

**前置依赖**：S2

**新建/修改文件**：

```
backend/app/services/segment_service.py
backend/app/schemas/segment.py
backend/app/api/v1/segments.py      # 可选：GET /documents/{id}/segments
```

**实现要点**：

1. **仅 `zone=study`** 执行分段；`life` 跳过  
2. 输入：优先 `parsed_cache_key` 文本；无则 `file_parser.parse_file`  
3. 策略（DATABASE.md §4.4）：
   - 有 `#` / `##`：按标题切 `document_segments`
   - 无标题：窗口 1500 字，overlap 200
4. 每段写入 `order_index`, `char_start`, `char_end`, `title`, `content`  
5. 更新 `documents.segment_status`: `not_started → processing → completed | failed`  
6. 上传流程末尾调用：`if doc.zone == "study": segment_service.segment_document(doc.id)`  

**验收标准**：

- [x] 上传 `.md` 后 `document_segments` 行数 ≥ 1  
- [x] `char_start/char_end` 与全文对得上（抽样校验）  
- [x] 生活区文档 `segment_status` 保持 `not_started`  

**常见坑**：

- 超大 PDF 同步分段会超时 → 响应先返回 200，后台线程分段（可用 FastAPI `BackgroundTasks`）  
- 重新上传同文档：先删旧 segments 再写新段  
- Dify 内部分段与 `document_segments` 无关，不要混用

---

### S4 — 出题（global_questions + provenance）

**目标**：从分段生成题目，写入全局题库 + 用户引用 + 溯源。

**前置依赖**：S3

**新建/修改文件**：

```
backend/app/services/question_gen_service.py
backend/app/services/question_hash.py       # 题干规范化 → content_hash
backend/app/schemas/question.py
backend/app/crud/question.py
backend/app/api/v1/questions.py
backend/app/api/v1/router.py
```

**API 约定**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/questions` | `?document_id=&collection_id=` 列出用户可见题 |
| POST | `/api/v1/questions/generate` | `{document_id}` 手动触发（上传已自动则可省略） |
| GET | `/api/v1/questions/{id}` | 含 provenance、关联 segment |

**实现要点**：

1. 遍历 `document_segments`，每段调 Tina（`tina_loader`）生成 1–2 道 **单选题**  
2. Prompt 要求输出 JSON：`{stem, options, answer, explanation, tags}`  
3. `content_hash = sha256(normalize(stem+options+answer))`  
4. 查 `global_questions`：存在则复用，否则 insert  
5. 写 `question_provenance`（`document_id`, `segment_id`, `excerpt`）  
6. 写 `user_question_refs`（`user_id`, `question_id`, `document_id`, `collection_id`）  
7. 更新 `documents.question_gen_status`  

**Tina 调用示例结构**（放在 service，非 router）：

```python
from app.utils.tina_loader import tina_env_path
from tina.llm import BaseAPI

llm = BaseAPI(env_path=tina_env_path())
# 同步 predict 或异步 apredict，按现有 zhishi_agent 模式
```

**验收标准**：

- [x] 学习区文档完成后 `user_question_refs` ≥ 1  
- [x] 同一题干全局只一条 `global_questions`  
- [x] `GET /questions/{id}` 能返回 `segment_id` 与 `excerpt`  

**常见坑**：

- LLM JSON 解析失败要有重试/跳过策略，避免整文档失败  
- 出题成本：MVP 限制每文档最多 N 段或 N 题  
- 标签 `tags`：MVP 用 LLM 生成；完整版再加用户手填 / 外部词表

---

### S5 — 刷题会话（quiz_sessions）

**目标**：创建会话、答题、判分、错题展示原文。

**前置依赖**：S4

**新建/修改文件**：

```
backend/app/services/quiz_service.py
backend/app/schemas/quiz.py
backend/app/crud/quiz.py
backend/app/api/v1/quiz.py
backend/app/api/v1/router.py
backend/test_s5_quiz.py
```

**API 约定**：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/quiz/sessions` | `{document_id?, collection_id?, question_ids?}` 创建 |
| GET | `/api/v1/quiz/sessions/{id}` | 会话题序、进度 |
| POST | `/api/v1/quiz/sessions/{id}/answers` | `{question_id, user_answer, status?, time_spent_seconds?}` |
| GET | `/api/v1/quiz/sessions/{id}/results` | 错题列表 + provenance 原文 |

**`status` 枚举**：`correct` | `wrong` | `unknown`（「我不会」）

**实现要点**：

1. 创建会话：默认从 `user_question_refs` 按 `document_id` 拉题，shuffle 后写入 `quiz_session_questions`  
2. 提交答案：单选比对 `global_questions.answer`；简答题 MVP 可只做 exact match  
3. `wrong` / `unknown` 响应体携带：

```json
{
  "status": "wrong",
  "explanation": "...",
  "citation": {
    "doc_id": "...",
    "segment_id": "...",
    "title": "...",
    "char_start": 0,
    "char_end": 100,
    "snippet": "..."
  }
}
```

4. 会话 `status`：全部作答 → `completed`

**验收标准**：

- [x] 能完成 3 题以上并看到对错  
- [x] 错题返回可定位的 `segment_id`  
- [x] `unknown` 不判错，但记入 `quiz_answers`  

**常见坑**：

- `UNIQUE(session_id, question_id)`：是否允许多次作答要在 schema 中定死  
- 出题未完成时创建会话 → 返回 409 或空题列表提示

---

### S6 — 辅导 Agent（tutor_sessions）

**目标**：「我不会，和 Agent 聊聊」— 绑定题目 + 分段上下文的苏格拉底式对话。

**前置依赖**：S5

**新建/修改文件**：

```
backend/app/services/tutor_service.py
backend/app/schemas/tutor.py
backend/app/crud/tutor.py
backend/app/api/v1/tutor.py
backend/test_s6_tutor.py
```

**API 约定**：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/tutor/sessions` | `{question_id, quiz_session_id?, quiz_answer_id?}` 创建 |
| POST | `/api/v1/tutor/sessions/{id}/messages` | `{content, stream?}` SSE 同 chat |
| GET | `/api/v1/tutor/sessions/{id}` | 元数据 + 绑定 segment 摘要 |

**实现要点**：

1. 创建时从 `question_provenance` 取 `segment_id`，写入 `tutor_sessions`  
2. `chat_session_id`：复用 Redis chat 键，或独立前缀 `tutor:history:{user}:{id}`  
3. System prompt 注入：题干、用户答案、**分段全文**（非整文档）、「禁止直接给答案，用引导问题」  
4. 工具：MVP 仅 `search_knowledge_base`；完整版加 KT `evaluate`（可选）  
5. Tina 仍经 `tina_loader`  

**验收标准**：

- [x] 从刷题页点「我不会」能进入辅导对话（`POST /tutor/sessions` + `quiz_session_id`）
- [x] Agent 回复明显引用分段内容（system prompt 注入 excerpt/分段全文）
- [x] `tutor_sessions.segment_id` 与错题 citation 一致

**S6 完成备注（2026-07-02）**：`SocraticTutorAgent` 内置于 `tutor_service.py`；对话历史 Redis 键 `tutor:history:{user}:{chat_session_id}`，Redis 不可用时回退内存；`test_s6_tutor.py` mock Agent 验证创建、消息往返与上下文注入。

**常见坑**：

- 分段过长需截断并注明；优先 `excerpt`，必要时 `content` 前 4000 字  
- 与通用 `/chat` 隔离 session，避免历史混淆  
- 流式 SSE 格式与 `chat.py` 保持一致，前端可复用解析逻辑

---

### S7 — 聊天分区选择与 Citation

**目标**：对话前选择 `kb_collections`；回答带可定位引用。

**前置依赖**：S2、S3（分段数据）

**修改文件**：

```
backend/app/schemas/schemas.py        # ChatRequest 增加 collection_id
backend/app/api/v1/chat.py
backend/app/services/zhishi_agent.py
backend/app/services/citation_service.py
```

**实现要点**：

1. `ChatRequest` 增加可选 `collection_id`；缺省用默认学习区  
2. `AgentManager.get_agent(user, collection)`：按 collection 的 `dataset_id` 构造 `DifyKB`  
3. 检索命中 Dify 片段后，用 `dify_document_id` 反查 `documents` + 最近 `document_segments`（按字符或模糊匹配）生成 `citations[]`  
4. SSE 末包或单独字段携带：

```json
{
  "citations": [
    {
      "doc_id": "uuid",
      "segment_id": "uuid",
      "title": "第二章",
      "char_start": 1200,
      "char_end": 1450,
      "snippet": "..."
    }
  ]
}
```

5. v2 再考虑持久化 `chat_citations` 表（DATABASE.md §8）

**验收标准**：

- [x] 前端传 `collection_id` 后检索范围切换（生活区 vs 学习区）  
- [x] 非流式与流式均能拿到 `citations`（流式可在最后一条 event）  
- [x] citation 的 `doc_id` 可调用 `GET /kb/documents/{id}/content` 做高亮  

**常见坑**：

- Dify 返回的 chunk 与 `document_segments` 不一定逐字对齐 → MVP 用 snippet 文本模糊匹配 segment  
- 生活区无分段时 citation 只到文档级（`segment_id=null`，`char_start/end` 为空）

---

### S8 — 前端联调（VITE_API_BASE）

**目标**：Web 端走完 MVP 闭环 UI。

**前置依赖**：S4（最低）、S5–S7（完整体验）

**修改/新建文件**：

```
frontend/.env.development
frontend/.env.production
frontend/src/lib/api.ts              # VITE_API_BASE + 新 API 模块
frontend/src/lib/quizApi.ts          # 或并入 api.ts
frontend/src/types/index.ts          # Question, QuizSession, Citation
frontend/src/features/knowledge-base/
├── KnowledgeBasePage.tsx            # 分区切换、zone 标签
└── UploadPage.tsx                   # 上传时选 collection
frontend/src/features/quiz/          # 新建
├── QuizPage.tsx
└── QuizReviewPanel.tsx
frontend/src/features/chat/ChatPage.tsx   # collection 选择、citation 点击
frontend/src/features/tutor/TutorPanel.tsx
frontend/src/routes/index.tsx
```

**实现要点**：

1. **API 基址**：`import.meta.env.VITE_API_BASE`，禁止硬编码穿透域名入库  
2. 上传：`FormData` 追加 `collection_id`  
3. 刷题：题面 → 提交 → 错题侧栏展示 `citation.snippet` + 跳转文档预览  
4. 聊天：会话级 state 保存 `collectionId`；解析 SSE `citations`  
5. 文档预览：根据 `char_start/end` 高亮（`substring` + `<mark>`）  

**验收标准**：

- [ ] 本地 `npm run dev` + 本地后端完整走通 MVP 一句话  
- [ ] 切换 `VITE_API_BASE` 可连公网穿透，无需改代码  
- [ ] 主要页面 loading / error 态齐全  

**常见坑**：

- CORS：后端已 `allow_origins=["*"]`，生产需收紧  
- `api.ts` 与后端字段命名（snake_case）对齐  
- 出题异步：上传后轮询 `documents.question_gen_status` 或 `segment_status`

---

## 7. 测试清单（跨阶段）

| 场景 | 命令/操作 |
|------|-----------|
| 迁移 | `cd backend && alembic upgrade head` |
| 注册 | `POST /api/v1/auth/register` |
| 列分区 | `GET /api/v1/kb/collections` |
| 上传 | `POST /api/v1/kb/upload` + `collection_id` |
| 查段 | `GET /api/v1/kb/documents/{id}/segments` |
| 列题 | `GET /api/v1/questions?document_id=` |
| 刷题 | `POST /api/v1/quiz/sessions` → `answers` |
| 辅导 | `POST /api/v1/tutor/sessions` |
| 聊天 | `POST /api/v1/chat` + `collection_id` |

---

## 8. 与 TEAM.md / KT 的关系

- `TEAM.md` 中 Flutter 分工与 **本仓库 `frontend/` React 端** 并行存在时，以 **同一套 REST API** 为准  
- `/api/v1/kt/*` 已独立；`quiz_answers` 稳定后可把答题结果转为 KT `states` 输入（**非 MVP**）  
- 算法负责人专注 LEKT；业务刷题逻辑在 `quiz_service`，不要在 `kt.py` 里堆功能

---

## 9. 文档维护

| 事件 | 更新 |
|------|------|
| 新增端点 | `backend/docs/API.md` |
| 表结构变更 | `backend/docs/DATABASE.md` + Alembic revision |
| 阶段完成 | 本文档对应阶段验收打勾 |
| 产品范围变更 | `docs/PLAN.md` |

---

## 10. 已确认的技术决策

| 决策 | 结论 | 影响 |
|------|------|------|
| **数据库默认** | 本地统一 SQLite（`data/zhishi.db`）；团队联调再切 MySQL | S1 需改 `config.py` 默认连接串；`DATABASE.md` 为 schema 真源 |
| **全局去重** | S2 起必须上 `global_documents` 跨用户去重 | S2 models + S3 上传链路需同时实现 `global_documents` / `documents` 双表与 `content_hash` 逻辑 |

---

*文档版本：2026-07-02 · 与仓库 `backend/` + `frontend/` 结构对齐*
