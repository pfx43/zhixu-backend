"""DeepSeek 思考模式工具回合必须回传 reasoning_content。"""
from types import SimpleNamespace

from app.services.llm.reasoning_roundtrip import attach_reasoning_roundtrip


class _FakeAgent:
    def __init__(self, messages):
        self.context_manager = SimpleNamespace(get_messages=lambda: messages)
        self.stream_handlers = []
        self.before_handlers = []
        self.after_handlers = []

    def add_on_stream_chunk_handler(self, func):
        self.stream_handlers.append(func)

    def add_before_tool_calls_handler(self, func):
        self.before_handlers.append(func)

    def add_after_tool_call_handler(self, func):
        self.after_handlers.append(func)


def test_writes_reasoning_onto_split_tool_turn():
    """复现日志里的 400：content 一条 + tool_calls 一条，且没有 reasoning_content。"""
    messages = [
        {"role": "user", "content": "我确认这个目标，就是这个。"},
        {"role": "assistant", "content": "好的，目标记下了。"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_00_4juu9uDX7V8J6OHmg0Z59451",
                "function": {"name": "onboarding_confirm_learning_goal"},
            }],
        },
        {"role": "tool", "content": "已弹出确认卡片", "tool_call_id": "call_00_4juu9uDX7V8J6OHmg0Z59451"},
    ]
    agent = _FakeAgent(messages)
    attach_reasoning_roundtrip(agent)

    agent.stream_handlers[0]({"reasoning_content": "用户确认了目标，"})
    agent.stream_handlers[0]({"reasoning_content": "应调用工具。"})
    agent.before_handlers[0](messages[2]["tool_calls"])

    assistants = [m for m in messages if m.get("role") == "assistant"]
    assert len(assistants) == 1
    assert assistants[0]["content"] == "好的，目标记下了。"
    assert assistants[0]["reasoning_content"] == "用户确认了目标，应调用工具。"
    assert assistants[0]["tool_calls"]


def test_does_not_overwrite_existing_reasoning():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "already",
            "tool_calls": [{"id": "c1", "function": {"name": "kb_search"}}],
        }
    ]
    agent = _FakeAgent(messages)
    attach_reasoning_roundtrip(agent)
    agent.stream_handlers[0]({"reasoning_content": "new"})
    agent.before_handlers[0](messages[0]["tool_calls"])
    assert messages[0]["reasoning_content"] == "already"
