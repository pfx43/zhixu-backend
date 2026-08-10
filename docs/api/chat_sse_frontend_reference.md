# 知序 Chat 流式接口（SSE）前端接入参考

## 协议

```
POST /api/v1/chat
Content-Type: application/json
Authorization: Bearer <登录token>

{
  "content": "你好",
  "stream": true,
  "mode": "qa"            // qa | learning | classroom_note | verify
}
```

响应为 `text/event-stream`，每条事件：

```
event: message
data: <JSON>

```

流结束信号：`data: [DONE]`（其后连接关闭）。

**协议说明**
- 每个 `data:` 是独立 JSON，前端按行解析（以 `data: ` 开头）
- **`type` 字段**是稳定的判别语义：`reasoning` / `tool_call` / `answer` / `metadata`
- 普通回复的 `content` 是**逐词分片**的，前端拼接 `type=answer` 的事件即完整回复
- 工具结果（`role=tool`）已由后端过滤，**不会**出现在 SSE 中
- 旧字段（role/content/reasoning_content/tool_name）继续保留，旧客户端可忽略 `type` 直接兼容

## 事件类型

### 1. `reasoning` — 思考内容（思考模型才有，逐词分片）

```json
{"session_id":"abc123","type":"reasoning","role":"assistant","content":"","reasoning_content":"The"}
{"session_id":"abc123","type":"reasoning","role":"assistant","content":"","reasoning_content":" user asks."}
```

> 前端可显示"正在思考…"，或拼接后折叠展示；`content` 恒为空。

### 2. `tool_call` — 工具调用（同一次调用只发一条）

```json
{"session_id":"abc123","type":"tool_call","role":"assistant","content":"","tool_name":"kb_search"}
```

> `tool_name` 是**后端原样透传的 Tina 内部函数名**（如 `kb_search`）。前端维护展示映射：

| 内部 tool_name | 前端展示 | 功能 |
|---|---|---|
| `kb_search` | "知识检索" | 在用户自己的知识库中检索相关资料片段 |
| 未登记的其他值 | 不展示该工具事件（忽略） | — |

> 不展示工具参数、工具返回内容、调用耗时或工具级状态。

### 3. `answer` — 正式回答正文（逐词分片）

```json
{"session_id":"abc123","type":"answer","role":"assistant","content":"根据"}
{"session_id":"abc123","type":"answer","role":"assistant","content":"你的知识库..."}
```

> 拼接所有 `type=answer` 的 `content` 即完整回答。**回答正文只由 answer 事件组成**（后端已过滤工具结果，不会混入）。

### 4. `metadata` — 结构化元数据

```json
{"session_id":"abc123","type":"metadata","role":"assistant","content":"","citations":[
  {"doc_id":"doc_1","segment_id":"seg_1","title":"第一章","char_start":0,"char_end":100,"snippet":"原文片段..."}
]}
```

或 TCN 知识状态：

```json
{"session_id":"abc123","type":"metadata","role":"system","content":"","lvr":0.65,"diagnosis":"..."}
```

> `citations` 结构：`doc_id` / `segment_id` / `title` / `char_start` / `char_end` / `snippet`。

### 5. 错误 / 降级（去敏，无技术细节）

```json
{"session_id":"abc123","type":"answer","role":"assistant","content":"抱歉，AI 服务暂时不可用，请稍后重试。"}
```

## 用户打断（break）

流式进行中，前端可请求打断当前输出：

```
POST /api/v1/chat/break
Authorization: Bearer <登录token>

{"session_id": "abc123"}
```

返回：

```json
{"message": "已请求打断", "session_id": "abc123"}
```

行为：
- 正在进行的流停止产出，随后正常发送 `data: [DONE]` 结束
- **已产出的部分正文会保存**到历史消息，并在消息末尾自动追加打断提示：
  `\n\n> ⏹️ 对话已被用户打断`
- 若打断时正文尚未产出（思考阶段），历史中仍会保存一条仅含打断提示的助手消息
- 已聚合的思考内容与工具名（`reasoning_content` / `tool_names`）同样会保存
- 前端主动断开 SSE 连接（abort）同样触发保存已产出内容 + 打断提示（后端兜底）

前端建议：点击"停止生成"时先调用 `/api/v1/chat/break`，再中止 SSE 连接；收到 `[DONE]` 后刷新历史即可看到带打断提示的完整消息。

## 历史接口（GET /api/v1/chat/history）

助手消息新增两个**可选**字段（旧历史数据缺失时为空，不影响解析）：

```json
{
  "role": "assistant",
  "content": "最终回答",
  "reasoning_content": "完整思考内容",
  "tool_names": ["kb_search"],
  "created_at": "2026-08-10T20:00:00+08:00"
}
```

规则：
- `reasoning_content`：完整思考内容（流式分片已在后端聚合）
- `tool_names`：按**首次调用顺序去重**的列表；同一工具重复调用只保留一次
- 不包含工具参数、工具原始结果或内部异常
- 前端展示工具名时同样走上述映射表

## 前端处理建议（伪代码）

```js
let fullContent = "";
const toolSet = new Set();

sse.on("data:", (d) => {
  if (d === "[DONE]") { finish(); return; }
  const p = JSON.parse(d);
  switch (p.type) {
    case "reasoning":
      showThinking(p.reasoning_content); break;          // 折叠区"正在思考"
    case "tool_call":
      if (TOOL_DISPLAY[p.tool_name]) {                   // 前端映射表
        showTool(TOOL_DISPLAY[p.tool_name]);             // 图标 + 名称
      }
      break;
    case "answer":
      fullContent += p.content; renderContent(fullContent); break;
    case "metadata":
      if (p.citations) renderCitations(p.citations);
      if (p.lvr !== undefined) renderLvr(p);
      break;
  }
});
```

## 字段说明汇总

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | 会话 ID |
| `type` | string | `reasoning` / `tool_call` / `answer` / `metadata` |
| `role` | string | `assistant` / `system`（不再出现 `tool`） |
| `content` | string | 正文分片 / 去敏错误信息 |
| `reasoning_content` | string | 思考分片（type=reasoning） |
| `tool_name` | string | 内部工具名，前端映射展示（type=tool_call） |
| `citations` | array | 引用（type=metadata） |
| `lvr` / `diagnosis` | number / string | TCN 知识状态（type=metadata） |
