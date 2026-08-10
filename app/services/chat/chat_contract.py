"""
Chat 领域事件归一化 — 把底层 Agent chunk 转为公开 SSE 合同。

规则：
- reasoning_content 分片 → {"type": "reasoning", ...}，并聚合完整思考内容
- tool_name（声明/参数分片/tool_calls）→ {"type": "tool_call", ...}，仅首次出现发一条；
  tool_name 原样透传（前端维护公开展示映射）
- role=tool 的工具结果 → 丢弃（不进入公开流，也不进入历史）
- 正文分片 → {"type": "answer", ...}
- 聚合结果：完整 reasoning_content + 按首次出现顺序去重的 tool_names（供历史持久化）
"""
from __future__ import annotations

from typing import Dict, List, Optional


class ChatChunkNormalizer:
    """把底层 Agent chunk 归一为 Chat 领域事件，并聚合思考/工具名。"""

    def __init__(self):
        self.reasoning: str = ""
        self.tool_names: List[str] = []
        self._current_tool: Optional[str] = None

    def normalize(self, chunk: dict) -> Optional[Dict]:
        """归一单条 chunk；返回 Chat 事件 dict，丢弃时返回 None。"""
        role = chunk.get("role", "assistant")

        # 工具结果：不进入公开输出（含其 content）
        if role == "tool":
            return None

        # 思考分片
        reasoning = chunk.get("reasoning_content")
        if reasoning:
            self.reasoning += reasoning
            return {
                "type": "reasoning",
                "role": "assistant",
                "content": "",
                "reasoning_content": reasoning,
            }

        # 工具相关事件（声明 / 参数分片 / tool_calls）：工具名首次出现才发一条
        tool_name = chunk.get("tool_name")
        if tool_name:
            if tool_name != self._current_tool:
                self._current_tool = tool_name
                if tool_name not in self.tool_names:
                    self.tool_names.append(tool_name)
                return {
                    "type": "tool_call",
                    "role": "assistant",
                    "content": "",
                    "tool_name": tool_name,
                }
            return None

        # 正文分片
        content = chunk.get("content") or ""
        if content:
            return {
                "type": "answer",
                "role": "assistant",
                "content": content,
            }

        return None
