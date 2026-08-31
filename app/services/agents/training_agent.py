"""
针对训练 / 学习教练 Agent — 独立 Tina Agent，负责选题与辅导对话
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator, List, Optional, TYPE_CHECKING

from tina import Agent

from app.services.llm.llm_pool import llm_pool
from app.services.llm.reasoning_roundtrip import attach_reasoning_roundtrip
from app.services.tools.training_tools import TrainingTools
from app.utils.prompt_loader import load_prompt

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MAX_TRAINING_QUESTIONS = 20


def _chunk_to_dict(chunk) -> dict:
    if isinstance(chunk, dict):
        return chunk
    if hasattr(chunk, "model_dump"):
        try:
            return chunk.model_dump()
        except Exception:
            pass
    role = getattr(chunk, "role", None) or "assistant"
    content = getattr(chunk, "content", None)
    if content is None and hasattr(chunk, "get"):
        content = chunk.get("content", "")
    result = {"role": role, "content": content or ""}
    for key in ("reasoning_content", "tool_name", "tool_calls"):
        val = getattr(chunk, key, None)
        if val is None and isinstance(chunk, dict):
            val = chunk.get(key)
        if val:
            result[key] = val
    return result

SYSTEM_PROMPT = load_prompt("training_coach")


@dataclass
class TrainingPlanResult:
    question_ids: List[str] = field(default_factory=list)
    weak_tags: List[str] = field(default_factory=list)
    rationale: str = ""
    agent_session_id: str = ""


class TrainingCoachAgent:
    """学习教练 Agent — 制定训练计划 + 同会话辅导"""

    def __init__(self, user_id: int, agent_session_id: str, db: "Session"):
        self.user_id = user_id
        self.agent_session_id = agent_session_id
        self._db = db
        self.training_tools: Optional[TrainingTools] = None
        self.agent = None
        self.llm = None
        self.tools = None

        try:
            self.llm = llm_pool.acquire()
            if self.llm is None:
                raise RuntimeError("LLMPool 为空")
            self.training_tools = TrainingTools(db, user_id)
            self.tools = self.training_tools.get_tools()

            self.agent = Agent(
                llm=self.llm,
                tools=self.tools,
                system_prompt=SYSTEM_PROMPT,
                max_context_length=80000,
                max_tool_result_length=6000,
                name=f"training_coach_{user_id}_{agent_session_id[:8]}",
            )
            attach_reasoning_roundtrip(self.agent)
        except Exception as e:
            logger.error("TrainingCoachAgent 初始化失败: user_id=%s error=%s", user_id, e)

    @property
    def is_ready(self) -> bool:
        return self.agent is not None

    async def plan_training(
        self,
        *,
        report_content: Optional[str] = None,
        report_title: Optional[str] = None,
        token: Optional[str] = None,
    ) -> TrainingPlanResult:
        """运行 Agent 制定训练计划，返回结构化结果。"""
        if not self.agent:
            return TrainingPlanResult(agent_session_id=self.agent_session_id)

        parts = [
            "请为用户制定一轮「针对训练」计划。",
            "步骤：分析错题统计 → 检索题目 → 调用 submit_training_plan 提交。",
        ]
        if report_content:
            title = report_title or "最新学习报告"
            excerpt = report_content[:4000]
            parts.append(f"\n## {title}\n{excerpt}")
        else:
            parts.append("\n（暂无学习报告，请主要依据错题 tag 统计。）")

        instruction = "\n".join(parts)
        if self.training_tools is not None:
            self.training_tools.submitted_plan = None

        try:
            self.llm.set_token(token or "")
            async for _chunk in self.agent.apredict(instruction=instruction):
                pass
        except Exception as e:
            logger.warning("TrainingCoachAgent.plan_training 失败: %s", e, exc_info=True)

        submitted_plan = self.training_tools.submitted_plan if self.training_tools else None

        if submitted_plan:
            return TrainingPlanResult(
                question_ids=submitted_plan.get("question_ids") or [],
                weak_tags=submitted_plan.get("weak_tags") or [],
                rationale=submitted_plan.get("rationale") or "",
                agent_session_id=self.agent_session_id,
            )
        return TrainingPlanResult(agent_session_id=self.agent_session_id)

    def inject_plan_context(self, rationale: str, weak_tags: List[str], question_ids: List[str]) -> None:
        """将已保存的训练计划注入 Agent 上下文（用于服务重启后恢复辅导）。"""
        if not self.agent:
            return
        weak_str = "、".join(weak_tags) if weak_tags else "（未指定）"
        msg = (
            f"## 本次针对训练计划（已制定）\n"
            f"- 薄弱 tag：{weak_str}\n"
            f"- 题目数量：{len(question_ids)}\n"
            f"- 选题理由：{rationale or '（无）'}\n"
        )
        try:
            self.agent.add_message(role="assistant", content=msg)
        except Exception as e:
            logger.warning("注入训练计划上下文失败: %s", e)

    async def tutor_stream(
        self, message: str, token: Optional[str] = None
    ) -> AsyncGenerator[dict, None]:
        """辅导对话流式输出（复用同一 Agent 会话上下文）。"""
        if not self.agent:
            yield {"role": "assistant", "content": "抱歉，AI 教练暂时不可用，请稍后重试。"}
            return

        try:
            self.llm.set_token(token or "")
            async for chunk in self.agent.apredict(instruction=message):
                mapped = _chunk_to_dict(chunk)
                content = mapped.get("content", "")
                yield {
                    "role": mapped.get("role", "assistant"),
                    "content": content,
                    **(
                        {"reasoning_content": mapped["reasoning_content"]}
                        if mapped.get("reasoning_content")
                        else {}
                    ),
                    **({"tool_name": mapped["tool_name"]} if mapped.get("tool_name") else {}),
                }
        except Exception as e:
            logger.error("TrainingCoachAgent.tutor_stream 错误: %s", e)
            yield {"role": "assistant", "content": f"抱歉，生成回复时出错了：{str(e)}"}


class TrainingAgentManager:
    """按 agent_session_id 管理 TrainingCoachAgent 实例，支持同会话辅导。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._agents: dict[str, TrainingCoachAgent] = {}
        self._last_access: dict[str, float] = {}

    def create_agent(self, user_id: int, db: "Session") -> TrainingCoachAgent:
        session_id = str(uuid.uuid4())
        agent = TrainingCoachAgent(user_id, session_id, db)
        with self._lock:
            self._agents[session_id] = agent
            self._last_access[session_id] = time.time()
        return agent

    def get_agent(
        self, agent_session_id: str, user_id: int
    ) -> Optional[TrainingCoachAgent]:
        with self._lock:
            agent = self._agents.get(agent_session_id)
            if agent and agent.user_id == user_id:
                self._last_access[agent_session_id] = time.time()
                return agent
            return None

    def register_agent(self, agent_session_id: str, agent: TrainingCoachAgent) -> None:
        with self._lock:
            self._agents[agent_session_id] = agent
            self._last_access[agent_session_id] = time.time()

    def remove_agent(self, agent_session_id: str) -> None:
        with self._lock:
            self._agents.pop(agent_session_id, None)
            self._last_access.pop(agent_session_id, None)


training_agent_manager = TrainingAgentManager()
