# TCN 接入知序（已拍口径）

知识追踪引擎在 `http://47.82.118.95:8001`。对接原文：[TCN_API_对接文档.md](../api/TCN/TCN_API_对接文档.md)。词表：[tcn-knowledge-tags.md](../api/TCN/tcn-knowledge-tags.md) / [tcn-knowledge-tags.json](../api/TCN/tcn-knowledge-tags.json)。

产品「为什么 / 做成什么样」见 [功能更新.md](./功能更新.md) 第五节。本文写规则、对接要求和认领。派活的人是王晨，不在认领表里。

闭环里学情仍是书、题、对/错/不会。TCN 只多一层：题上的知识点必须来自引擎图谱，交卷时把对/错告诉引擎。不要用 TCN 的 Learning OS（`goals` / `today` / `evidence`）冒充知序的目标和日任务。

---

## 1. 现在怎样、要改成怎样

以前出题 Agent 自己编 tag。接 TCN 之后，**知识点 tag 只来自图谱 name**（人工维护的节点，不是模型现场发明）。`name` 写在题目上；`id`（如 `higher_math:夹逼准则`）只在交卷时查表，作为 `predict` 的 `current_node`。

三套 tag 不要混：

| 种类 | 用途 | 进 TCN？ |
| --- | --- | --- |
| 题目知识点 | 图谱 `name` | 是 |
| 书的学科 `domain` | 对应引擎 `domain_id`，现在只有 `higher_math` | 用来选词表 |
| tip / 画像 | 用户自己的分类 | 否 |

学生身份是知序库里的 `users.user_hash`。引擎按这个键记掌握度。调用方不用带答题历史。`session_id` 只是日志。前端不直连 TCN，也不传 `tc_node_id`。

现有聊天结束时的 `predict`（前端带 `tc_node_id`）**不当主路径**。主路径是刷题交卷。

`predict` 只有 `correct` / `incorrect`。交卷 `correct` → `correct`，`wrong` → `incorrect`，**「不会」不传**。任务完成仍计「不会」。失败降级，交卷 HTTP 照样成功。不要因为 TCN 把整站打挂。`TCN_BASE_URL` 配错的修法仍等王晨点头，见 [next.md](./next.md) bug 列表。

联调：本机 `127.0.0.1:8001` 可能 502，文档地址 `47.82.118.95:8001` 健康检查 ready。图谱 503 节点、`graph_version` 3。用抽出的 `higher_math:夹逼准则` 打 `predict` 能 200，但 `node_mastery` 可能吐 `discrete_math:*`、没有夹逼准则——引擎 quirks，知序侧仍按词表传节点。文档写未知节点 404，线上有时是 200 + `diagnosis` 以 `Unknown node:` 开头。

---

## 2. 知序怎么接（开发顺序）

1. 词表当代码模块加载 `tcn-knowledge-tags.json`（按 `domain` → `name` → `id`）。图更新整表换一版，记下 `graph_version`。
2. **目录提取时判学科**（跟章→页同一趟，但是单独字段）。prompt 只给封闭名单（现在就 `higher_math`），输出只能是名单里的 id 或 `None`。拿不准就 `None`，不要猜，不要自造「微积分」。页码规则不变：优先书签/目录，禁止编页。学科不要和编目录揉成一段自由发挥。
3. 书上持久化 `tcn_domain`（或等价列）。人以后能改；改完只影响新出的题。旧题按当时 tag 查表，查不到就不 `predict`。
4. `domain != None`：出题 prompt 带该领域 **name 列表**。入库前程序校验，不在词表里 → 整题打回一次；再不行丢弃，非法 tag 不准入库。有 domain 时禁用 `["自动生成", …]` 那种兜底。一道题只拿词表内 tag；`predict` 用第一个合法 name 对应的 `id`。`domain is None`：出题刷题照旧，不调 TCN。
5. 交卷挂钩 `predict`。开关默认关，配置齐了再开。
6. 等对面 `register` 好了：知序注册成功后用服务 Key 建档；删号若有注销就调。在此之前不要依赖「第一次 predict 自动建档」当正式方案。

Tina 用 TCN `gaps` 派刷题放到功能 D 之后，先用知序自己的错/不会。`gaps` 是增强，不是任务完成条件。

---

## 3. 跟 TCN 要的（服务密钥 + 建档）

不是每个学生一把 Key。知序后端一把服务密钥；学生身份仍是 `user_hash`。

可直接转给对面或丢给 Agent：

`/v1/user/*` 必须在 Header 带 TCN 签发的服务 Key（建议 `X-Api-Key` 或 `Authorization: Bearer`，定死一种）。缺、错、过期 → 401，不进推理、不写状态。不要用 `predict` body 里那个空的 `api_key` 字段做鉴权。Key 由 TCN 签发、登记、吊销、轮换，不提供公网自助申请。限速按 Key 计。`GET /health` 可继续无密钥。`/admin/*` 仍走控制台登录（含 `GET /admin/auth/api-keys`，那是控制台列 Key，不是知序申请口）。

另增建档接口（如 `POST /v1/user/register`）：body 只收知序已生成的 `user_hash`，TCN 不给学生发账号、不存密码。同样必须带服务 Key。同一 hash 重复登记幂等，不重置掌握度。取消「第一次 predict 自动建档」；未登记的 hash 打 `predict` / 画像 / gaps → 404 `User not found`。无 Key 时一律 401，不要用 404 暴露「这个学生在不在」。

知序对接顺序：注册 → 本地写入 `user_hash` → 调 TCN register → 之后交卷才 predict。

---

## 4. 认领（从 `origin/develop` 拉分支）

生产 bug（#28–#40）未合入前，TCN 当第二队列，不要同一人两条线一起爆。

| 人 | 做 | 不做 |
| --- | --- | --- |
| 张子麟 | 目录提取写 `tcn_domain`（封闭名单或 `None`）；Alembic 加列；书信息可读、可改。[#51](https://github.com/pfx43/zhixu-backend/issues/51) | 不写出题 prompt、不调 `predict`、不编页码 |
| 陈勇搏 | 加载词表；有 domain 时出题锁 tag、非法打回；交卷 `predict`（「不会」不传）；失败降级。[#52](https://github.com/pfx43/zhixu-backend/issues/52) | 不接 Learning OS；不让前端传 `tc_node_id`；聊天旧挂钩不当主路径 |
| 罗洁 | 等对面 register：注册后建档、删号注销；`TCN_API_KEY`；挂了降级。[#53](https://github.com/pfx43/zhixu-backend/issues/53) | 不改出题 Agent |
| 彭飞翔 | [功能更新.md](./功能更新.md) 第五节；书上展示/改学科；刷题请求不带节点 id | 不改后端 |

合同：[#51](https://github.com/pfx43/zhixu-backend/issues/51) 书学科（张子麟）、[#52](https://github.com/pfx43/zhixu-backend/issues/52) 出题+交卷（陈勇搏，等 #51）、[#53](https://github.com/pfx43/zhixu-backend/issues/53) Key+建档（罗洁）。不要把王晨写进认领表。生产剩余 bug 先于本条。

---

## 5. 别做

- 为 TCN 另做书 ID（引擎没有书，只有图节点）
- 让模型输出 `higher_math:…` 写进题里
- 把 tip / 画像 tag 当知识点
- 用聊天参数冒充交卷
- 把「不会」当成 `incorrect`
- 领域拿不准还写成 `higher_math`（默认 `None`，宁可不追踪）
