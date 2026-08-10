"""
出题 Agent — 通过 tool call 结构化提交题目，避免从 LLM 文本解析 JSON。

生成模式失败时返回一个仅供服务内部传播的失败标记。该标记无法通过题目字段
校验，因此现有批处理会将文档终态设置为 failed，而不会继续走固定模板回退。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from tina import Agent

from app.services.llm.llm_config import create_base_api
from app.services.llm.llm_runner import agent_predict_no_stream
from app.services.tools.question_gen_tools import QuestionGenTools
from app.utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

GENERATE_SYSTEM_PROMPT = load_prompt("question_gen_agent_generate")
EXTRACT_SYSTEM_PROMPT = load_prompt("question_gen_agent_extract")

QUESTION_GENERATION_FAILURE_KEY = "_question_generation_failure"
_FAILURE_REASONS = {
    "agent_unavailable",
    "llm_timeout",
    "llm_error",
    "invalid_output",
}

_last_readiness = {
    "ready": False,
    "status": "unknown",
    "reason": "not_checked",
}


def _classify_failure(exc: BaseException) -> str:
    """将内部异常映射为稳定、去敏的失败分类。"""
    name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in name or "timed out" in message:
        return "llm_timeout"
    return "llm_error"


def _failure_marker(reason: str) -> List[dict]:
    """返回不会通过 _normalize_question 的内部失败标记。"""
    stable_reason = reason if reason in _FAILURE_REASONS else "llm_error"
    return [{QUESTION_GENERATION_FAILURE_KEY: stable_reason}]


def is_generation_failure_marker(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get(QUESTION_GENERATION_FAILURE_KEY) in _FAILURE_REASONS
    )


def get_question_agent_readiness(*, probe: bool = True) -> dict:
    """返回独立于 TCN 的 Question Agent/LLM readiness。

    服务尚未尝试初始化出题 Agent 时，health 探针可通过 ``probe=True`` 做一次轻量
    初始化检查。响应只暴露稳定分类，不包含密钥、上游地址或异常正文。
    """
    if probe and not _last_readiness["ready"]:
        QuestionGenAgent(mode="generate")
    return dict(_last_readiness)


class QuestionGenAgent:
    """出题 Agent — 通过 submit_question 工具结构化输出题目。"""

    def __init__(self, mode: str = "generate"):
        self.mode = mode
        self.question_tools: Optional[QuestionGenTools] = None
        self.failure_reason: Optional[str] = None
        self.agent = None
        self.llm = None
        self.tools = None
        self._system_prompt = (
            GENERATE_SYSTEM_PROMPT if mode == "generate" else EXTRACT_SYSTEM_PROMPT
        )

        try:
            self.llm = create_base_api()
            self.question_tools = QuestionGenTools()
            self.tools = self.question_tools.get_tools()

            self.agent = Agent(
                llm=self.llm,
                tools=self.tools,
                system_prompt=self._system_prompt,
                max_context_length=60000,
                max_tool_result_length=4000,
                name=f"question_gen_{mode}",
            )
            _last_readiness.update(
                ready=True,
                status="ok",
                reason=None,
            )
        except Exception:
            self.failure_reason = "agent_unavailable"
            _last_readiness.update(
                ready=False,
                status="unavailable",
                reason=self.failure_reason,
            )
            logger.exception(
                "QuestionGenAgent 初始化失败: classification=%s",
                self.failure_reason,
            )

    @property
    def is_ready(self) -> bool:
        return self.agent is not None

    def generate_from_content(
        self,
        *,
        title: str,
        content: str,
        tag_hint: str = "",
        count: int = 1,
        user_id: int = 0,
        token: Optional[str] = None,
    ) -> List[dict]:
        """根据文档内容生成题目，返回结构化题目列表。"""
        if self.question_tools is not None:
            self.question_tools.submitted_questions = []
        self.failure_reason = None
        if not self.agent:
            self.failure_reason = self.failure_reason or "agent_unavailable"
            return []

        if self.mode == "extract":
            instruction = (
                f"页面：{title}\n\n页面内容：\n{content[:4000]}\n\n"
                f"{tag_hint}\n\n请提取本页自带题目，逐题调用 submit_question。"
            )
        else:
            instruction = (
                f"段落/页面：{title}\n\n内容：\n{content[:3000]}\n\n"
                f"{tag_hint}\n\n"
                f"请生成 {count} 道练习题，逐题调用 submit_question 提交。"
            )

        try:
            self.llm.set_token(token or "")
            agent_predict_no_stream(self.agent, instruction=instruction)
        except Exception as exc:
            self.failure_reason = _classify_failure(exc)
            _last_readiness.update(
                ready=False,
                status="degraded",
                reason=self.failure_reason,
            )
            logger.exception(
                "QuestionGenAgent.generate_from_content 失败: classification=%s",
                self.failure_reason,
            )
            return []

        submitted_questions = (
            self.question_tools.submitted_questions if self.question_tools else []
        )

        if not submitted_questions and self.mode == "generate":
            self.failure_reason = "invalid_output"
            _last_readiness.update(
                ready=False,
                status="degraded",
                reason=self.failure_reason,
            )
            logger.warning(
                "QuestionGenAgent 无有效结构化输出: classification=%s",
                self.failure_reason,
            )
        elif submitted_questions:
            _last_readiness.update(
                ready=True,
                status="ok",
                reason=None,
            )

        return list(submitted_questions)


def agent_generate_for_segment(segment, *, tag_hint: str = "", token: Optional[str] = None) -> List[dict]:
    """Agent 路径：按分段出题；失败时返回内部失败标记。"""
    agent = QuestionGenAgent(mode="generate")
    if not agent.is_ready:
        return _failure_marker(agent.failure_reason or "agent_unavailable")
    title = segment.title or "（无标题）"
    questions = agent.generate_from_content(
        title=title,
        content=segment.content,
        tag_hint=tag_hint,
        count=1,
        token=token,
    )
    if questions:
        return questions
    return _failure_marker(agent.failure_reason or "invalid_output")


def agent_generate_for_page(
    page: dict, *, count: int = 1, tag_hint: str = "", token: Optional[str] = None
) -> List[dict]:
    """Agent 路径：按页出题；失败时返回内部失败标记。"""
    agent = QuestionGenAgent(mode="generate")
    if not agent.is_ready:
        return _failure_marker(agent.failure_reason or "agent_unavailable")
    title = page.get("title") or f"第 {page.get('page_number', '?')} 页"
    questions = agent.generate_from_content(
        title=title,
        content=page["content"],
        tag_hint=tag_hint,
        count=count,
        token=token,
    )
    if questions:
        return questions
    return _failure_marker(agent.failure_reason or "invalid_output")


def agent_extract_for_page(
    page: dict, *, tag_hint: str = "", token: Optional[str] = None
) -> List[dict]:
    """Agent 路径：按页提取题目；无现成题目仍返回空列表。"""
    agent = QuestionGenAgent(mode="extract")
    if not agent.is_ready:
        logger.warning(
            "QuestionGenAgent 提取不可用: classification=%s",
            agent.failure_reason or "agent_unavailable",
        )
        return []
    title = page.get("title") or f"第 {page.get('page_number', '?')} 页"
    return agent.generate_from_content(
        title=title,
        content=page["content"],
        tag_hint=tag_hint,
        token=token,
    )
