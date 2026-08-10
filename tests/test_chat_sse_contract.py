"""
Chat SSE 公开合同测试 — 覆盖：
- ChatChunkNormalizer 归一化（reasoning/tool_call/answer 白名单、工具结果过滤、去重）
- chat SSE 输出（type 字段、[DONE]、无工具结果泄漏）
- 历史持久化（reasoning_content / tool_names 按序去重）
- 错误去敏、旧历史兼容、非流式响应新字段
"""
import json
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import chat as chat_api
from app.schemas.common import ChatHistoryItem
from app.services.chat.chat_contract import ChatChunkNormalizer


class FakeAgent:
    """模拟 ZhishiAgent：用真实 Normalizer 处理原始 chunk，暴露聚合结果。"""

    def __init__(self, raw_chunks, *, error=None):
        self._raw = raw_chunks
        self._error = error
        self._last_reasoning = ""
        self._last_tool_names = []

    @property
    def is_ready(self) -> bool:
        return True

    def predict_stream(self, *args, **kwargs):
        if self._error:
            raise self._error
        normalizer = ChatChunkNormalizer()
        for chunk in self._raw:
            event = normalizer.normalize(chunk)
            if event:
                yield event
        self._last_reasoning = normalizer.reasoning
        self._last_tool_names = list(normalizer.tool_names)


RAW_CHUNKS = [
    {"role": "assistant", "reasoning_content": "The"},
    {"role": "assistant", "reasoning_content": " user asks."},
    {"role": "assistant", "tool_name": "kb_search"},
    {"role": "assistant", "tool_name": "kb_search", "tool_arguments": '{"query": "知识追踪"}'},
    {"role": "assistant", "tool_name": "kb_search", "tool_arguments": "}"},
    {"role": "tool", "content": '{"hits": [{"segment_id": "LEAK_MARKER"}], "count": 0}', "tool_name": "kb_search"},
    {"role": "assistant", "reasoning_content": "No hits."},
    {"role": "assistant", "content": "你好"},
    {"role": "assistant", "content": "，世界"},
]


@contextmanager
def _sse_client(fake_agent, saved_messages, *, history=None):
    """构建 chat 路由测试客户端；patch 在请求期间保持生效。"""
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/api/v1/chat")
    app.dependency_overrides[chat_api.get_current_active_user] = lambda: {
        "user_id": 1, "dataset_id": ""
    }
    app.dependency_overrides[chat_api.get_current_token] = lambda: "test-token"
    app.dependency_overrides[chat_api.get_db] = lambda: MagicMock()
    app.dependency_overrides[chat_api.check_quota] = lambda: {"user_id": 1}

    def recorder(*args, **kwargs):
        saved_messages.append((args, kwargs))

    with (
        patch.object(chat_api.agent_manager, "get_agent", return_value=fake_agent),
        patch.object(
            chat_api,
            "resolve_chat_collection",
            return_value=(SimpleNamespace(id="c1"), "ds1"),
        ),
        patch.object(chat_api, "_save_message", side_effect=recorder),
        patch.object(chat_api, "_load_history", return_value=history or []),
    ):
        yield TestClient(app)


def _parse_sse(text: str):
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(line[6:])
    return events


class ChatChunkNormalizerTests(unittest.TestCase):
    def test_reasoning_aggregated_and_typed(self):
        n = ChatChunkNormalizer()
        ev = n.normalize({"role": "assistant", "reasoning_content": "The"})
        self.assertEqual(ev, {
            "type": "reasoning", "role": "assistant", "content": "", "reasoning_content": "The",
        })
        n.normalize({"role": "assistant", "reasoning_content": " user asks."})
        self.assertEqual(n.reasoning, "The user asks.")

    def test_tool_call_emitted_once_per_tool(self):
        n = ChatChunkNormalizer()
        ev1 = n.normalize({"role": "assistant", "tool_name": "kb_search"})
        ev2 = n.normalize({"role": "assistant", "tool_name": "kb_search", "tool_arguments": "x"})
        self.assertEqual(ev1["type"], "tool_call")
        self.assertEqual(ev1["tool_name"], "kb_search")
        self.assertIsNone(ev2)  # 重复 tool_name 不再发事件
        self.assertNotIn("tool_arguments", ev1)

    def test_tool_result_dropped(self):
        n = ChatChunkNormalizer()
        ev = n.normalize({"role": "tool", "content": '{"hits": []}', "tool_name": "kb_search"})
        self.assertIsNone(ev)
        self.assertEqual(n.tool_names, [])

    def test_tool_names_ordered_dedup(self):
        n = ChatChunkNormalizer()
        for t in ("kb_search", "search", "kb_search", "search"):
            n.normalize({"role": "assistant", "tool_name": t})
        self.assertEqual(n.tool_names, ["kb_search", "search"])

    def test_answer_passthrough(self):
        n = ChatChunkNormalizer()
        ev = n.normalize({"role": "assistant", "content": "你好"})
        self.assertEqual(ev, {"type": "answer", "role": "assistant", "content": "你好"})


