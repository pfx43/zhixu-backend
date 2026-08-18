"""
Chat 领域事件归一化 — 把底层 Agent chunk 转为公开 SSE 合同。

规则：
- reasoning_content 分片 → {"type": "reasoning", ...}，并聚合完整思考内容
- tool_name（声明/参数分片/tool_calls）→ {"type": "tool_call", ...}，
  同一工具调用的连续分片合并为一条；工具被再次调用时发新事件（直播过程可重复）。
  tool_name 原样透传（前端维护名称/图标映射）
- role=tool 的工具结果 → 丢弃（不进入公开流，也不进入历史）
- 正文分片 → {"type": "answer", ...}
- 历史聚合 ``tool_names``：按首次出现顺序去重，刷新后图标一致；不含参数/结果
"""
from __future__ import annotations

from typing import Dict, List, Optional


def _function_name(tc) -> Optional[str]:
    fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
    if isinstance(fn, dict):
        return fn.get("name")
    return getattr(fn, "name", None) if fn else None


class ChatChunkNormalizer:
    """把底层 Agent chunk 归一为 Chat 领域事件，并聚合思考/工具名。"""

    def __init__(self):
        self.reasoning: str = ""
        self.tool_names: List[str] = []
        self._current_tool: Optional[str] = None

    def _remember_tool(self, name: str) -> None:
        if name not in self.tool_names:
            self.tool_names.append(name)

    def _tool_event(self, name: str) -> Dict:
        return {
            "type": "tool_call",
            "role": "assistant",
            "content": "",
            "tool_name": name,
        }

    def normalize(self, chunk: dict) -> List[Dict]:
        """归一单条 chunk；返回 0..N 条公开事件（一条 chunk 里多个 tool_calls 会拆开）。"""
        role = chunk.get("role", "assistant")

        if role == "tool":
            return []

        reasoning = chunk.get("reasoning_content")
        if reasoning:
            self.reasoning += reasoning
            return [
                {
                    "type": "reasoning",
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": reasoning,
                }
            ]

        tool_name = chunk.get("tool_name")
        if tool_name:
            if tool_name != self._current_tool:
                self._current_tool = tool_name
                self._remember_tool(tool_name)
                return [self._tool_event(tool_name)]
            return []

        tool_calls = chunk.get("tool_calls")
        if tool_calls:
            events: List[Dict] = []
            for tc in tool_calls:
                name = _function_name(tc)
                if not name:
                    continue
                self._remember_tool(name)
                if name == self._current_tool:
                    continue
                self._current_tool = name
                events.append(self._tool_event(name))
            return events

        content = chunk.get("content") or ""
        if content:
            return [
                {
                    "type": "answer",
                    "role": "assistant",
                    "content": content,
                }
            ]

        return []
