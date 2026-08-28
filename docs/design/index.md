# 这一期文档从哪看

先认领，再看口径，最后点设计稿。后端从 **`origin/develop`** 拉分支，PR 打回 `develop`。不要从 `feature/wangchuri-RAG-keyword-search` 拉。

## 你是王晨

你是**派活的人**，不在下面这张认领表里。

- 拍产品口径（[闭环与更新方案.md](./闭环与更新方案.md)、[TCN集成.md](./TCN集成.md)）
- 验收三条：页码不许猜、用户不能勾选、不向量化。TCN：题 tag 必须来自图谱词表，交卷才 `predict`
- 不领 Issue、不写实现、不整理 [功能更新.md](./功能更新.md)（那份给前端同学彭飞翔整理）

## 执行的人

| 你 | 先打开 | 做什么 |
| --- | --- | --- |
| 罗洁 | [罗洁.md](./罗洁.md) | 目标记住、引导写入、删号。[#15](https://github.com/pfx43/zhixu-backend/issues/15) 已合。TCN：[#53](https://github.com/pfx43/zhixu-backend/issues/53) |
| 张子麟 | [张子麟.md](./张子麟.md) | 段上页码、章→页目录。[#16](https://github.com/pfx43/zhixu-backend/issues/16) 已合。TCN：[#51](https://github.com/pfx43/zhixu-backend/issues/51) |
| 陈勇搏 | [陈勇搏.md](./陈勇搏.md) | 出题页后端 → 任务检查器 → Tina 派任务。[#17](https://github.com/pfx43/zhixu-backend/issues/17) [#19](https://github.com/pfx43/zhixu-backend/issues/19) [#20](https://github.com/pfx43/zhixu-backend/issues/20) 已合。TCN：[#52](https://github.com/pfx43/zhixu-backend/issues/52) |
| 彭飞翔 | [彭飞翔.md](./彭飞翔.md) | 改前端；整理 [功能更新.md](./功能更新.md)（含 TCN 第五节） |

合同和验收勾选以 GitHub Issue 为准，人文档是认领摘要。

## 产品口径（大家看）

| 文件 | 干什么 |
| --- | --- |
| [闭环与更新方案.md](./闭环与更新方案.md) | 产品方向，拍板用 |
| [功能更新.md](./功能更新.md) | 为什么做、做成什么样（彭飞翔整理） |
| [next.md](./next.md) | 后端怎么拆 A–E、积木、别做、依赖顺序 |
| [TCN集成.md](./TCN集成.md) | TCN 词表、书学科、交卷 predict、跟对面要的 Key/建档、认领 |

三句话：目标决定 Tina 能派什么；书和答题记录决定派哪一件；用户去做上传 / 出题 / 刷题，程序看见结果就宣布完成。用户不能勾选。弹窗固定：「该任务已经完成！」

## 设计稿

可点的 HTML 在 [html/](./html/)。常用：

- [html/index.html](./html/index.html) 首页
- [html/tina.html](./html/tina.html) 对话
- [html/generate.html](./html/generate.html) 出题页
- [html/onboarding.html](./html/onboarding.html) 引导
- [html/notes.html](./html/notes.html) 笔记 / tip
- [html/practice.html](./html/practice.html) 刷题

雾面底、鼠尾草绿。不要扫成另一套产品。

## 后端 Issue

| 编号 | 标题 |
| --- | --- |
| [#15](https://github.com/pfx43/zhixu-backend/issues/15) | Goal |
| [#16](https://github.com/pfx43/zhixu-backend/issues/16) | KB 页码 + 目录 |
| [#17](https://github.com/pfx43/zhixu-backend/issues/17) | 出题页 / 邻页 |
| [#18](https://github.com/pfx43/zhixu-backend/issues/18) | tip 笔记接口 |
| [#19](https://github.com/pfx43/zhixu-backend/issues/19) | 今日任务 + 检查器（等 #15–#17） |
| [#20](https://github.com/pfx43/zhixu-backend/issues/20) | Tina 派任务（等 #15–#17、#19） |
| [#51](https://github.com/pfx43/zhixu-backend/issues/51) | TCN：目录提取写 `tcn_domain`（张子麟） |
| [#52](https://github.com/pfx43/zhixu-backend/issues/52) | TCN：出题锁词表 + 交卷 predict（陈勇搏，等 #51） |
| [#53](https://github.com/pfx43/zhixu-backend/issues/53) | TCN：服务 Key + 注册建档（罗洁） |

#15–#20 已 CLOSED completed，对应 PR 已合进 `develop`。生产剩余见 #44–#47 与 PR #43。TCN 是第二队列，先收口生产剩余再拉 #51–#53。

## 分支

```bash
git fetch origin
git checkout develop
git pull origin develop
git checkout -b feature/<缩写>-<短名>
```

RJ 罗洁 / ZL 张子麟 / CYB 陈勇搏。新表用 Alembic。查询带当前用户。不向量化、不勾选完成、页码不许猜。

接口总览在仓库文档 [docs/README.md](../README.md)（`api/`、`development/` 等），和这一期认领分开看。