class InfiniteInterruptAgent(FakeAgent):
    """无限输出 + 每次迭代同步聚合结果的 Agent（模拟真实 ZhishiAgent finally 行为）。"""

    def __init__(self):
        self._last_reasoning = ""
        self._last_tool_names = []
        self._error = None
        self._raw = []

    @property
    def is_ready(self) -> bool:
        return True

    def predict_stream(self, *args, **kwargs):
        normalizer = ChatChunkNormalizer()
        n = 0
        while True:
            ev = normalizer.normalize({"role": "assistant", "content": f"片段{n}"})
            self._last_reasoning = normalizer.reasoning
            self._last_tool_names = list(normalizer.tool_names)
            if ev:
                yield ev
            n += 1


class ChatSseContractTests(unittest.TestCase):
    def test_sse_typed_events_and_no_tool_result_leak(self):
        saved = []
        fake = FakeAgent(RAW_CHUNKS)
        with _sse_client(fake, saved) as client:
            resp = client.post("/api/v1/chat", json={
                "content": "知识追踪是什么？", "stream": True, "mode": "qa",
            })
        self.assertEqual(resp.status_code, 200)
        events = _parse_sse(resp.text)

        self.assertEqual(events[-1], "[DONE]")  # 稳定结束语义
        payloads = [json.loads(e) for e in events[:-1]]

        # 每个 payload 都有 type，且无工具参数/结果泄漏
        for p in payloads:
            self.assertIn("type", p)
            self.assertNotIn("tool_arguments", p)
            self.assertNotIn("LEAK_MARKER", json.dumps(p, ensure_ascii=False))

        types = [p["type"] for p in payloads]
        self.assertIn("reasoning", types)
        self.assertIn("tool_call", types)
        self.assertIn("answer", types)
        # tool_call 只出现一次（去重）
        self.assertEqual(types.count("tool_call"), 1)
        tool_events = [p for p in payloads if p["type"] == "tool_call"]
        self.assertEqual(tool_events[0]["tool_name"], "kb_search")

        # 回答正文由 answer 事件拼接，不含工具结果
        answer_text = "".join(p["content"] for p in payloads if p["type"] == "answer")
        self.assertEqual(answer_text, "你好，世界")

        # 历史持久化：干净正文 + 完整思考 + 按序去重工具名
        save_calls = [s for s in saved if s[0][2] == "assistant"]
        self.assertTrue(save_calls)
        args, kwargs = save_calls[-1]
        self.assertEqual(args[3], "你好，世界")
        self.assertEqual(kwargs["reasoning_content"], "The user asks.No hits.")
        self.assertEqual(kwargs["tool_names"], ["kb_search"])

    def test_error_is_desensitized(self):
        saved = []
        fake = FakeAgent([], error=ValueError("secret-internal-detail: db timeout"))
        with _sse_client(fake, saved) as client:
            resp = client.post("/api/v1/chat", json={
                "content": "你好", "stream": True, "mode": "qa",
            })
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("secret-internal-detail", resp.text)
        self.assertIn("抱歉", resp.text)

    def test_non_stream_response_has_new_fields(self):
        saved = []
        fake = FakeAgent(RAW_CHUNKS)
        with _sse_client(fake, saved) as client:
            resp = client.post("/api/v1/chat", json={
                "content": "知识追踪是什么？", "stream": False, "mode": "qa",
            })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["content"], "你好，世界")  # 无工具结果
        self.assertEqual(body["reasoning_content"], "The user asks.No hits.")
        self.assertEqual(body["tool_names"], ["kb_search"])

    def test_old_history_missing_new_fields_still_ok(self):
        old = {"role": "assistant", "content": "旧消息", "created_at": "2026-08-10T10:00:00"}
        item = ChatHistoryItem.model_validate(old)
        self.assertIsNone(item.reasoning_content)
        self.assertIsNone(item.tool_names)

        saved = []
        fake = FakeAgent(RAW_CHUNKS)
        with _sse_client(
            fake, saved,
            history=[{"role": "user", "content": "hi", "created_at": "2026-08-10T10:00:00"}],
        ) as client:
            resp = client.get("/api/v1/chat/history?session_id=old-session")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_user_interrupt_saves_partial_output_with_notice(self):
        """生成器级测试：消费部分输出后标记打断，断言流提前结束且保存内容带打断提示。"""
        saved = []
        fake = InfiniteInterruptAgent()
        with (
            patch.object(chat_api.agent_manager, "get_agent", return_value=fake),
            patch.object(
                chat_api,
                "resolve_chat_collection",
                return_value=(SimpleNamespace(id="c1"), "ds1"),
            ),
            patch.object(chat_api, "_save_message", side_effect=lambda *a, **k: saved.append((a, k))),
            patch.object(chat_api, "_load_history", return_value=[]),
        ):
            gen = chat_api._stream_agent_response(
                user_id=1,
                session_id="sess-break",
                message="打断测试",
                dataset_id="ds1",
                collection_id="c1",
                mode="qa",
                token="t",
            )
            it = iter(gen)
            consumed = []
            for _ in range(30):  # 消费部分输出
                consumed.append(next(it))

            # 前端发送 break：标记该 session
            chat_api._mark_interrupt(1, "sess-break")
            remaining = list(it)  # 继续消费 → 检查到标记，流提前结束
            consumed += remaining

        # 流以 [DONE] 结束，且未产出全部内容
        self.assertEqual(consumed[-1], "data: [DONE]\n\n")
        answer_chunks = [
            l for l in consumed
            if l.startswith("data: ") and '"type": "answer"' in l
        ]
        self.assertLess(len(answer_chunks), 100)  # 无限流被打断，只产出部分

        # 已产出内容被保存，且消息末尾追加打断提示
        save_calls = [s for s in saved if s[0][2] == "assistant"]
        self.assertTrue(save_calls)
        args, kwargs = save_calls[-1]
        self.assertTrue(args[3].endswith(chat_api.INTERRUPT_NOTICE))
        self.assertIn("片段", args[3])
        # 打断标记已清理（一次性消费）
        self.assertFalse(chat_api._check_interrupt(1, "sess-break"))

    def test_stale_interrupt_does_not_break_new_stream(self):
        """残留标记（上次打断未消费）不应中断新一轮对话。"""
        chat_api._mark_interrupt(1, "sess-stale")
        saved = []
        fake = FakeAgent(RAW_CHUNKS)
        with (
            patch.object(chat_api.agent_manager, "get_agent", return_value=fake),
            patch.object(
                chat_api,
                "resolve_chat_collection",
                return_value=(SimpleNamespace(id="c1"), "ds1"),
            ),
            patch.object(chat_api, "_save_message", side_effect=lambda *a, **k: saved.append((a, k))),
            patch.object(chat_api, "_load_history", return_value=[]),
        ):
            lines = list(chat_api._stream_agent_response(
                user_id=1, session_id="sess-stale", message="新对话",
                dataset_id="ds1", collection_id="c1", mode="qa", token="t",
            ))

        # 新流完整产出（未被残留标记打断）：有 answer 事件 + [DONE] + 无打断提示
        sse_text = "\n".join(lines)
        self.assertIn('"type": "answer"', sse_text)
        self.assertIn("data: [DONE]", sse_text)
        save_calls = [s for s in saved if s[0][2] == "assistant"]
        self.assertTrue(save_calls)
        self.assertNotIn(chat_api.INTERRUPT_NOTICE, save_calls[-1][0][3])
        # 残留标记已被新流启动清理
        self.assertFalse(chat_api._check_interrupt(1, "sess-stale"))


if __name__ == "__main__":
    unittest.main()
