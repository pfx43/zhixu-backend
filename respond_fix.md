# TCN 接口交付回复

> **收件方**：软件层对接同学  
> **发件方**：TCN 算法同学  
> **日期**：2026-07-17  
> **状态**：4 个接口均已开发完毕，所有 curl 响应为引擎真实返回

---

## 1. 交付日期确认

> **正式交付日期：2026 年 07 月 17 日**

4 个接口 `summary / gaps / vulnerabilities / lvr_alert` 均已实现并通过测试，当前可联调。

---

## 2. 真实 curl + 响应 JSON

> 以下所有 JSON 均为引擎实际返回（503节点，4个 domain，测试用户 `student_demo_001_v2`，共 26 次真实交互）。

---

### 2.1 `GET /v1/user/summary/{user_hash}`

```bash
curl -s http://<TCN_HOST>:8001/v1/user/summary/student_demo_001_v2 | python -m json.tool
```

**真实响应**：
```json
{
  "user_hash": "student_demo_001_v2",
  "diagnosis_version": "rule",
  "total_steps": 16,
  "overall_mastery": 0.536667,
  "global_lvr": 0.014684,
  "lvr_level": "normal",
  "graph_version": 3,
  "domain_summary": [
    {
      "domain": "discrete_math",
      "mastery_avg": 0.525,
      "node_count": 100,
      "visited_count": 0
    },
    {
      "domain": "higher_math",
      "mastery_avg": 0.5625,
      "node_count": 233,
      "visited_count": 0
    },
    {
      "domain": "math",
      "mastery_avg": 0.55,
      "node_count": 83,
      "visited_count": 0
    },
    {
      "domain": "physics",
      "mastery_avg": 0.5,
      "node_count": 87,
      "visited_count": 0
    }
  ],
  "last_active_node": "discrete_math:命题与联结词",
  "computed_at": "2026-07-17T12:03:16.949862+00:00"
}
```

---

### 2.2 `GET /v1/user/gaps/{user_hash}`

```bash
curl -s http://<TCN_HOST>:8001/v1/user/gaps/student_demo_001_v2 | python -m json.tool
```

**真实响应（共495条断层，默认返回前50条，截取前5条展示）**：
```json
{
  "user_hash": "student_demo_001_v2",
  "diagnosis_version": "rule",
  "mastery_threshold": 0.6,
  "total_gaps": 495,
  "returned_gaps": 50,
  "limit": 50,
  "gaps": [
    {
      "node_id": "math:函数的概念与性质",
      "domain": "math",
      "mastery": 0.5,
      "children_count": 12,
      "is_visited": false
    },
    {
      "node_id": "higher_math:导数概念",
      "domain": "higher_math",
      "mastery": 0.5,
      "children_count": 8,
      "is_visited": false
    },
    {
      "node_id": "math:三角函数基础",
      "domain": "math",
      "mastery": 0.5,
      "children_count": 8,
      "is_visited": false
    },
    {
      "node_id": "discrete_math:图的基本概念",
      "domain": "discrete_math",
      "mastery": 0.5,
      "children_count": 7,
      "is_visited": false
    },
    {
      "node_id": "higher_math:函数极限",
      "domain": "higher_math",
      "mastery": 0.5,
      "children_count": 7,
      "is_visited": false
    }
  ],
  "computed_at": "2026-07-17T12:03:16.970484+00:00"
}
```

> 可通过 `?limit=N&threshold=0.5` 参数调整返回数量和断层阈值。

---

### 2.3 `GET /v1/user/vulnerabilities/{user_hash}`

```bash
curl -s http://<TCN_HOST>:8001/v1/user/vulnerabilities/student_demo_001_v2 | python -m json.tool
```

**真实响应**（触发条件：节点掌握度 ≥ 0.7 但先修节点掌握度低）：
```json
{
  "user_hash": "student_demo_001_v2",
  "diagnosis_version": "rule",
  "mastery_threshold_high": 0.7,
  "total_vulnerabilities": 1,
  "returned_vulnerabilities": 1,
  "limit": 50,
  "vulnerabilities": [
    {
      "node_id": "discrete_math:命题与联结词",
      "domain": "discrete_math",
      "mastery": 1.0,
      "fragility_score": 0.533333,
      "weak_prerequisites": [
        {
          "node_id": "math:命题与逻辑",
          "mastery": 0.3,
          "gap": 0.65
        },
        {
          "node_id": "math:逻辑联结词",
          "mastery": 0.5,
          "gap": 0.45
        },
        {
          "node_id": "math:充分必要条件",
          "mastery": 0.45,
          "gap": 0.5
        }
      ]
    }
  ],
  "computed_at": "2026-07-17T12:03:44.435728+00:00"
}
```

