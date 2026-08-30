"""Tina 默认截断一次只删 assistant + 一条 tool，并行多工具会留下孤儿 tool 消息。

DeepSeek 要求 role=tool 必须紧跟带 tool_calls 的 assistant，否则 400。
"""
from __future__ import annotations

from tina.agent.core.context_manager import ContextManager


def drop_orphan_tool_messages(messages: list[dict]) -> None:
    """删掉前面没有对应 assistant.tool_calls 的 tool 消息。"""
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") != "tool":
            i += 1
            continue
        parent = None
        for j in range(i - 1, -1, -1):
            prev = messages[j]
            if prev.get("role") == "tool":
                continue
            if prev.get("role") == "assistant" and prev.get("tool_calls"):
                parent = prev
            break
        if parent is None:
            messages.pop(i)
            continue
        ids = {
            str(call.get("id") or call.get("tool_call_id") or "")
            for call in parent.get("tool_calls") or []
        }
        tool_id = str(msg.get("tool_call_id") or "")
        if tool_id and tool_id not in ids:
            messages.pop(i)
            continue
        i += 1


class PairedContextManager(ContextManager):
    """滚动窗口时把一轮 tool_calls 和后面所有 tool 结果整组删除。"""

    def get_messages(self) -> list[dict]:
        drop_orphan_tool_messages(self.messages)
        return self.messages

    def limit_messages(self) -> None:
        for msg in self.messages:
            if msg.get("content") is None:
                msg["content"] = ""

        total_length = sum(len(msg.get("content", "")) for msg in self.messages)
        i = 1
        while total_length > self.max_length and len(self.messages) > 1:
            if i >= len(self.messages):
                break
            msg = self.messages[i]
            if msg.get("tool_calls"):
                n = 1
                while (
                    i + n < len(self.messages)
                    and self.messages[i + n].get("role") == "tool"
                ):
                    n += 1
                for offset in range(n - 1, -1, -1):
                    total_length -= len(self.messages[i + offset].get("content", ""))
                    self.messages.pop(i + offset)
                continue
            if msg.get("role") == "tool":
                total_length -= len(msg.get("content", ""))
                self.messages.pop(i)
                continue
            total_length -= len(msg.get("content", ""))
            self.messages.pop(i)

        drop_orphan_tool_messages(self.messages)

        if self.messages and total_length > self.max_length:
            sys_msg = self.messages[0]
            content = sys_msg.get("content", "")
            if len(content) > self.max_length:
                sys_msg["content"] = content[: self.max_length - 3] + "..."
