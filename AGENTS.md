# Repository Guidelines

> 本文件是仓库根目录的贡献者与 Agent 入口。自然语言说明使用中文；命令、路径、接口名和代码标识保持原文。进入 `zhishi-web/` 时还须遵守其子目录 `AGENTS.md`。

## 1. 仓库定位与最短阅读路径

这是“知拾/知序”应用后端工作区，主实现位于 `zhishi-master/`，同时保留配套 Web 前端、架构方案、迁移记录和端到端验收脚本。开始任务时依次阅读：

1. 本文件与 `git status --short --branch`；
2. `zhishi-master/backend/app/api/v1/router.py`、`app/core/config.py`；
3. 与任务对应的 router、service、crud、model/schema 和测试；
4. 接口查 `backend/docs/API.md`，表结构查 `backend/docs/DATABASE.md`，开发范式查 `zhishi-master/docs/DEV_GUIDE.md`；
5. TCN 契约再查根目录 `SYSTEM_ARCHITECTURE_BRIEF.md`、`TCN_API_CONFIRMATION_REPLY.md`。

真相优先级为：当前代码与运行时 OpenAPI > 自动化测试 > `backend/docs/` > 根目录方案/迁移文档。后者可能描述目标态，不能仅凭文档宣称功能已实现。

## 2. 总体架构与运行链路

```text
React/Vite 前端
  └─ src/lib/api.ts（Bearer Token、JSON、SSE）
       └─ FastAPI :8765（backend/server.py）
            ├─ api/v1/* 路由 + deps 鉴权/DB Session
            ├─ services/* 业务编排
            │    ├─ crud/* → SQLAlchemy → SQLite/MySQL
            │    ├─ 文件解析/OCR → 分段 → Chroma 或 Dify RAG
            │    ├─ ZhishiAgent → OpenAI 兼容 LLM 接口
            │    └─ TCNClient → TCN 引擎 :8001
            └─ auth_sessions + MemoryCache + 本地文件（鉴权与运行态数据）
```

主要接缝：

- **HTTP 接口**：所有业务路由由 `app/api/v1/router.py` 聚合，并统一挂载到 `/api/v1`。
- **持久化接口**：同步 SQLAlchemy `Session`；router 注入 `get_db`，service 负责事务编排，crud 只做查询和写入。
- **检索接口**：`RAG_BACKEND=local|dify`。默认 `local` 使用 Chroma；Dify 是可替换 adapter，不要在页面或路由中直接分叉实现。
- **知识追踪接口**：`TCNClient` 通过 HTTP 调用独立 TCN 引擎。应用层展示与解释结果，不自行重算 mastery、LVR 或先修关系。
- **LLM 接口**：`ZhishiAgent` 按用户隔离实例，检索上下文后调用 LLM，并通过 SSE 输出。

## 3. 后端启动与模块地图

生产/本地运行入口是 `zhishi-master/backend/server.py:app`。其 lifespan 依次创建 ORM 表、探测 TCN、加载图谱缓存并初始化用户 Agent 池；TCN 不可达时 `/health` 仍可能以 HTTP 200 返回 `status=degraded`。`app/main.py` 是兼容/测试入口，目前 onboarding 测试使用它；不要用它替代实际启动验证。

`app/api/v1/` 的领域模块包括：

- `auth`、`plan`、`onboarding`：账号、套餐和首次引导；
- `kb`：分区、上传、解析、页面预览和文档生命周期；
- `questions`、`quiz`、`tutor`：出题、刷题会话、答案与辅导上下文；
- `chat`：会话、流式回复、citation 与可选 TCN 更新；
- `kt`：TCN 图谱、掌握度、gaps、vulnerabilities、LVR；
- `analytics`、`reports`、`training`：学习分析、报告与针对训练；
- `notes`、`dashboard`：笔记和首页聚合。

注意两个同名概念：`backend/models.py` 是旧 KT 请求模型；真正的 ORM 位于 `app/models/`，HTTP DTO 主要位于 `app/schemas/`。新增持久化模型必须在 `app/models/__init__.py` 导入，才能被 `Base.metadata.create_all()` 注册。

## 4. 核心数据流与不变量

### 鉴权

注册/登录生成不透明 Token，数据库 `auth_sessions` 仅保存 SHA-256 哈希、用户 ID 和有效期。`get_current_user` 按哈希查询持久化会话并读取当前用户，因此服务重启不会丢失有效登录态；前端 Token 存于 `localStorage`。退出登录删除当前会话，修改密码、重置密码和注销账号删除该用户全部会话。受保护路由统一使用 `get_current_active_user`，所有用户资源查询必须同时过滤当前 `user_id`。

### 文档与 RAG

上传主链路为：大小/扩展名校验 → SHA-256 → `global_documents` 全局去重 → `documents` 用户引用 → 本地原件/解析缓存 → OCR/文本解析 → 学习区分段 → 向量索引 → 状态回写。核心实现集中在 `kb_service.py`、`file_parser.py`、`segment_service.py`、`index_service.py`。`DOCUMENT_PIPELINE_ASYNC=true` 时任务在线程中运行，并使用独立 `SessionLocal`；接口返回成功不等于解析/索引完成，必须检查 status。citation 由文档、segment 和字符偏移组装。

### 对话、练习与 TCN

