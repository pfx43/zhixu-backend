"""
出题 Agent — 通过 tool call 结构化提交题目，避免从 LLM 文本解析 JSON
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from app.utils.tina_loader import tina_env_path
from tina import Agent
from tina.agent.core.tools import Tools
from tina.llm import BaseAPI

from app.services.llm.llm_runner import agent_predict_no_stream

logger = logging.getLogger(__name__)

GENERATE_SYSTEM_PROMPT = """你是知拾学习助手，根据给定文档内容生成练习题。

## 要求
- 覆盖核心知识点，难度适中
- tags 必须从用户已有 tag 列表中选择或复用相同含义的名称
- 单选题 answer 必须是 A/B/C/D；简答/应用题 options 可为空
- reference_text 为题目所依据的原文关键片段（100-300字）
- 生成完成后，对每道题调用 submit_question 提交结构化数据
- 全部提交完毕后回复「出题完成」"""

EXTRACT_SYSTEM_PROMPT = """你是知拾学习助手。给定教材页面内容，识别并提取其中自带的练习题。

## 要求
- 若页面无现成题目，直接回复「无现成题目」
- 对每道提取到的题目调用 submit_question 提交
- tags 优先复用已有 tag 名"""


class QuestionGenAgent:
    """出题 Agent — 通过 submit_question 工具结构化输出题目"""

    def __init__(self, mode: str = "generate"):
        self.mode = mode
        self._submitted_questions: List[dict] = []
        self._phase_done: bool = False
        self.agent = None
        self.llm = None
        self.tools = None
        self._system_prompt = (
            GENERATE_SYSTEM_PROMPT if mode == "generate" else EXTRACT_SYSTEM_PROMPT
        )

        try:
            self.llm = BaseAPI(env_path=tina_env_path())
            self.tools = Tools(name="question_gen")
            self._register_tools()

            self.agent = Agent(
                llm=self.llm,
                tools=self.tools,
                system_prompt=self._system_prompt,
                max_context_length=60000,
                max_tool_result_length=4000,
                name=f"question_gen_{mode}",
            )
            self._register_event_hooks()
        except Exception as e:
            logger.error("QuestionGenAgent 初始化失败: %s", e)

    @property
    def is_ready(self) -> bool:
        return self.agent is not None

    def _register_event_hooks(self) -> None:
        gen_agent = self

        @self.agent.after_tool_call()
        def capture_submit_question(tool_name, tool_arguments, tool_result):
            if "submit_question" not in tool_name:
                return tool_name, tool_arguments, tool_result
            try:
                result_data = json.loads(tool_result) if isinstance(tool_result, str) else {}
            except json.JSONDecodeError:
                result_data = {}
            if result_data.get("status") != "ok":
                return tool_name, tool_arguments, tool_result
            from app.services.quiz.question_gen_service import _normalize_question

            options = []
            for key, arg_key in [
                ("A", "option_a"),
                ("B", "option_b"),
                ("C", "option_c"),
                ("D", "option_d"),
            ]:
                text = (tool_arguments.get(arg_key) or "").strip()
                if text:
                    options.append({"key": key, "text": text})
            tags_raw = tool_arguments.get("tags") or ""
            tag_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
            raw = {
                "stem": (tool_arguments.get("stem") or "").strip(),
                "question_type": (tool_arguments.get("question_type") or "").strip().lower(),
                "options": options,
                "answer": (tool_arguments.get("answer") or "").strip(),
                "explanation": (tool_arguments.get("explanation") or "").strip() or None,
                "tags": tag_list,
                "reference_text": (tool_arguments.get("reference_text") or "").strip() or None,
            }
            normalized = _normalize_question(raw)
            if normalized:
                gen_agent._submitted_questions.append(normalized)
                gen_agent._phase_done = True
            return tool_name, tool_arguments, tool_result

    def _register_tools(self) -> None:
        def submit_question(
            stem: str,
            question_type: str,
            answer: str,
            option_a: str = "",
            option_b: str = "",
            option_c: str = "",
            option_d: str = "",
            explanation: str = "",
            tags: str = "",
            reference_text: str = "",
        ) -> str:
            """
            提交一道结构化题目（出题时必须调用）。

            Args:
                stem (str): 题干
                question_type (str): 题型 single_choice / short_answer / application
                answer (str): 正确答案
                option_a (str): 选项 A 文本（单选题）
                option_b (str): 选项 B 文本
                option_c (str): 选项 C 文本
                option_d (str): 选项 D 文本
                explanation (str): 解析
                tags (str): 逗号分隔的知识点 tag
                reference_text (str): 原文参考片段
            """
            options = []
            for key, text in [
                ("A", option_a),
                ("B", option_b),
                ("C", option_c),
                ("D", option_d),
            ]:
                if text and text.strip():
                    options.append({"key": key, "text": text.strip()})

            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            from app.services.quiz.question_gen_service import _normalize_question

            raw = {
                "stem": stem.strip(),
                "question_type": question_type.strip().lower(),
                "options": options,
                "answer": answer.strip(),
                "explanation": explanation.strip() or None,
                "tags": tag_list,
                "reference_text": reference_text.strip() or None,
            }
            if _normalize_question(raw):
                return json.dumps({"status": "ok"}, ensure_ascii=False)
            return json.dumps({"status": "invalid", "reason": "题目字段校验失败"}, ensure_ascii=False)

        self.tools.register_tool(submit_question)

    def generate_from_content(
        self,
        *,
        title: str,
        content: str,
        tag_hint: str = "",
        count: int = 1,
    ) -> List[dict]:
        """根据文档内容生成题目，返回结构化题目列表。"""
        self._submitted_questions = []
        self._phase_done = False
        if not self.agent:
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
            agent_predict_no_stream(self.agent, instruction=instruction)
        except Exception as e:
            logger.warning("QuestionGenAgent.generate_from_content 失败: %s", e, exc_info=True)

        return list(self._submitted_questions)


def agent_generate_for_segment(segment, *, tag_hint: str = "") -> List[dict]:
    """Agent 路径：按分段出题，失败时返回空列表由调用方 fallback。"""
    agent = QuestionGenAgent(mode="generate")
    if not agent.is_ready:
        return []
    title = segment.title or "（无标题）"
    questions = agent.generate_from_content(
        title=title,
        content=segment.content,
        tag_hint=tag_hint,
        count=1,
    )
    return questions


def agent_generate_for_page(page: dict, *, count: int = 1, tag_hint: str = "") -> List[dict]:
    """Agent 路径：按页出题。"""
    agent = QuestionGenAgent(mode="generate")
    if not agent.is_ready:
        return []
    title = page.get("title") or f"第 {page.get('page_number', '?')} 页"
    return agent.generate_from_content(
        title=title,
        content=page["content"],
        tag_hint=tag_hint,
        count=count,
    )


def agent_extract_for_page(page: dict, *, tag_hint: str = "") -> List[dict]:
    """Agent 路径：按页提取题目。"""
    agent = QuestionGenAgent(mode="extract")
    if not agent.is_ready:
        return []
    title = page.get("title") or f"第 {page.get('page_number', '?')} 页"
    return agent.generate_from_content(
        title=title,
        content=page["content"],
        tag_hint=tag_hint,
    )
