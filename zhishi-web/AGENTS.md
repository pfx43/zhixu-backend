# AGENTS.md

> 本文件是 `D:\桌面\zhishi-web` 唯一 AI / Agent 执行入口。所有自然语言说明使用中文；代码标识、命令、路径、接口名保持原文。

## 1. 先读顺序

进入仓库后先读：

1. `AGENTS.md`
2. `docs/0.文档体系说明.md`
3. `docs/1.产品需求文档.md`
4. `docs/2.技术架构文档.md`
5. `docs/4.API接口文档.md`
6. `docs/6.文件树与目录结构.md`
7. `package.json`
8. 与任务直接相关的源码文件

本仓库不使用 `CLAUDE.md`。不要创建、恢复或要求维护 `CLAUDE.md`。

## 2. 仓库定位

这是知序 Web 前端仓库，当前是 Vite + React + TypeScript 单页应用。当前 Web 前端主要承载个人工作台体验，完整产品需求见 `docs/1.产品需求文档.md`。

当前代码事实：

- 全局布局由 `AppShell`、`Sidebar`、`Topbar`、`RightPanel` 组成。
- 路由在 `src/routes/index.tsx`，业务页面使用 `ProtectedRoute`。
- 鉴权状态由 `src/lib/auth/AuthContext.tsx` 管理。
- API 请求统一收敛到 `src/lib/api`。
- `src/data` 仍保留 mock/demo/默认展示数据，不等于真实业务数据源。
- `src/hooks/useNotifications.ts` 当前仍使用本地通知样例，虽然 `src/lib/api/notifications.ts` 已有封装。

## 3. 常用命令

```powershell
npm run dev
npm run build
npm run lint
npm run test
npm run preview
```

命令含义：

- `npm run dev`：启动 Vite 开发服务器。
- `npm run build`：执行 `tsc -b && vite build`。
- `npm run lint`：执行 ESLint。
- `npm run test`：执行 Vitest。
- `npm run preview`：预览构建产物。

## 4. 文档真相源

| 修改内容 | 先读 | 必要时回写 |
| --- | --- | --- |
| 文档体系、AI 入口 | `docs/0.文档体系说明.md` | `docs/0.文档体系说明.md`、`AGENTS.md` |
| 产品需求、业务边界 | `docs/1.产品需求文档.md` | `docs/1.产品需求文档.md` |
| 架构边界、状态归属 | `docs/2.技术架构文档.md` | `docs/2.技术架构文档.md` |
| API、DTO、错误码 | `docs/4.API接口文档.md` | `docs/4.API接口文档.md` |
| 创建、修改、删除、移动、重命名任何文件 | `docs/6.文件树与目录结构.md` | `docs/6.文件树与目录结构.md` |
| 启动、测试、构建命令 | `README.md`、`package.json` | `README.md`、`AGENTS.md` |

## 5. 架构底线

- 页面不要直接写裸 `fetch`；普通请求走 `apiRequest`，流式请求走 `apiStream` 或领域封装。
- 鉴权状态归 `src/lib/auth`，不要放入 `UIContext`。
- `UIContext` 只处理布局 UI 状态。
- 新 API 先更新 `docs/4.API接口文档.md`，再更新 `src/lib/api`。
- 新页面同步 `src/routes/index.tsx`、`src/data/nav.ts`、`src/components/layout/Topbar.tsx`。
- 文件归属以 `docs/6.文件树与目录结构.md` 为准。
- 创建、修改、删除、移动、重命名任何文件后，都必须核对并更新 `docs/6.文件树与目录结构.md` 的完整目录结构和文件数量；如果只改文件内容、路径和数量不变，也必须在收尾说明中说明已核对无需调整目录树。
- 不把机构端、公益版、学校端等完整产品需求误写成当前 Web 前端已实现能力。

## 6. 样式与 TypeScript

- 优先使用 `bg-bg`、`bg-surface`、`text-ink-primary`、`border-line-soft`、`text-primary` 等已有 token。
- 图标优先使用 `lucide-react`。
- 图标按钮需要 `aria-label` 或 `title`。
- 保持工作台风格，避免营销页式 Hero。
- 类型导入使用 `import type`。
- 路径别名使用 `@/*`。
- 未使用变量和参数会导致检查失败。

## 7. Git 与用户改动

开始任何改动前运行：

```powershell
git status --short
```

规则：

- 不回滚、覆盖或格式化与当前任务无关的用户改动。
- 不使用 `git add .` 或 `git add -A`，除非用户明确要求且工作区已确认干净。
- 暂存使用白名单路径：`git add -- <path>`。
- 不运行 `git reset --hard`、`git checkout -- <path>`、`git clean -fd` 等破坏性命令，除非用户明确要求并确认影响范围。
- 提交信息使用 Conventional Commits，中文说明业务意图，例如 `docs: 重建项目文档体系`。

## 8. 验证要求

按改动范围选择验证：

- 只改文档：至少运行 `git diff --check` 并检查文档路径。
- 改 UI 组件或页面：运行 `npm run lint`，必要时运行 `npm run build`。
- 改 API 客户端：运行 `npm run test`，必要时运行 `npm run build`。
- 改路由或构建配置：运行 `npm run build`。

如果验证失败：

- 报告真实错误。
- 判断是本次改动、既有未提交改动还是测试纳入策略导致。
- 不删除测试、绕过鉴权或隐藏错误来制造通过。

## 9. 收尾说明

最终回复至少说明：

- 改了哪些文件。
- 为什么这样改。
- 执行了哪些验证。
- 是否还有未验证项。
- 当前剩余未提交改动，尤其是非本次任务文件。
