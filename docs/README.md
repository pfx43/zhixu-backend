# 知序（Zhixu）文档索引

> 文档按主题分类存放，命名规范：英文小写 + 下划线（snake_case）。
> 新文档请按类别放入对应目录并在此登记。

## 📖 分类总览

| 目录 | 主题 |
|---|---|
| [`design/`](design/) | 这一期认领、功能更新、设计稿（从这里进） |
| [`api/`](api/) | 接口对接文档 |
| [`architecture/`](architecture/) | 架构与实现 |
| [`development/`](development/) | 开发协作规范 |
| [`deploy/`](deploy/) | 部署与安全 |
| [`features/`](features/) | 功能方案与实施 |
| [`plans/`](plans/) | 计划与 Backlog |
| [`agents/`](agents/) | Agent 相关 |

## 📄 文档清单

## 这一期认领（design/）

先打开 [design/index.md](design/index.md)，再按人进罗洁 / 张子麟 / 陈勇搏 / 彭飞翔。TCN 接入见 [design/TCN集成.md](design/TCN集成.md)。

### 接口对接（api/）
| 文件 | 说明 |
|---|---|
| [api_overview.md](api/api_overview.md) | 后端 API 总览 |
| [chat_sse_frontend_reference.md](api/chat_sse_frontend_reference.md) | Chat 流式接口（SSE）前端接入参考：type 事件、工具映射、break 打断、历史合同 |
| [notes_frontend_guide.md](api/notes_frontend_guide.md) | 笔记功能前端对接 |
| [account_delete_guide.md](api/account_delete_guide.md) | 账号注销接口对接 |
| [TCN_API_对接文档.md](api/TCN/TCN_API_对接文档.md) | TCN 引擎对接（predict / 画像；Learning OS 不要当知序任务） |
| [tcn-knowledge-tags.md](api/TCN/tcn-knowledge-tags.md) | 按领域抽出的知识点 tag（higher_math / math / physics / discrete_math） |

### 架构与实现（architecture/）
| 文件 | 说明 |
|---|---|
| [multi_user_implementation_guide.md](architecture/multi_user_implementation_guide.md) | 生产多用户改造实现指南（可派工手册） |
| [implementation.md](architecture/implementation.md) | 分阶段实现说明 |
| [database.md](architecture/database.md) | 数据库设计（schema 真源） |

### 开发协作规范（development/）
| 文件 | 说明 |
|---|---|
| [dev_guide.md](development/dev_guide.md) | 开发指南 |
| [git_workflow.md](development/git_workflow.md) | Git 协作规范 |
| [team_roles.md](development/team_roles.md) | 团队分工 |
| [team.md](development/team.md) | 团队说明 |

### 部署与安全（deploy/）
| 文件 | 说明 |
|---|---|
| [deploy.md](deploy/deploy.md) | 部署指南 |
| [defense.md](deploy/defense.md) | 安全防御 |

### 功能方案（features/）
| 文件 | 说明 |
|---|---|
| [onboarding_plan.md](features/onboarding_plan.md) | 新用户引导功能方案 |
| [onboarding_implementation.md](features/onboarding_implementation.md) | 新用户引导实施说明 |

### 计划与 Backlog（plans/）
| 文件 | 说明 |
|---|---|
| [plan.md](plans/plan.md) | 工程化设计文档 |
| [ui_ux_backlog.md](plans/ui_ux_backlog.md) | UI/UX Backlog |

## 📌 根目录文件

- [欢迎使用知序.md](欢迎使用知序.md) — 产品欢迎文档（`config.py` 的 `WELCOME_DOC_PATH` 引用，请勿移动/改名）
