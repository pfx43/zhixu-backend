# Git 协作规范

## 核心原则

1. **每个人都有自己的分支**，所有开发工作在自己的分支上进行
2. **永远不要直接在 main 分支上修改代码**
3. 代码写好、自测没问题后，通过 **Pull Request（PR）** 请求合并到 main
4. **每天至少提交并推送一次**到自己的远程分支（哪怕是半成品，也要推上去备份）
5. main 有更新时，**及时拉取并合并到自己的分支**，避免最后冲突堆积

---

## 分支命名规则

格式：`<类型>/<姓名缩写>-<简短描述>`

| 类型 | 用途 | 示例 |
|------|------|------|
| `feature/` | 新功能开发 | `feature/cyb-learning-path` |
| `fix/` | 修复 bug | `fix/zl-chat-crash` |
| `refactor/` | 重构（不改功能） | `refactor/rj-service-layer` |
| `docs/` | 文档相关 | `docs/cyb-api-readme` |

**姓名缩写对照**（按团队成员补充）：
- CYB = 陈勇搏
- ZL = 张子麟
- RJ = 罗洁

**注意**：
- 描述部分用英文小写 + 短横线连接，不要用中文（避免终端编码问题）
- 一个分支只做一件事，功能做完合并后就不再使用

---

## 提交信息（Commit Message）规范

格式：

```
<类型>: <简短描述>

<可选的详细说明>
```

### 类型前缀

| 前缀 | 含义 | 示例 |
|------|------|------|
| `feat:` | 新增功能 | `feat: 添加学习路径页面` |
| `fix:` | 修复 bug | `fix: 修复聊天页面滚动崩溃` |
| `style:` | 样式/UI 调整（不影响逻辑） | `style: 调整首页卡片间距` |
| `refactor:` | 重构代码（不改功能） | `refactor: 抽取公共图表配置` |
| `docs:` | 文档变动 | `docs: 更新 README 接口说明` |
| `chore:` | 杂项（依赖更新、配置等） | `chore: 升级 fl_chart 到 0.68` |

### 写好提交信息的要点

- 第一行不超过 50 个字（中文算 2 个字符宽度，但不用严格数）
- 说清楚"做了什么"，而不是"改了哪个文件"
- 正文可以用中文，但前缀必须是英文

**好的例子**：
```
feat: 实现知识图谱可视化组件
fix: 修复 KT 后端离线时页面白屏
style: 统一学习仪表盘配色方案
```

**坏的例子**：
```
更新代码          ← 没有前缀，描述太模糊
fix: 改了bug     ← 没说改了什么 bug
feat: 修改了 home_page.dart 和 learning_path_page.dart ← 说的是文件不是功能
```

---

## 日常工作流程（完整步骤）

### 第一次参与项目

```bash
# 1. 克隆仓库
git clone <仓库地址>
cd patchouli-knowledge-kt

# 2. 创建自己的开发分支（从 main 拉出）
git checkout main
git pull origin main
git checkout -b feature/你的缩写-你要做的事
# 例如：git checkout -b feature/cyb-learning-path

# 3. 推送分支到远程（建立追踪关系）
git push -u origin feature/cyb-learning-path
```

### 每天的开发流程

```bash
# ===== 开始工作前 =====

# 1. 先拉取 main 的最新代码
git checkout main
git pull origin main

# 2. 切回自己的分支
git checkout feature/cyb-learning-path

# 3. 把 main 的更新合并到自己的分支
git merge main
# 如果有冲突，解决冲突后 git add . && git commit

# ===== 开发中 =====
# git merge feature/rj-P0 --no-edit
# 4. 正常写代码...

# ===== 一天结束 / 阶段性完成 =====

# 5. 查看改了什么
git status

# 6. 添加要提交的文件（建议逐个添加，不要无脑 git add .）
git add lib/pages/learning_path_page.dart
git add lib/widgets/learning_path_card.dart

# 7. 提交
git commit -m "feat: 完成学习路径卡片组件"

# 8. 推送到远程（每天至少一次！）
git push
```
# 1. 切主分支
git checkout main
# 2. 更新远端最新main
git pull origin main
# 3. 合并功能分支到main
git merge feature/rj-fic-chat --no-edit
# 4. 推送到远程main
git push origin main
### 功能完成后提交 PR

