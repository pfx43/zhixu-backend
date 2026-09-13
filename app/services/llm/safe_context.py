"""Tina 默认截断一次只删 assistant + 一条 tool，并行多工具会留下孤儿 tool 消息。

DeepSeek 要求 role=tool 必须紧跟带 tool_calls 的 assistant，否则 400。

多模态：继承 ``MultimodalContextManager``，user 消息可按图片/音频/URL 构造
多模态 content；纯文本仍写字符串 content，保持与旧行为一致。
"""
from __future__ import annotations

from typing import Any, Optional

from tina.agent.core.context_manager import MultimodalContextManager


def _content_length(content: Any) -> int:
    """多模态 content 可能是 str 或 ``[{type: text/image_url, ...}]``。

    按可计文本长度估算：text part 取 text 长度，其余 part 计 1，避免列表
    被 ``len()`` 当成元素个数而低估。
    """
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                total += len(part.get("text") or "")
            else:
                total += 1
        return total
    return 0


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


class PairedContextManager(MultimodalContextManager):
    """滚动窗口时把一轮 tool_calls 和后面所有 tool 结果整组删除。

    继承多模态上下文管理器：``add_user_message`` 兼容「纯文本 1 参」和
    「带图 4 参」两种调用；纯文本仍写字符串 content。
    """

    def __init__(
        self,
        tools=None,
        max_length: int = 100000,
        max_tool_result_length: int = 6000,
    ) -> None:
        super().__init__(
            tools=tools,
            max_length=max_length,
            max_tool_result_length=max_tool_result_length,
        )

    def add_user_message(
        self,
        instruction: str,
        image: Optional[Any] = None,
        audio: Optional[Any] = None,
        url: Optional[Any] = None,
    ) -> list[dict]:
        if image or audio or url:
            return super().add_user_message(instruction, image, audio, url)
        self.messages.append({"role": "user", "content": instruction})
        self.limit_messages()
        return self.messages

    def add_assistant_message(self, message: str, name: str = None) -> list[dict]:
        """MultimodalContextManager 少了 name 参数，历史回填传 name 时会 TypeError。

        与基类 ContextManager.add_assistant_message 对齐，兼容带/不带 name。
        """
        self.messages.append(
            {"role": "assistant", "content": message}
            if name is None
            else {"role": "assistant", "content": message, "name": name}
        )
        self.limit_messages()
        return self.messages

    def get_messages(self) -> list[dict]:
        drop_orphan_tool_messages(self.messages)
        return self.messages

    def limit_messages(self) -> None:
        for msg in self.messages:
            if msg.get("content") is None:
                msg["content"] = ""

        total_length = sum(
            _content_length(msg.get("content", "")) for msg in self.messages
        )
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
                    total_length -= _content_length(
                        self.messages[i + offset].get("content", "")
                    )
                    self.messages.pop(i + offset)
                continue
            if msg.get("role") == "tool":
                total_length -= _content_length(msg.get("content", ""))
                self.messages.pop(i)
                continue
            total_length -= _content_length(msg.get("content", ""))
            self.messages.pop(i)

        drop_orphan_tool_messages(self.messages)

        if self.messages and total_length > self.max_length:
            sys_msg = self.messages[0]
            content = sys_msg.get("content", "")
            if isinstance(content, str) and len(content) > self.max_length:
                sys_msg["content"] = content[: self.max_length - 3] + "..."
