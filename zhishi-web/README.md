# 知序 Web 前端

知序 Web 是基于 Vite + React + TypeScript 的个人知识管理与学习辅助工作台。当前仓库重点承载个人 Web 前端，包括登录、AI 对话、笔记、知识库、上传、知识图谱、学习分析、学习路径、提醒、画像、设置和诊断等页面。

完整产品需求见 `docs/1.产品需求文档.md`。当前 Web 前端只是产品体系中的一个实现端，不等同于机构端、公益版、学校管理端或家长端的完整实现。

## 当前状态

- 技术栈：Vite 7、React 19、TypeScript 5.9、React Router 6。
- 样式系统：Tailwind CSS、CSS 变量、Radix UI/shadcn 风格组件、lucide-react。
- API 边界：`src/lib/api` 统一维护 base URL、Token、JSON/FormData、SSE、错误归一化和端点封装。
- 鉴权边界：`src/lib/auth/AuthContext.tsx` 管理 Token、本地恢复、当前用户、登录、注册、登出和资料更新。
- 页面状态：真实 API、`src/data` 静态样例和页面本地状态仍处于混合阶段。

## 安装

```powershell
npm install
```

CI 或干净环境复现依赖时使用：

```powershell
npm ci
```

## 开发

```powershell
npm run dev
```

默认访问：

```text
http://localhost:5173/
```

如果端口被占用，以 Vite 终端输出为准。

## 构建、预览和验证

```powershell
npm run build
npm run preview
npm run lint
npm run test
```

命令含义：

| 命令 | 作用 |
| --- | --- |
| `npm run dev` | 启动 Vite 开发服务器 |
| `npm run build` | 执行 `tsc -b && vite build` |
| `npm run preview` | 预览 `dist/` 构建产物 |
| `npm run lint` | 执行 ESLint |
| `npm run test` | 执行 Vitest |

建议验证范围：

- 只改文档：运行 `git diff --check` 并检查文档路径。
- 改页面或组件：运行 `npm run lint`，必要时运行 `npm run build`。
- 改路由或构建配置：运行 `npm run build`。
- 改 `src/lib/api` 或 `src/lib/auth`：运行 `npm run test`，必要时运行 `npm run build`。

## 环境变量

| 变量 | 说明 | 示例 |
| --- | --- | --- |
| `VITE_ZHISHI_API_BASE_URL` | 后端 API 基础地址 | `https://zhishi-backend.ximocy.com` |
| `VITE_SKIP_AUTH` | 开发模式鉴权旁路，只在 `MODE=development` 生效 | `true` |

注意：

- `VITE_*` 变量会进入前端 bundle，不要放密钥、Token、Dify Key、OCR Secret。
- `.env.local`、`.env.development.local`、`.env.production.local` 属于本地配置，不应提交。
- 使用 `VITE_SKIP_AUTH=true` 后需要重启 dev server。

## 文档入口

| 想了解 | 文件 |
| --- | --- |
| 文档体系和维护规则 | `docs/0.文档体系说明.md` |
| 产品需求、商业模式、用户场景 | `docs/1.产品需求文档.md` |
| 技术栈、模块边界、依赖方向 | `docs/2.技术架构文档.md` |
| API、DTO、错误码、状态对象 | `docs/4.API接口文档.md` |
| 文件树、目录职责、文件数量 | `docs/6.文件树与目录结构.md` |
| AI / Agent 工作规则 | `AGENTS.md` |

## 代码入口

| 想了解 | 文件 |
| --- | --- |
| React 挂载 | `src/main.tsx` |
| Provider 和 Router 装配 | `src/App.tsx` |
| 路由表 | `src/routes/index.tsx` |
| 鉴权状态 | `src/lib/auth/AuthContext.tsx` |
| API 客户端 | `src/lib/api/client.ts` |
| API DTO 和端点 | `src/lib/api/types.ts`、`src/lib/api/*.ts` |
| 全局布局状态 | `src/context/UIContext.tsx` |
| 页面模块 | `src/features/*` |
| 样例数据 | `src/data/*.ts` |

## 架构注意事项

- 页面不要直接写裸 `fetch`，普通请求走 `apiRequest`，流式请求走 `apiStream` 或领域封装。
- 新增页面要同步 `src/routes/index.tsx`、`src/data/nav.ts` 和 `src/components/layout/Topbar.tsx`。
- `UIContext` 只放布局 UI 状态，鉴权状态归 `src/lib/auth`。
- 静态样例数据不等于真实业务数据源。
- 生产构建不要依赖开发模式鉴权旁路。
