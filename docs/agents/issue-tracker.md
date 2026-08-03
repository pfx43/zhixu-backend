# 议题追踪：GitHub

本仓库的工程议题和 PRD 使用 GitHub Issues 管理。所有操作使用 `gh` CLI；在仓库内运行时由 Git 远端自动识别仓库。

## 约定

- 创建议题：`gh issue create --title "..." --body "..."`。多行正文使用 PowerShell here-string 或临时文件。
- 阅读议题：`gh issue view <number> --comments`，并同时读取 labels。
- 列出议题：`gh issue list --state open --json number,title,body,labels,comments`，按需附加 `--label` 与 `--state`。
- 评论：`gh issue comment <number> --body "..."`。
- 增删标签：`gh issue edit <number> --add-label "..."` 或 `gh issue edit <number> --remove-label "..."`。
- 关闭议题：`gh issue close <number> --comment "..."`。

## Pull requests as a triage surface

**PRs as a request surface: no.**

外部 PR 不进入 triage 队列。需要将其纳入时，把本标记改为 `yes`，并由 `triage` 技能使用对应的 `gh pr` 工作流。

## 技能操作

- 当技能要求“发布到 issue tracker”时，创建一个 GitHub Issue。
- 当技能要求“获取相关 ticket”时，运行 `gh issue view <number> --comments`。

## 跨仓试点议题

- 用户可见症状首先记录在承载该体验的仓库，并使用稳定编号 `KS-PILOT-xxxx`。
- 确认需要后端修改后，在本仓库建立同编号的实现或阻塞议题，并从两侧正文互相链接。
- 一个跨仓 Bug 只有在所有关联议题完成验证、提交和推送后才能关闭源议题。

## Wayfinding 操作

- Map：创建带 `wayfinder:map` 标签的单个 Issue，保存 Notes、Decisions-so-far 和 Fog。
- 子 ticket：优先使用 GitHub sub-issue；不可用时，在 Map 正文中维护任务列表，并在子 Issue 顶部写 `Part of #<map>`。
- 阻塞关系：优先使用 GitHub 原生 issue dependencies；不可用时，在子 Issue 顶部记录 `Blocked by: #<n>`。
- Frontier：开放、无未完成 blocker、未被认领的第一个 ticket。
- Claim：第一次写操作使用 `gh issue edit <n> --add-assignee @me`。
- Resolve：把结论、验证证据与提交 SHA 写入 Issue 后再关闭。
