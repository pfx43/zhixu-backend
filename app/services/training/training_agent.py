"""
针对训练 / 学习教练 Agent — 独立 Tina Agent，负责选题与辅导对话
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Generator, List, Optional, TYPE_CHECKING

from app.utils import tina_loader  # noqa: F401
from tina import Agent
from tina.agent.core.tools import Tools

from app.services.llm.llm_config import create_base_api
from app.services.llm.llm_runner import (
    agent_predict_no_stream,
    iter_agent_continue_stream,
)
from app.services.training.training_tools import (
    get_user_wrong_stats_by_tag,
    search_questions_by_tags,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MAX_TRAINING_QUESTIONS = 20

SYSTEM_PROMPT = """你是知拾（Zhishi）的学习教练 Tina，负责「针对训练」的选题与辅导。

## 职责
1. 分析用户学习报告与错题 tag 统计，识别薄弱知识点
2. 调用工具从题库检索匹配题目，制定训练计划
3. 通过 submit_training_plan 提交结构化训练计划（question_ids、weak_tags、rationale）
4. 在后续辅导对话中，解释选题理由、薄弱点与复习建议

## 工作流程（制定计划时）
1. 先调用 get_user_wrong_stats_by_tag 了解错题分布
2. 若有报告摘要，结合报告中的薄弱 tag 分析
3. 调用 search_questions_by_tags 检索题目（优先覆盖薄弱 tag，最多 20 题）
4. 最后**必须**调用 submit_training_plan 提交计划；rationale 用中文说明为何选这些题、薄弱点在哪

## 辅导风格
- 清晰、鼓励、具体，使用中文
- 可引用本次训练计划中的 weak_tags 与 rationale
- 适当使用 Markdown 格式
"""


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
        self._submitted_plan: Optional[dict] = None
        self._phase_done: bool = False
        self.agent = None
        self.llm = None
        self.tools = None

        try:
            self.llm = create_base_api()
            self.tools = Tools(name="training_coach")
            self._register_tools(db)

            self.agent = Agent(
                llm=self.llm,
                tools=self.tools,
                system_prompt=SYSTEM_PROMPT,
                max_context_length=80000,
                max_tool_result_length=6000,
                name=f"training_coach_{user_id}_{agent_session_id[:8]}",
            )
            self._register_event_hooks()
        except Exception as e:
            logger.error("TrainingCoachAgent 初始化失败: user_id=%s error=%s", user_id, e)

    @property
    def is_ready(self) -> bool:
        return self.agent is not None

    def _register_event_hooks(self) -> None:
        coach = self

        @self.agent.after_tool_call()
        def capture_training_plan_submit(tool_name, tool_arguments, tool_result):
            if "submit_training_plan" in tool_name:
                coach._submitted_plan = {
                    "question_ids": list(tool_arguments.get("question_ids") or []),
                    "weak_tags": list(tool_arguments.get("weak_tags") or []),
                    "rationale": (tool_arguments.get("rationale") or "").strip(),
                }
                coach._phase_done = True
            return tool_name, tool_arguments, tool_result

    def _register_tools(self, db: "Session") -> None:
        user_id = self.user_id
        agent = self

        def get_user_wrong_stats_by_tag_tool(min_wrong: int = 1, limit: int = 10) -> str:
            """
            获取用户按 tag 的错题统计。

            Args:
                min_wrong (int): 最少错题次数
                limit (int): 返回条数上限
            """
            stats = get_user_wrong_stats_by_tag(
                db, user_id, min_wrong=min_wrong, limit=limit
            )
            return json.dumps({"stats": stats}, ensure_ascii=False)

        def search_questions_by_tags_tool(
            tags: str, limit: int = 20, question_types: str = ""
        ) -> str:
            """
            按知识点 tag 从题库检索题目 ID。

            Args:
                tags (str): 逗号分隔的 tag 名称
                limit (int): 最多返回题目数
                question_types (str): 可选，逗号分隔题型
            """
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            type_list = (
                [t.strip() for t in question_types.split(",") if t.strip()]
                if question_types
                else None
            )
            ids = search_questions_by_tags(
                db, user_id, tag_list, limit=limit, question_types=type_list
            )
            return json.dumps({"question_ids": ids, "count": len(ids)}, ensure_ascii=False)

        def submit_training_plan(
            question_ids: List[str],
            weak_tags: List[str],
            rationale: str,
        ) -> str:
            """
            提交针对训练计划（结构化输出，制定计划时必须调用）。

            Args:
                question_ids (List[str]): 选中的题目 ID 列表
                weak_tags (List[str]): 本次重点薄弱 tag
                rationale (str): 选题理由与薄弱点说明（中文）
            """
            return json.dumps(
                {"status": "ok", "question_count": len(question_ids)},
                ensure_ascii=False,
            )

        self.tools.register_tool(get_user_wrong_stats_by_tag_tool)
        self.tools.register_tool(search_questions_by_tags_tool)
        self.tools.register_tool(submit_training_plan)

    def plan_training(
        self,
        *,
        report_content: Optional[str] = None,
        report_title: Optional[str] = None,
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
        self._submitted_plan = None
        self._phase_done = False

        try:
            agent_predict_no_stream(self.agent, instruction=instruction)
        except Exception as e:
            logger.warning("TrainingCoachAgent.plan_training 失败: %s", e, exc_info=True)

        if self._submitted_plan:
            return TrainingPlanResult(
                question_ids=self._submitted_plan.get("question_ids") or [],
                weak_tags=self._submitted_plan.get("weak_tags") or [],
                rationale=self._submitted_plan.get("rationale") or "",
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

    def tutor_stream(self, message: str) -> Generator[dict, None, None]:
        """辅导对话流式输出（复用同一 Agent 会话上下文）。"""
        if not self.agent:
            yield {"role": "assistant", "content": "抱歉，AI 教练暂时不可用，请稍后重试。"}
            return

        try:
            for chunk in iter_agent_continue_stream(self.agent, message):
                yield {
                    "role": chunk.get("role", "assistant"),
                    "content": chunk.get("content", ""),
                    **(
                        {"reasoning_content": chunk["reasoning_content"]}
                        if chunk.get("reasoning_content")
                        else {}
                    ),
                    **({"tool_name": chunk["tool_name"]} if chunk.get("tool_name") else {}),
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
