# 这一期文档从哪看

先认领，再看口径，最后点设计稿。后端从 **`origin/develop`** 拉分支，PR 打回 `develop`。不要从 `feature/wangchuri-RAG-keyword-search` 拉。

## 我是谁

| 你 | 先打开 | 做什么 |
| --- | --- | --- |
| 罗洁 | [罗洁.md](./罗洁.md) | 目标记住、引导写入、删号。Issue [#15](https://github.com/pfx43/zhixu-backend/issues/15) |
| 张子麟 | [张子麟.md](./张子麟.md) | 段上页码、章→页目录。Issue [#16](https://github.com/pfx43/zhixu-backend/issues/16) |
| 陈勇搏 | [陈勇搏.md](./陈勇搏.md) | 出题页后端 → 任务检查器 → Tina 派任务。[#17](https://github.com/pfx43/zhixu-backend/issues/17) [#19](https://github.com/pfx43/zhixu-backend/issues/19) [#20](https://github.com/pfx43/zhixu-backend/issues/20) |
| 彭飞翔 | [彭飞翔.md](./彭飞翔.md) | 改前端；整理 [功能更新.md](./功能更新.md) |

合同和验收勾选以 GitHub Issue 为准，人文档是认领摘要。

## 产品口径（大家看）

| 文件 | 干什么 |
| --- | --- |
| [闭环与更新方案.md](./闭环与更新方案.md) | 产品方向，拍板用 |
| [功能更新.md](./功能更新.md) | 为什么做、做成什么样（彭飞翔整理） |
| [next.md](./next.md) | 后端怎么拆 A–E、积木、别做、依赖顺序 |

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

#19、#20 没到依赖不要硬接假数据当正式方案。

## 分支

```bash
git fetch origin
git checkout develop
git pull origin develop
git checkout -b feature/<缩写>-<短名>
```

RJ 罗洁 / ZL 张子麟 / CYB 陈勇搏。新表用 Alembic。查询带当前用户。不向量化、不勾选完成、页码不许猜。

接口总览在仓库文档 [docs/README.md](../README.md)（`api/`、`development/` 等），和这一期认领分开看。