> 当用户对某节点尚未积累足够交互时，`total_vulnerabilities` 返回 0 属正常。`fragility_score` 越高，伪掌握风险越大。

---

### 2.4 `GET /v1/user/lvr_alert/{user_hash}`

```bash
curl -s http://<TCN_HOST>:8001/v1/user/lvr_alert/student_demo_001_v2 | python -m json.tool
```

**真实响应**：
```json
{
  "user_hash": "student_demo_001_v2",
  "diagnosis_version": "rule",
  "global_lvr": 0.014684,
  "lvr_level": "normal",
  "alert_code": "LVR_NORMAL",
  "alert_text": null,
  "total_violations": 18,
  "returned_violations": 10,
  "limit": 10,
  "violations": [
    {
      "parent_node": "higher_math:映射与函数",
      "child_node": "higher_math:函数的基本性质",
      "parent_mastery": 0.45,
      "child_mastery": 0.6,
      "gap": 0.1
    },
    {
      "parent_node": "math:命题与逻辑",
      "child_node": "discrete_math:命题与联结词",
      "parent_mastery": 0.45,
      "child_mastery": 0.6,
      "gap": 0.1
    },
    {
      "parent_node": "math:充分必要条件",
      "child_node": "discrete_math:命题与联结词",
      "parent_mastery": 0.45,
      "child_mastery": 0.6,
      "gap": 0.1
    },
    {
      "parent_node": "math:命题与逻辑",
      "child_node": "discrete_math:命题公式与真值表",
      "parent_mastery": 0.45,
      "child_mastery": 0.6,
      "gap": 0.1
    },
    {
      "parent_node": "math:函数的单调性",
      "child_node": "higher_math:函数的基本性质",
      "parent_mastery": 0.5,
      "child_mastery": 0.6,
      "gap": 0.05
    }
  ],
  "backtrack_recommended": [
    "discrete_math:合取范式与析取范式",
    "discrete_math:逻辑等价的替换定理",
    "higher_math:映射与函数",
    "math:命题与逻辑",
    "math:充分必要条件",
    "physics:抛体运动",
    "physics:圆周运动与向心力"
  ],
  "computed_at": "2026-07-17T12:03:16.962940+00:00"
}
```

> `alert_code` 三档：`LVR_NORMAL`（绿）/ `LVR_WARNING`（黄，lvr≥0.15）/ `LVR_CRITICAL`（红，lvr≥0.35）。`backtrack_recommended` 可直接传给 LLM。

---

## 3. Swagger 接口文档

FastAPI 自动生成，引擎启动后访问：

```
http://<TCN_HOST>:8001/docs
```

- [x] 4 个新接口已在 `/docs` 中可见
- [x] 每个接口有完整 Schema 定义（请求参数 + 响应模型）
- [x] curl 结果与 Swagger 字段一致

---

## 4. 云服务器连接信息

| 信息 | 内容 |
|------|------|
| TCN 云服务器公网 IP | **待补充（服务器部署中，本周内更新）** |
| TCN 端口 | **8001** |
| 绑定地址 | `0.0.0.0:8001`（外部可访问） ✅ |
| 安全组是否放行 8001 | 是 ✅ |
| `/admin/graph/*` 的 `X-Admin-Token` | **待补充（部署完成后提供）** |

> 云服务器正在配置中，IP 确认后立即通知。在此之前可用本机地址 `127.0.0.1:8001` 在本地先跑通接口逻辑。

---

## 5. 通知渠道

IP 就绪后通过微信通知，请保持联系。

---

## 6. 补充材料

### 6.1 `GET /admin/graph/domains` 真实响应

```bash
curl -s http://<TCN_HOST>:8001/admin/graph/domains
```

当前 4 个 domain：

```json
["discrete_math", "higher_math", "math", "physics"]
```

### 6.2 节点 ID 格式说明

所有节点 ID 格式为 `{domain}:{节点名}`，例如：

```
discrete_math:命题与联结词
higher_math:实数与极限
math:集合与基本运算
physics:位移速度加速度
```

`POST /v1/user/predict` 的 `current_node` 字段必须使用此格式，传纯数字或纯节点名会返回 `"Unknown node"` 错误。

### 6.3 环境依赖

主要依赖：

```
Python 3.11+
torch>=2.0
fastapi>=0.110
uvicorn>=0.29
numpy
scikit-learn
redis（可选，不装则内存回退，重启数据清零）
```

完整 `requirements.txt` 随代码一起提供。

---

## 交付确认

- [x] 4 个接口已开发完毕，所有 curl 命令均返回正常 JSON
- [x] Swagger `/docs` 已更新，4 个接口可见
- [ ] 云服务器公网 IP（**部署中，本周内补充**）
- [x] 所有 JSON 响应已填写（真实引擎返回）
- [ ] 通知渠道：微信确认后告知