`chat.py` 将会话热数据写入 MemoryCache，并通过 `storage_service` 保存完整历史；`AgentManager` 为每个用户缓存 `ZhishiAgent`。Agent 从本地 Chroma 或 Dify 检索，注入上下文，调用 LLM，再输出内容与 citations。题目、刷题和辅导业务落在 SQLAlchemy 表；KT 路由使用用户 `user_hash` 调用外部 TCN。缺少 `user_hash` 应返回 503，TCN 异常与应用业务错误要分别报告。

## 5. 数据、配置与外部依赖

- 默认数据库是 `zhishi-master/data/zhishi.db`；设置 `DATABASE_URL` 可切 MySQL。当前启动仍调用 `create_all()`；Alembic 已覆盖 onboarding 和 `auth_sessions` 增量，但未覆盖其余历史表，不能假定迁移可从空库建立完整业务 schema。
- 非密钥运行参数来自 `backend/config.json`；环境变量优先覆盖相关项。密钥放在本地环境文件，参考 `backend/.env.example`。
- `LOCAL_STORAGE_DIR` 是相对当前工作目录解析的；固定从 `backend/` 启动或显式设绝对路径，避免写入不同的 `storage/`。
- 本地 RAG 默认目录为 `zhishi-master/data/chroma`，默认嵌入模型为 `BAAI/bge-small-zh-v1.5`。Dify、百度 OCR、TCN 和 LLM 都是可选/外部依赖，应为不可达、未配置和真实实现缺陷使用不同结论。
- LLM 配置实际由 `backend/tina.env` 提供 `LLM_API_KEY`、`BASE_URL`、`MODEL_NAME`；该文件不得提交。`USE_OSS=true` 的实现尚不完整，不得把它描述为已验证能力。

## 6. 前端架构

配套前端是 `zhishi-master/frontend/` 下的 React 19 + TypeScript + Vite SPA。`src/main.tsx` 挂载全局 Provider，`src/routes/index.tsx` 管理鉴权路由，`src/context/AuthContext.tsx` 管理登录态，`src/features/` 按业务页面组织。普通 HTTP、文件下载与 SSE 都应收敛到 `src/lib/api.ts`；基址使用 `VITE_API_BASE`，默认 `http://127.0.0.1:8765`。新增页面通常同步更新 route、导航、API 封装与 `src/types/`。`zhishi-web/` 是另一套前端文档子树，不要误改成这里的运行代码。

## 7. 编码与架构约束

- Python 使用 4 空格、`snake_case` 函数/模块、`PascalCase` 类；仓库未配置统一 Python formatter，遵循邻近代码。
- Router 只做参数、依赖和 HTTP 映射；可复用业务流程放 service，数据库细节放 crud。不要新增只透传调用的浅层模块。
- Pydantic request/response 与 ORM 分离；公开接口优先声明 `response_model`，错误统一为 `{"detail": "..."}`。
- 事务使用 `commit/rollback`，后台任务不得复用请求结束后关闭的 Session。
- TypeScript/TSX 使用 2 空格、`PascalCase` 组件、`useXxx` Hook、`@/` 别名和 `import type`；普通请求不要在页面中写裸 `fetch`。
- 修改接口时闭环更新 router/schema/service/crud、`backend/docs/API.md`、前端 API/types 与回归测试。修改表结构时同步 model 导出、Alembic、`DATABASE.md` 和隔离测试。

## 8. 构建、测试与本地开发

```powershell
cd zhishi-master\backend
python -m venv ..\.venv
..\.venv\Scripts\python -m pip install -r requirements.txt pytest
..\.venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8765 --reload
..\.venv\Scripts\python -m pytest tests -q

cd ..\frontend
npm ci
npm run dev
npm run lint
npm run build
npm run preview
```

后端自检：`GET http://127.0.0.1:8765/health`，部署还必须确认 `api_contract.status=ok`；OpenAPI：`http://127.0.0.1:8765/docs`。`requirements.txt` 当前未固定 pytest，因此测试环境需显式安装。前端没有 `npm test` 脚本；`npm run build` 会执行 `tsc -b && vite build`。根目录 `start_server.ps1` 使用自身目录定位后端，并在启动后校验 Onboarding 路由契约。

## 9. 测试策略

稳定 pytest 套件位于 `backend/tests/`：`test_auth_delete_account.py`、`test_onboarding.py`、`test_tcn_kt_routes.py`。测试文件和函数分别使用 `test_*.py`、`test_*`；优先采用临时 SQLite、fixture、mock 外部 adapter 和 FastAPI 依赖覆盖。新增接口至少覆盖成功、未鉴权、用户隔离和主要错误路径。`backend/test_s*.py`、其他 `backend/test_*.py` 及根目录 `test_*.py` 多是阶段验收或真实服务脚本，可能写 storage、调用模型或要求 8765 服务在线，不应混入默认单元测试命令。当前无覆盖率门槛。

## 10. Git、PR 与收尾

保护脏工作区，不回滚或格式化无关改动；暂存使用明确路径。历史目前只有初始提交，尚无稳定惯例，建议采用 `feat(backend): ...`、`fix(kb): ...`、`test(auth): ...` 等 Conventional Commits。PR 必须说明目的、架构/接口/迁移/配置影响、验证命令与结果、外部依赖未验证项，并关联 issue；前端视觉变化附截图。提交前至少运行 `git diff --check` 和与改动范围匹配的测试/构建。不得提交 `.env`、`tina.env`、密钥、日志、数据库、上传文件、向量索引或无关生成产物。
