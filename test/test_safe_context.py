"""并行 tool_calls 截断时不能留下孤儿 tool 消息。"""
from tina.agent.core.context_manager import ContextManager

from app.services.llm.safe_context import PairedContextManager, drop_orphan_tool_messages


def _parallel_round(prefix: str, n: int = 3, result_size: int = 100):
    calls = [
        {"id": f"{prefix}_{i}", "function": {"name": "kb_search"}}
        for i in range(n)
    ]
    assistant = {"role": "assistant", "content": "", "tool_calls": calls}
    tools = [
        {
            "role": "tool",
            "content": f"{prefix}-result-{i}-" + ("x" * result_size),
            "tool_call_id": f"{prefix}_{i}",
        }
        for i in range(n)
    ]
    return [assistant, *tools]


def test_tina_default_limit_leaves_orphan_tools():
    """复现日志：一轮 3 个 search，截断只带走 assistant + 第一条 tool。"""
    cm = ContextManager(max_length=80, max_tool_result_length=10000)
    cm.set_messages(
        [
            {"role": "system", "content": "sys"},
            *_parallel_round("old", 3, 40),
            *_parallel_round("new", 3, 40),
        ]
    )
    cm.limit_messages()
    roles = [m.get("role") for m in cm.messages]
    assert roles[0] == "system"
    assert "tool" in roles
    # 默认实现会在超长时拆开 tool 组
    first_non_system = next(m for m in cm.messages if m.get("role") != "system")
    assert first_non_system.get("role") == "tool"


def test_paired_limit_drops_whole_tool_group():
    cm = PairedContextManager(max_length=80, max_tool_result_length=10000)
    later = _parallel_round("new", 3, 10)
    cm.set_messages(
        [
            {"role": "system", "content": "sys"},
            *_parallel_round("old", 3, 40),
            *later,
        ]
    )
    cm.limit_messages()
    messages = cm.get_messages()
    assert messages[0]["role"] == "system"
    for i, msg in enumerate(messages):
        if msg.get("role") != "tool":
            continue
        prev = messages[i - 1]
        assert prev.get("role") in ("assistant", "tool")
        if prev.get("role") == "assistant":
            assert prev.get("tool_calls")


def test_drop_orphan_tools_matches_log():
    messages = [
        {"role": "system", "content": "prompt"},
        {
            "role": "tool",
            "content": "hits-1",
            "tool_call_id": "call_01_orphan",
        },
        {
            "role": "tool",
            "content": "hits-2",
            "tool_call_id": "call_02_orphan",
        },
        {
            "role": "assistant",
            "content": "再搜",
            "tool_calls": [{"id": "call_00_new", "function": {"name": "kb_search"}}],
        },
        {"role": "tool", "content": "ok", "tool_call_id": "call_00_new"},
    ]
    drop_orphan_tool_messages(messages)
    assert messages[1]["role"] == "assistant"
    assert messages[2]["tool_call_id"] == "call_00_new"
    assert all(m.get("tool_call_id") != "call_01_orphan" for m in messages)
