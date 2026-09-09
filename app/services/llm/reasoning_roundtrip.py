"""DeepSeek 思考模式 + tools：工具回合必须回传 reasoning_content。

Tina 会丢掉思考，并把同一轮拆成 content 一条 + tool_calls 一条。
用 on_stream_chunk 记下思考，在 before_tool_calls（json.loads 之前）写回。
工具参数解析失败时 after_tool_call 不会触发，所以不能只靠 after_tool_call。
"""
from __future__ import annotations

import logging

from tina import Agent

logger = logging.getLogger(__name__)


def _last_tool_calls_assistant(messages: list[dict]) -> dict | None:
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            return msg
        if role in ("user", "system"):
            break
    return None


def _tool_turn_key(tool_calls: list) -> str:
    ids = []
    for call in tool_calls or []:
        ids.append(str(call.get("id") or call.get("tool_call_id") or ""))
    return "|".join(ids)


def _merge_split_assistant(messages: list[dict], target: dict) -> None:
    """Tina 会把同一轮拆成 content 一条 + tool_calls 一条，合回 DeepSeek 要的一条。"""
    try:
        idx = messages.index(target)
    except ValueError:
        return
    if idx == 0:
        return
    prev = messages[idx - 1]
    if prev.get("role") != "assistant" or prev.get("tool_calls"):
        return
    if prev.get("content") and not target.get("content"):
        target["content"] = prev["content"]
    if prev.get("reasoning_content") and not target.get("reasoning_content"):
        target["reasoning_content"] = prev["reasoning_content"]
    messages.pop(idx - 1)


def _chunk_reasoning(chunk) -> str:
    if isinstance(chunk, dict):
        return str(chunk.get("reasoning_content") or "")
    return str(getattr(chunk, "reasoning_content", None) or "")


def attach_reasoning_roundtrip(agent: Agent) -> None:
    parts: list[str] = []
    patched: set[str] = set()

    def _on_stream_chunk(chunk) -> None:
        text = _chunk_reasoning(chunk)
        if text:
            parts.append(text)

    def _patch_last_tool_turn() -> None:
        messages = agent.context_manager.get_messages()
        target = _last_tool_calls_assistant(messages)
        if target is None:
            return
        key = _tool_turn_key(target.get("tool_calls") or [])
        if key in patched:
            return
        patched.add(key)
        reasoning = "".join(parts)
        parts.clear()
        if reasoning and not target.get("reasoning_content"):
            target["reasoning_content"] = reasoning
        _merge_split_assistant(messages, target)

    def _before_tool_calls(tool_calls) -> None:
        try:
            _patch_last_tool_turn()
        except Exception:
            logger.exception("回写工具回合 reasoning 失败")

    def _after_tool_call(tool_name: str, tool_arguments: dict, tool_result):
        try:
            _patch_last_tool_turn()
        except Exception:
            logger.exception("回写工具回合 reasoning 失败")
        return tool_name, tool_arguments, tool_result

    agent.add_on_stream_chunk_handler(_on_stream_chunk)
    agent.add_before_tool_calls_handler(_before_tool_calls)
    agent.add_after_tool_call_handler(_after_tool_call)
