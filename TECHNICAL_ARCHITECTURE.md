# 知拾 (Zhishi) 后端技术架构文档

> **版本**: v2.1.0  
> **最后更新**: 2026-08-01  
> **文档状态**: 活跃维护中

---

## 目录

1. [系统概述](#1-系统概述)
2. [技术栈](#2-技术栈)
3. [项目结构](#3-项目结构)
4. [分层架构](#4-分层架构)
5. [核心模块详解](#5-核心模块详解)
6. [TCN 引擎集成](#6-tcn-引擎集成)
7. [数据存储设计](#7-数据存储设计)
8. [安全设计](#8-安全设计)
9. [配置管理](#9-配置管理)
10. [启动流程](#10-启动流程)
11. [关键设计模式](#11-关键设计模式)
12. [外部依赖](#12-外部依赖)
13. [API 路由总览](#13-api-路由总览)
14. [数据模型](#14-数据模型)
15. [附录](#15-附录)

---

## 1. 系统概述

知拾 (Zhishi) 是一个基于知识追踪 (Knowledge Tracing) 的智能教育平台，核心能力包括 AI 对话辅导、知识状态追踪、个性化学习路径推荐、智能出题与刷题、错题辅导等。

系统采用 **双服务 + 松耦合** 架构：

| 服务 | 端口 | 技术栈 | 职责 |
|------|------|--------|------|
| **应用后端** | 8765 | FastAPI + SQLAlchemy + Uvicorn | 全部业务逻辑、用户管理、知识库、聊天、刷题等 |
| **TCN 引擎** | 8001 | 独立 Python 服务 | 知识追踪内核 — 掌握度计算、LVR 违反率、先修断层诊断 |

所有用户请求首先到达应用后端，应用后端按需通过 HTTP 调用 TCN 引擎获取知识状态数据。两个服务完全独立部署，通过 REST API 通信，任一服务故障不影响另一个服务的基础运行。

### 架构设计原则

- **关注点分离**：业务逻辑与算法引擎完全解耦，应用后端不实现任何追踪算法
- **优雅降级**：TCN 引擎不可达时，主流程（聊天、刷题等）不受阻断，仅知识追踪功能静默降级
- **全局去重**：文档和题目按内容哈希去重，避免多用户重复存储
- **多后端可切换**：RAG 检索、OCR、文件存储均支持多后端，通过配置切换

---

## 2. 技术栈

### 2.1 核心框架

| 类别 | 技术 | 版本 | 用途 |
|------|------|------|------|
| Web 框架 | FastAPI | 0.109.0 | API 路由、请求校验、OpenAPI 文档 |
| ASGI 服务器 | Uvicorn | 0.27.0 | 生产级 ASGI 服务器 |
| ORM | SQLAlchemy | 2.0.25 | 数据库抽象层 |
| 数据校验 | Pydantic | 2.5.3 | 请求/响应模型序列化 |
| MySQL 驱动 | PyMySQL | 1.1.0 | MySQL 连接驱动 |
| 环境变量 | python-dotenv | 1.0.1 | .env 文件加载 |

### 2.2 认证与安全

| 技术 | 版本 | 用途 |
|------|------|------|
| python-jose[cryptography] | 3.3.0 | JWT Token 签发与验证 |
| passlib[bcrypt] | 1.7.4 | 密码哈希 |
| bcrypt | >=4.0.1, <4.1 | bcrypt 哈希算法 |

### 2.3 AI / 机器学习

| 技术 | 版本 | 用途 |
|------|------|------|
| openai (SDK) | >=1.0.0 | LLM API 调用（DeepSeek） |
| sentence-transformers | >=2.2.0 | 文本向量化（BAAI/bge-small-zh-v1.5） |
| chromadb | >=0.5.0 | 本地向量数据库 |
| torch | >=1.12.0 | 深度学习推理底座 |
| PaddleOCR | >=2.7.0 | 图片/PDF OCR |

### 2.4 文档处理

| 技术 | 版本 | 用途 |
|------|------|------|
| PyMuPDF | >=1.24.0 | PDF 解析 |
| pdfplumber | >=0.11.0 | PDF 文本提取 |
| PyPDF2 | >=3.0.0 | PDF 基础操作 |
| python-docx | >=1.0.0 | Word 文档解析 |

### 2.5 HTTP 客户端

| 技术 | 版本 | 用途 |
|------|------|------|
| httpx | 0.27.0 | 异步 HTTP 客户端（TCN 通信） |
| requests | 2.31.0 | 同步 HTTP 客户端 |
| tenacity | >=8.0 | 重试机制 |

### 2.6 数据处理

| 技术 | 版本 | 用途 |
|------|------|------|
| numpy | >=1.21.0 | 数值计算 |
| scikit-learn | >=1.0.0 | 机器学习工具 |
| pandas | >=1.3.0 | 数据分析 |
| tqdm | >=4.60.0 | 进度条 |

### 2.7 LLM 配置

| 配置项 | 值 |
|--------|-----|
| LLM Provider | DeepSeek |
| API 端点 | `https://api.deepseek.com/v1/chat/completions` |
| 模型 | `deepseek-chat` |

---

## 3. 项目结构

```
zhishi-master/
├── backend/                          # 后端服务（主项目）
│   ├── server.py                     # FastAPI 应用入口 + lifespan
│   ├── config.json                   # 运行时配置
│   ├── requirements.txt              # Python 依赖
│   ├── tina.env                       # LLM 环境变量
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api/                      # API 层
│   │   │   └── v1/
│   │   │       ├── router.py         # 路由聚合
│   │   │       ├── auth.py           # 认证
│   │   │       ├── chat.py           # 聊天
│   │   │       ├── kt.py             # 知识追踪
│   │   │       ├── kb.py             # 知识库
│   │   │       ├── questions.py      # 题目
│   │   │       ├── quiz.py           # 刷题
│   │   │       ├── tutor.py          # 辅导
│   │   │       ├── training.py       # 训练
│   │   │       ├── analytics.py      # 学习分析
│   │   │       ├── reports.py        # 学习报告
│   │   │       ├── dashboard.py      # 首页
│   │   │       ├── notes.py          # 笔记
│   │   │       ├── plan.py           # 套餐
│   │   │       └── onboarding.py     # 引导
│   │   ├── core/                     # 核心层（基础设施）
│   │   │   ├── config.py             # 全局配置
│   │   │   ├── app_config.py         # config.json 读取
│   │   │   ├── database.py           # SQLAlchemy 引擎
│   │   │   ├── security.py           # JWT + bcrypt
│   │   │   ├── tcn_config.py         # TCN 连接配置
│   │   │   ├── agent_manager.py      # Agent 池管理
│   │   │   └── redis.py              # 进程内缓存
│   │   ├── services/                 # 服务层（业务逻辑）
│   │   │   ├── tcn_client.py         # TCN HTTP 客户端
│   │   │   ├── graph_cache.py        # 图谱缓存
│   │   │   ├── zhishi_agent.py       # 核心聊天 Agent
│   │   │   ├── chat_agent.py         # 聊天编排
│   │   │   ├── kb_service.py         # 知识库管理
│   │   │   ├── chroma_store.py       # 向量存储
│   │   │   ├── embedding_service.py  # 向量化
│   │   │   ├── local_retrieval_service.py  # 本地 RAG 检索
│   │   │   ├── dify_kb.py            # Dify 知识库
│   │   │   ├── ocr_service.py        # OCR 服务
│   │   │   ├── pdf_ocr_service.py    # PDF OCR
│   │   │   ├── file_parser.py        # 文档解析
│   │   │   ├── quiz_service.py       # 刷题服务
│   │   │   ├── question_gen_agent.py # 题目生成 Agent
│   │   │   ├── question_gen_service.py  # 题目生成服务
│   │   │   ├── tutor_service.py      # 辅导服务
│   │   │   ├── training_agent.py     # 训练 Agent
│   │   │   ├── training_service.py   # 训练服务
│   │   │   ├── training_tools.py     # 训练工具
│   │   │   ├── kt_service.py         # 知识追踪服务
│   │   │   ├── report_service.py     # 报告服务
│   │   │   ├── analytics_service.py  # 学习分析服务
│   │   │   ├── onboarding_service.py # 引导服务
│   │   │   ├── auth_service.py       # 认证服务
│   │   │   ├── llm_runner.py         # LLM 执行器
│   │   │   ├── segment_service.py    # 分段服务
│   │   │   ├── storage_service.py    # 文件存储
│   │   │   ├── citation_service.py   # 引用服务
│   │   │   ├── index_service.py      # 索引服务
│   │   │   ├── page_service.py       # 页面服务
│   │   │   ├── ocr_progress.py       # OCR 进度追踪
│   │   │   └── question_hash.py      # 题目哈希
│   │   ├── models/                   # 数据模型层（ORM）
│   │   │   ├── __init__.py           # 模型注册
│   │   │   ├── models.py             # User, PlanTier
│   │   │   ├── kb.py                 # 知识库模型
│   │   │   ├── quiz.py               # 题目模型
│   │   │   ├── quiz_session.py       # 刷题会话模型
│   │   │   ├── tutor.py              # 辅导模型
│   │   │   ├── tag.py                # 标签模型
│   │   │   ├── note.py               # 笔记模型
│   │   │   ├── training_plan.py      # 训练计划模型
│   │   │   ├── onboarding.py         # 引导状态模型
│   │   │   └── tcn_schemas.py        # TCN 数据模式
│   │   ├── schemas/                  # Pydantic 模型
│   │   ├── crud/                     # 数据库操作封装
│   │   └── ...
│   ├── storage/                      # 用户上传文件
│   └── data/                         # 数据库 + 向量库
│       ├── zhishi.db                 # SQLite 数据库
│       └── chroma/                   # Chroma 向量库
├── frontend/                         # 前端项目
├── data/                             # 全局数据
├── docs/                             # 项目文档
└── README.md
```

---

## 4. 分层架构

后端采用经典的 **四层架构**，职责严格分离：

```
┌─────────────────────────────────────────────────────────┐
│                    客户端请求                             │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  API Layer (app/api/v1/)                                 │
│  14 个 FastAPI Router — 参数校验、认证、调用 Service      │
│  不包含业务逻辑                                           │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Service Layer (app/services/)                           │
│  32 个服务模块 — 全部业务逻辑                             │
│  TCN 通信、LLM 编排、RAG 检索、OCR、文档处理等           │
└──────────┬──────────────────────────┬───────────────────┘
           ▼                          ▼
┌─────────────────────┐  ┌──────────────────────────────┐
│  Core Layer          │  │  Data Layer                  │
│  (app/core/)         │  │  (app/models + crud +        │
│  配置、数据库、安全、  │  │   schemas)                   │
│  Agent管理、缓存      │  │  16 张 ORM 表、CRUD 封装、    │
│                      │  │  Pydantic 序列化模型          │
└─────────────────────┘  └──────────────────────────────┘
           │                          │
           ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│  外部系统                                                │
│  SQLite/MySQL · Chroma · TCN 引擎 · DeepSeek API ·      │
│  Dify API · 百度 OCR · SMTP                              │
└─────────────────────────────────────────────────────────┘
```

### 层间依赖规则

- **API → Service → Core / Data**：单向依赖，不允许反向调用
- **Service 之间**：允许互相调用（如 `chat_agent` 调用 `tcn_client` 和 `local_retrieval_service`）
- **Core 层**：不依赖 Service 和 API，只提供基础设施
- **Data 层**：ORM 模型不包含业务逻辑，CRUD 只做数据库读写

---

## 5. 核心模块详解

### 5.1 API 层（`app/api/v1/`）

14 个路由模块，统一挂在 `/api/v1` 前缀下，由 `router.py` 聚合注册。每个模块是一个 FastAPI `APIRouter`，只负责参数校验、认证检查和调用 Service 层。

**设计特点**：
- 每个路由函数通过 `Depends(get_current_user)` 注入当前用户
- 请求/响应使用 Pydantic Schema 校验
- 不包含任何数据库直接操作或业务判断逻辑

### 5.2 Service 层（`app/services/`）

32 个服务模块承载全部业务逻辑。以下为关键服务说明：

#### tcn_client.py — TCN 引擎 HTTP 客户端

这是应用后端与 TCN 引擎通信的唯一入口，采用 **单例模式**。

```python
class TCNClient:
    """单例模式，全局唯一实例"""
    
    # 重试机制
    # - 最多重试 2 次（共 3 次尝试）
    # - 每次重试间隔 1 秒
    # - 3 次全部失败 → _enabled = False（服务降级）
    # - 任意一次成功 → _enabled = True（自动恢复）
```

**用户哈希生成**：
```python
user_hash = sha256(f"{user_id}:{TCN_SECRET_SALT}")[:32]
```
后端不向 TCN 传递真实用户 ID，而是使用 SHA-256 哈希，保护用户隐私。

**降级策略**：每个 TCN 接口调用都有对应的 `fallback` 默认返回值（如 `lvr=0`, `mastery=0.5`），TCN 不可达时主流程不受阻断。

#### graph_cache.py — 图谱缓存

启动时从 TCN 全量拉取知识图谱（503 节点 + 边关系），缓存为内存中的 dict：

```python
{
    "math:addition": {
        "name": "加法",
        "parents": ["math:arithmetic"],        # 先修节点
        "dependents": ["math:multiplication"]   # 后继节点
    },
    ...
}
```

后续所有图谱查询都是 O(1) 内存读取，无需再次请求 TCN。

#### zhishi_agent.py — 核心聊天 Agent

负责组装 LLM 对话的完整上下文：
1. 构建 System Prompt（含角色设定 + 知识状态注入）
2. RAG 检索相关知识片段
3. 调用 LLM（DeepSeek）生成回答
4. SSE 流式返回

#### kb_service.py — 知识库管理

完整文档处理管道：
```
上传 → 文件解析 → 分段 → 向量化 → 存储
              ↘ OCR（如需要）
```

支持同步和异步两种模式，由 `config.json` 的 `document_pipeline_async` 控制。

#### chroma_store.py + embedding_service.py — 本地向量检索

- **Embedding 模型**：`BAAI/bge-small-zh-v1.5`（sentence-transformers）
- **向量数据库**：Chroma（本地持久化，`data/chroma/`）
- 可切换为 Dify 云端知识库（`RAG_BACKEND=dify`）

### 5.3 Core 层（`app/core/`）

#### config.py — 全局配置

配置优先级（从高到低）：
```
环境变量 (os.getenv) > config.json (AppConfig) > 硬编码默认值
```

启动时执行 `dotenv.load_dotenv()` 加载 `.env` 文件，再通过 `get_app_config()` 读取 `config.json`。

#### database.py — 数据库引擎

- **ORM**：SQLAlchemy 2.0.25，`declarative_base()` 模式
- **Session**：`sessionmaker(autocommit=False, autoflush=False)`
- **SQLite**：`check_same_thread=False`，启动时 `PRAGMA foreign_keys=ON`
- **MySQL**：`pool_recycle=3600`（连接池 1 小时回收）
- **建表**：`Base.metadata.create_all(bind=engine)`（S1 阶段，后续迁移至 Alembic）

#### security.py — 认证与密码

- **JWT**：HS256 签名，7 天有效期，`python-jose` 实现
- **密码哈希**：bcrypt（`2b` 版本标识），密码截断为前 72 字符（bcrypt 限制）

#### agent_manager.py — Agent 池管理

- `user_id → ZhishiAgent` 映射，用户隔离
- 懒加载：首次访问时创建
- 线程安全：`threading.Lock()`
- 自动清理：1 小时未活动的 Agent 被回收
- 知识库变更检测：dataset_id 变化时自动重建

#### redis.py — 进程内缓存

虽然文件名为 `redis.py`，实际是进程内内存缓存（`MemoryCache` 类），非真正的 Redis：
- 键值存储 + TTL 过期
- 列表操作（lpush/rpush/lrange/lrem）
- 模式扫描（`scan_keys` 支持 glob）
- 用途：auth token session、验证码、聊天历史

### 5.4 Data 层

#### ORM 模型（16 张表）

详见 [第 14 节：数据模型](#14-数据模型)。

#### CRUD 层

8 个模块封装数据库读写操作，Service 层通过 CRUD 层访问数据库，不直接操作 Session。

#### Schemas 层

11 个 Pydantic 模型模块，负责请求参数校验和响应序列化。

#### Alembic 迁移

当前 S1 阶段使用 `create_all` 自动建表，后续团队协作环境迁移至 Alembic 管理。

---

## 6. TCN 引擎集成

### 6.1 架构定位

TCN (Temporal Cognitive Network) 是独立部署的知识追踪算法服务，应用后端不实现任何追踪算法，全部通过 HTTP 调用 TCN。

```
┌──────────────────┐         HTTP          ┌──────────────────┐
│   应用后端        │ ──────────────────▶   │   TCN 引擎        │
│   (port 8765)    │   REST API            │   (port 8001)    │
│                  │ ◀──────────────────   │                  │
│  tcn_client.py   │   JSON 响应           │  知识追踪内核     │
└──────────────────┘                       └──────────────────┘
```

### 6.2 TCN 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `TCN_BASE_URL` | `http://127.0.0.1:8001` | TCN 引擎地址 |
| `TCN_ADMIN_TOKEN` | (空) | 管理 Token |
| `TCN_TIMEOUT` | 5 秒 | HTTP 请求超时 |
| `TCN_MAX_RETRIES` | 2 | 最大重试次数 |
| `TCN_ENABLED` | true | 是否启用 |
| `TCN_SECRET_SALT` | `zhixu-tcn-salt-2026` | 用户哈希盐值 |

### 6.3 TCN API 接口

| 方法 | HTTP | 端点 | 说明 | 降级返回 |
|------|------|------|------|----------|
| `health_check()` | GET | `/health` | 探测可用性 | — |
| `predict()` | POST | `/v1/user/predict` | 更新知识状态 | `lvr=0, mastery=0.5` |
| `get_profile()` | GET | `/v1/user/profile/{hash}` | 知识追踪概况 | 空字典 |
| `get_report()` | GET | `/v1/user/report/{hash}` | 学习报告 | 空字典（404 不重试） |
| `get_summary()` | GET | `/v1/user/summary/{hash}` | 知识状态摘要 | 空字典 |
| `get_gaps()` | GET | `/v1/user/gaps/{hash}` | 先修断层查询 | 空列表 |
| `get_vulnerabilities()` | GET | `/v1/user/vulnerabilities/{hash}` | 认知脆弱点 | 空列表 |
| `get_lvr_alert()` | GET | `/v1/user/lvr_alert/{hash}` | LVR 预警 | 空列表 |
| `get_graph_domains()` | GET | `/admin/graph/domains` | 图谱域列表 | 空列表 |
| `get_graph_data()` | GET | `/admin/graph/data/{domain}` | 图谱数据 | 空字典 |

### 6.4 Chat 对话中的 TCN 交互时序

```
客户端                     应用后端                         TCN 引擎                   LLM (DeepSeek)
  │                          │                                │                          │
  │  POST /chat (SSE)        │                                │                          │
  │ ──────────────────────▶  │                                │                          │
  │                          │                                │                          │
  │                          │  并行拉取:                      │                          │
  │                          │  ┌─ get_summary(user_hash)  ──▶ │                          │
  │                          │  ├─ get_gaps(user_hash)      ──▶ │                          │
  │                          │  └─ get_vulnerabilities()    ──▶ │                          │
  │                          │                                │                          │
  │                          │  构建 System Prompt ◀─────────── │                          │
  │                          │  (注入知识状态)                  │                          │
  │                          │                                │                          │
  │                          │  RAG 检索相关知识片段             │                          │
  │                          │ ───────────────────────────────────────────────────────▶ │
  │                          │                                │                          │
  │  SSE: 流式回答           │ ◀──────────────── 流式 Token ──────────────────────────── │
  │ ◀──────────────────────  │                                │                          │
  │                          │                                │                          │
  │                          │  对话后（如有 tc_node_id）:      │                          │
  │                          │  POST /predict ─────────────▶  │                          │
  │                          │  (更新知识状态)                  │                          │
  │                          │ ◀── LVR + 诊断信息 ──────────── │                          │
  │                          │                                │                          │
  │  SSE: 最终事件 (LVR)     │                                │                          │
  │ ◀──────────────────────  │                                │                          │
  │                          │                                │                          │
```

**关键点**：
- **对话前**：并行拉取 TCN 的 summary、gaps、vulnerabilities，注入 LLM System Prompt
- **对话中**：SSE 流式返回 LLM 回答
- **对话后**：如请求携带 `tc_node_id` + `tc_user_action`，异步调用 `POST /predict` 更新知识状态，返回 LVR + 诊断信息

### 6.5 降级机制

```
TCN 不可达
    │
    ▼
tcn_client._enabled = False
    │
    ├── Chat: 继续工作，System Prompt 不含知识状态（正常聊天，无个性化）
    ├── KT 接口: 返回默认值 (lvr=0, mastery=0.5)
    ├── Graph Cache: 保持上次缓存（如有），否则空字典
    └── 主流程: 不阻断
    │
    ▼
TCN 恢复
    │
    ▼
下次调用成功 → _enabled = True（自动恢复）
```

---

## 7. 数据存储设计

### 7.1 存储总览

| 存储类型 | 用途 | 技术 | 位置 |
|----------|------|------|------|
| 关系数据库 | 用户、文档、题目、刷题记录等结构化数据 | SQLite（默认）/ MySQL | `data/zhishi.db` |
| 向量数据库 | RAG 检索 — 文档分段向量索引 | Chroma / Dify | `data/chroma/` |
| 文件存储 | 用户上传的原始文件 | 本地 `storage/` / OSS | `backend/storage/` |
| 内存缓存 | 热数据（会话、图谱缓存等） | 进程内 dict（MemoryCache） | 进程内存 |
| 图谱缓存 | 知识图谱节点+关系 | 进程内 dict | 进程内存 |

### 7.2 关系数据库

**SQLite（默认）**：
- 连接串：`sqlite:///{REPO_ROOT}/data/zhishi.db`
- `check_same_thread=False`（允许跨线程）
- `PRAGMA foreign_keys=ON`（启用外键约束）

**MySQL（可选）**：
- 连接串：`mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}`
- `pool_recycle=3600`（1 小时连接回收）

切换方式：设置环境变量 `DATABASE_URL`。

### 7.3 向量数据库

**本地模式（`RAG_BACKEND=local`）**：
- 引擎：Chroma
- Embedding 模型：`BAAI/bge-small-zh-v1.5`
- 持久化目录：`data/chroma/`

**Dify 模式（`RAG_BACKEND=dify`）**：
- 引擎：Dify 云端知识库
- Embedding 模型：`multimodal-embedding-v1`（通义）
- Reranking 模型：`gte-rerank`（通义）
- API 端点：`https://api.dify.ai/v1`

### 7.4 文件存储

**本地模式（`USE_OSS=false`）**：
- 根目录：`backend/storage/`
- 按 `user_id` 分子目录存储

**OSS 模式（`USE_OSS=true`）**：
- 切换为阿里云 OSS

---

## 8. 安全设计

### 8.1 认证机制

```
用户登录 → 验证密码 (bcrypt) → 签发 JWT (HS256, 7天有效)
                                         │
                                         ▼
                              后续请求 Header: Authorization: Bearer <token>
                                         │
                                         ▼
                              get_current_user() → 解析 JWT → 查询用户
```

| 配置项 | 值 |
|--------|-----|
| 签名算法 | HS256 |
| 密钥来源 | `config.SECRET_KEY`（环境变量） |
| Token 有效期 | 7 天（`60 * 24 * 7` 分钟） |
| 密码哈希 | bcrypt（`2b` 标识） |
| 密码截断 | 前 72 字符（bcrypt 限制） |

### 8.2 用户隐私保护

- 向 TCN 引擎传递的 user_id 使用 SHA-256 哈希 + 盐值，不暴露真实用户 ID
- 密码以 bcrypt 哈希存储，不存储明文
- JWT Token 不包含敏感信息，仅含 `sub`（用户 ID）和 `exp`（过期时间）

### 8.3 CORS 配置

```python
CORSMiddleware(
    allow_origins=["*"],      # 当前允许所有来源（生产环境需收紧）
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 8.4 邮件验证

- 邮箱验证码有效期：15 分钟
- 密码重置链接有效期：30 分钟
- SMTP 服务器：`smtp.gmail.com:587`

---

## 9. 配置管理

### 9.1 配置优先级

```
环境变量 (.env)  >  config.json (AppConfig)  >  硬编码默认值
     最高优先级        运行时可调              兜底
```

### 9.2 config.json

文件位置：`backend/config.json`（优先）或 `{REPO_ROOT}/config.json`（回退）

```json
{
  "ocr_max_parallel_pages": 1,
  "pdf_ocr_max_pages": 50,
  "pdf_max_pages": 0,
  "pdf_ocr_render_dpi": 150,
  "max_questions_per_document": 20,
  "document_pipeline_async": true,
  "question_gen_async": true,
  "llm_async": true,
  "image_ocr_async": true,
  "upload_max_size_mb": 0,
  "ocr_backend": "local",
  "ocr_pages_dir_name": "pages"
}
```

### 9.3 核心配置项速查

| 配置项 | 默认值 | 来源 | 说明 |
|--------|--------|------|------|
| `SECRET_KEY` | `"your-very-secret-key"` | 环境变量 | JWT 签名密钥 |
| `ALGORITHM` | `"HS256"` | 环境变量 | JWT 签名算法 |
| `DATABASE_URL` | SQLite 路径 | 环境变量 | 数据库连接串 |
| `RAG_BACKEND` | `local` | 环境变量 | RAG 后端：local / dify |
| `OCR_BACKEND` | `local` | 环境变量 > config.json | OCR 后端：local / baidu / auto |
| `USE_OSS` | `false` | 环境变量 | 文件存储：本地 / OSS |
| `CHROMA_PERSIST_DIR` | `data/chroma` | 环境变量 | Chroma 持久化目录 |
| `EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 环境变量 | 向量化模型 |
| `DOCUMENT_PIPELINE_ASYNC` | `true` | 环境变量 > config.json | 文档处理异步模式 |
| `TCN_BASE_URL` | `http://127.0.0.1:8001` | 环境变量 | TCN 引擎地址 |
| `TCN_ENABLED` | `true` | 环境变量 | 是否启用 TCN |
| `TCN_TIMEOUT` | 5 | 环境变量 | TCN 请求超时（秒） |
| `FRONTEND_URL` | `http://localhost:3000` | 环境变量 | 前端地址（CORS/邮件链接） |

---

## 10. 启动流程

### 10.1 Lifespan 启动序列

`server.py` 使用 FastAPI 的 lifespan 机制，按顺序执行：

```
应用启动
  │
  ├─ 1. init_db()
  │     ├── 导入 app.models 注册所有 ORM 模型
  │     ├── Base.metadata.create_all(bind=engine)  →  自动建表
  │     └── SQLite: PRAGMA foreign_keys=ON
  │
  ├─ 2. tcn_client.health_check()
  │     ├── 探测 TCN 引擎: GET http://127.0.0.1:8001/health
  │     ├── 成功 → app.state.tcn_healthy = True
  │     └── 失败 → app.state.tcn_healthy = False (降级模式)
  │
  ├─ 3. init_graph_cache()
  │     ├── 检查 tcn_client.is_enabled
  │     ├── 拉取所有域: tcn_client.get_graph_domains()
  │     ├── 逐域拉取图谱: tcn_client.get_graph_data(domain)
  │     └── 构建缓存: {node_id → {name, parents, dependents}}
  │         └── 503 节点 + 先修/后继关系
  │
  ├─ 4. AgentManager()
  │     └── 初始化用户 Agent 池管理器
  │
  └─ (yield)  →  应用开始接收请求
  
  ... 应用运行期 ...

  应用关闭
  │
  └─ 5. tcn_client.close()
        └── 关闭 httpx AsyncClient
```

### 10.2 降级处理

| 启动步骤 | 失败后果 | 处理方式 |
|----------|----------|----------|
| init_db() | 应用无法启动 | 抛出异常，终止 |
| TCN health_check() | 知识追踪功能不可用 | `tcn_healthy=False`，主流程继续 |
| init_graph_cache() | 图谱查询返回空 | 保留空字典，KT 接口返回默认值 |
| AgentManager() | 聊天功能不可用 | `agent_manager=None`，Chat 接口返回 503 |

### 10.3 全局异常处理

- `HTTPException`：由 FastAPI 直接处理，返回对应状态码
- 其他未捕获异常：返回 500 JSON：`{"detail": "服务器内部错误，请稍后重试"}`

---

## 11. 关键设计模式

### 11.1 全局去重

文档和题目通过内容哈希在全局表中去重，多用户上传同一内容不会重复存储：

- **文档去重**：`content_hash` 字段在 `global_documents` 表唯一
- **题目去重**：`content_hash` 字段在 `global_questions` 表唯一
- **用户关联**：通过 `user_document_refs` / `user_question_refs` 关联表建立多对多关系

### 11.2 多后端可切换

| 子系统 | 后端选项 | 切换方式 |
|--------|----------|----------|
| RAG 检索 | Chroma（本地）/ Dify（云端） | `RAG_BACKEND` 环境变量 |
| OCR | PaddleOCR（本地）/ 百度 OCR / 自动 | `OCR_BACKEND` 环境变量 |
| 文件存储 | 本地 `storage/` / 阿里云 OSS | `USE_OSS` 环境变量 |
| 数据库 | SQLite / MySQL | `DATABASE_URL` 环境变量 |

### 11.3 异步处理管道

文档处理管道支持同步和异步两种模式：

```
上传 → 文件解析 → 分段 → 向量化 → 出题
         ↘ OCR（如需要）
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `document_pipeline_async` | true | 文档处理管道异步 |
| `question_gen_async` | true | 题目生成异步 |
| `llm_async` | true | LLM 调用异步 |
| `image_ocr_async` | true | 图片 OCR 异步 |

### 11.4 套餐体系

4 级套餐（level 0-3），控制资源配额：

| 限制项 | 说明 |
|--------|------|
| API 日限额 | 每日 API 调用次数上限 |
| Token 月限额 | 每月 LLM Token 消耗上限 |
| 知识库数量 | 可创建的知识库数量上限 |
| 可用 LLM 模型 | 不同套餐可使用的 LLM 模型范围 |

### 11.5 单例模式

`TCNClient` 使用 `__new__` + `_initialized` 标志实现单例，全局唯一实例，避免重复创建 HTTP 客户端连接池。

### 11.6 用户级 Agent 隔离

`AgentManager` 按 `user_id` 管理 Agent 实例：
- 同一用户的多个请求共享同一个 Agent（会话连续性）
- 不同用户的 Agent 完全隔离（数据安全）
- 知识库变更时自动重建 Agent（数据一致性）

---

## 12. 外部依赖

### 12.1 外部服务

| 服务 | 地址 | 用途 | 超时 |
|------|------|------|------|
| TCN 引擎 | `http://127.0.0.1:8001` | 知识追踪算法 | 5 秒 |
| DeepSeek API | `https://api.deepseek.com/v1/chat/completions` | LLM 对话 | — |
| Dify API | `https://api.dify.ai/v1` | 知识库管理（可选） | — |
| 百度 OCR | `https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic` | OCR（可选） | — |
| SMTP | `smtp.gmail.com:587` | 邮件发送 | — |

### 12.2 依赖关系图

```
                    ┌─────────────┐
                    │  应用后端    │
                    │  (port 8765)│
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┬─────────────┐
           │               │               │             │
           ▼               ▼               ▼             ▼
    ┌─────────────┐ ┌─────────────┐ ┌──────────┐ ┌──────────┐
    │  TCN 引擎   │ │ DeepSeek API│ │ Dify API │ │   SMTP   │
    │ (port 8001) │ │  (LLM)      │ │ (可选)   │ │ (邮件)   │
    └─────────────┘ └─────────────┘ └──────────┘ └──────────┘
           │
           ▼
    ┌─────────────┐
    │  知识图谱    │
    │ 503 节点    │
    └─────────────┘
```

### 12.3 百度 OCR 配置

配置文件位置：`zhishi_app/assets/config/baidu_ocr.json`

支持通过环境变量覆盖 JSON 文件中的配置。

---

## 13. API 路由总览

所有业务路由统一挂在 `/api/v1` 前缀下。

| 模块 | 路径前缀 | 功能描述 |
|------|---------|----------|
| auth | `/api/v1/auth` | 注册、登录、JWT、邮箱验证、密码重置、注销 |
| plan | `/api/v1/plan` | 用户套餐管理 |
| chat | `/api/v1/chat` | SSE 流式聊天，集成 TCN predict |
| kt | `/api/v1/kt` | 知识追踪（图谱、学习路径、断层、脆弱点、LVR预警） |
| kb | `/api/v1/kb` | 知识库管理（分区、上传、分段、向量化） |
| dashboard | `/api/v1/dashboard` | 首页个性化建议 |
| questions | `/api/v1/questions` | AI 出题、教材题目提取 |
| quiz | `/api/v1/quiz` | 刷题会话、提交答案、错题汇总 |
| tutor | `/api/v1/tutor` | 苏格拉底式错题辅导 |
| training | `/api/v1/training` | 薄弱环节针对训练 |
| analytics | `/api/v1/analytics` | 学习数据统计 |
| reports | `/api/v1/reports` | LLM 学习报告生成 |
| notes | `/api/v1/notes` | 用户笔记 CRUD |
| onboarding | `/api/v1/onboarding` | 新用户 5 步引导 |

### 系统路由

| 路由 | 方法 | 响应 |
|------|------|------|
| `/` | GET | `{"service": "知拾 KT 后端", "version": "2.1.0", "status": "running"}` |
| `/health` | GET | `{"status": "ok"|"degraded", "skills_count": N, "model_loaded": bool}` |

---

## 14. 数据模型

### 14.1 ORM 模型总览（16 张表）

| 模型类 | 文件 | 说明 | 关键字段 |
|--------|------|------|----------|
| `User` | `models.py` | 用户 | email, password_hash, plan_level, tcn_user_hash, dify_dataset_id |
| `PlanTier` | `models.py` | 套餐等级 | level, price, api_daily_limit, token_monthly_limit, max_kb_count |
| `KbCollection` | `kb.py` | 知识库收藏集 | user_id, name, description |
| `GlobalDocument` | `kb.py` | 全局文档（去重） | content_hash, title, total_segments |
| `Document` | `kb.py` | 用户文档 | user_id, global_doc_id, kb_collection_id |
| `DocumentSegment` | `kb.py` | 文档分段 | global_doc_id, segment_index, content, embedding_id |
| `GlobalQuestion` | `quiz.py` | 全局题目（去重） | content_hash, content, answer, question_type |
| `QuestionProvenance` | `quiz.py` | 题目出处 | question_id, source_type, source_id |
| `UserQuestionRef` | `quiz.py` | 用户-题目关联 | user_id, question_id, is_favorite, is_wrong |
| `QuizSession` | `quiz_session.py` | 刷题会话 | user_id, started_at, ended_at, total_count |
| `QuizSessionQuestion` | `quiz_session.py` | 会话题目 | session_id, question_id, sequence |
| `QuizAnswer` | `quiz_session.py` | 答题记录 | session_question_id, user_answer, is_correct, time_spent |
| `TutorSession` | `tutor.py` | 辅导会话 | user_id, question_id, started_at |
| `QuestionTag` | `tag.py` | 题目标签 | name, color |
| `UserNote` | `note.py` | 用户笔记 | user_id, title, content, related_type, related_id |
| `TrainingPlan` | `training_plan.py` | 训练计划 | user_id, node_ids, status, created_at |
| `OnboardingState` | `onboarding.py` | 引导状态 | user_id, current_step, completed_steps |

### 14.2 核心关系

```
User ──1:N── Document ──N:1── GlobalDocument ──1:N── DocumentSegment
  │                                                         │
  │──1:N── QuizSession ──1:N── QuizSessionQuestion ──N:1── GlobalQuestion
  │                                       │
  │──1:N── QuizAnswer                     └── QuizAnswer
  │
  │──1:N── TutorSession ──N:1── GlobalQuestion
  │
  │──1:N── TrainingPlan
  │
  │──1:N── UserNote
  │
  │──1:1── OnboardingState
  │
  └──N:1── PlanTier
```

### 14.3 全局去重设计

```
用户 A 上传文档 X ──▶ content_hash = "abc123"
用户 B 上传文档 X ──▶ content_hash = "abc123" (相同)

GlobalDocument 表: 只存一份 (content_hash 唯一约束)
Document 表: 
  ├── 用户 A → global_doc_id = X
  └── 用户 B → global_doc_id = X
```

题目同理，`GlobalQuestion` 按 `content_hash` 去重，`UserQuestionRef` 建立用户与题目的多对多关系。

---

## 15. 附录

### 15.1 开发环境

| 项目 | 值 |
|------|-----|
| Python | 3.12+ |
| 启动命令 | `python server.py` 或 `uvicorn server:app --host 127.0.0.1 --port 8765` |
| 默认端口 | 8765 |
| 数据库 | SQLite (`data/zhishi.db`) |
| 向量库 | Chroma (`data/chroma/`) |
| TCN 引擎 | `http://127.0.0.1:8001` |

### 15.2 文件索引

| 文件 | 说明 |
|------|------|
| `backend/server.py` | 应用入口、lifespan、中间件 |
| `backend/config.json` | 运行时配置 |
| `backend/tina.env` | LLM 环境变量 |
| `backend/requirements.txt` | Python 依赖 |
| `backend/app/core/config.py` | 全局配置定义 |
| `backend/app/core/database.py` | 数据库引擎 |
| `backend/app/core/security.py` | JWT + 密码哈希 |
| `backend/app/core/tcn_config.py` | TCN 连接配置 |
| `backend/app/core/agent_manager.py` | Agent 池管理 |
| `backend/app/core/redis.py` | 进程内缓存 |
| `backend/app/services/tcn_client.py` | TCN HTTP 客户端 |
| `backend/app/services/graph_cache.py` | 图谱缓存 |
| `backend/app/services/zhishi_agent.py` | 核心聊天 Agent |
| `backend/app/api/v1/router.py` | 路由聚合 |
| `backend/app/models/__init__.py` | ORM 模型注册 |

### 15.3 术语表

| 术语 | 全称 | 说明 |
|------|------|------|
| TCN | Temporal Cognitive Network | 时序认知网络，知识追踪算法引擎 |
| LVR | Learning Violation Rate | 学习违反率，衡量跳过先修知识的程度 |
| KT | Knowledge Tracing | 知识追踪 |
| RAG | Retrieval-Augmented Generation | 检索增强生成 |
| SSE | Server-Sent Events | 服务器推送事件 |
| OCR | Optical Character Recognition | 光学字符识别 |
| ORM | Object-Relational Mapping | 对象关系映射 |
| JWT | JSON Web Token | JSON Web 令牌 |

---

> **文档维护说明**：本文档随系统迭代持续更新。如发现信息过时或有遗漏，请联系开发团队修正。