1. 确保自己分支已经合并了最新的 main（重复上面第 1-3 步）
2. 推送所有提交到远程
3. 在 GitHub/Gitee 网页上点击 **"New Pull Request"**
4. 选择：`base: main` ← `compare: feature/你的分支`
5. 填写 PR 标题和描述（说清楚做了什么、怎么测的）
6. 指派主负责人 Review
7. 等待审核通过后由负责人合并

---

## 同步 main 更新（重要！）

当你收到通知"main 有新的合并"时，立即执行：
git fetch origin
```bash
git checkout main
git pull origin main
git checkout feature/你的分支
git merge main
```

**为什么要及时同步？**
- 拖得越久，冲突越多越难解决
- 你基于过期的代码开发，最后合并时很可能出问题
- 养成习惯：每天开始工作前先同步一次

---

## 冲突解决（别慌）

当 `git merge main` 出现冲突时：

1. Git 会告诉你哪些文件冲突了
2. 打开冲突文件，找到类似这样的标记：
```
<<<<<<< HEAD
你的代码
=======
main 上别人的代码
>>>>>>> main
```
3. 手动决定保留哪部分（或者两边都保留），然后删掉 `<<<`、`===`、`>>>` 这些标记
4. 解决完所有冲突后：
```bash
git add .
git commit -m "chore: 合并 main 并解决冲突"
git push
```

**拿不准怎么解决？** 找负责人一起看，不要乱删别人的代码。

---

## 禁止事项

| 操作 | 为什么不行 |
|------|------------|
| 直接在 main 上 commit | main 只接受 PR 合并，保证代码质量 |
| `git push --force` | 会覆盖别人的提交，可能丢代码 |
| 长期不推送 | 电脑坏了代码就没了，也不利于协作 |
| 一次巨大的提交 | 很难 review，出问题也难定位 |
| 提交 `.env`、密钥、大型二进制文件 | 安全风险 + 仓库膨胀 |

---

## 常见问题

### Q: 我改到一半，需要临时切到别的分支怎么办？

```bash
# 暂存当前修改
git stash

# 切到其他分支做事...
git checkout other-branch

# 回来后恢复
git checkout feature/你的分支
git stash pop
```

### Q: 我不小心提交到了 main 怎么办？

```bash
# 如果还没 push，撤回最近一次提交（代码保留在工作区）
git reset HEAD~1

# 然后切到自己的分支重新提交
git checkout feature/你的分支
git add .
git commit -m "feat: 你的提交信息"
```

如果已经 push 了，立即联系负责人处理。

### Q: 我的分支名起错了怎么办？

```bash
# 重命名当前分支
git branch -m 新的分支名

# 删除远程旧分支，推送新分支
git push origin --delete 旧的分支名
git push -u origin 新的分支名
```

### Q: 怎么看当前在哪个分支？

```bash
git branch        # 带 * 号的就是当前分支
git status        # 第一行会显示 "On branch xxx"
```

---

## 一图流总结

```
main (受保护，只接受 PR)
 │
 ├── feature/cyb-learning-path    ← 陈勇搏的功能分支
 │       │
 │       ├── commit: feat: 完成路径卡片
 │       ├── commit: fix: 修复卡片溢出
 │       └── → PR → 合并到 main ✓
 │
 ├── feature/zl-chat-enhance      ← 张子麟的功能分支
 │       │
 │       └── 开发中...每天推送
 │
 └── fix/rj-pdf-viewer            ← 罗洁的修复分支
         │
         └── 开发中...每天推送
```

---

## 速查表

| 想做什么 | 命令 |
|----------|------|
| 查看当前状态 | `git status` |
| 查看所有分支 | `git branch -a` |
| 创建并切换分支 | `git checkout -b 分支名` |
| 切换到已有分支 | `git checkout 分支名` |
| 拉取远程更新 | `git pull` |
| 添加文件到暂存区 | `git add 文件名` |
| 提交 | `git commit -m "类型: 描述"` |
| 推送 | `git push` |
| 合并 main 到当前分支 | `git merge main` |
| 暂存修改 | `git stash` |
| 恢复暂存 | `git stash pop` |
| 查看提交历史 | `git log --oneline` |
