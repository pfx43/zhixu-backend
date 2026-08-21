"""出题工具包 — 通过 submit_question 工具结构化收集题目（避免从 LLM 文本解析 JSON）"""
import json
import logging
from typing import List

from tina import Tools

logger = logging.getLogger(__name__)


class QuestionGenTools:
    """出题工具包 — 收集 Agent 通过 submit_question 提交的结构化题目。

    工具调用即完成归一化并落到 submitted_questions，无需再依赖事件钩子。
    """

    def __init__(self):
        self.submitted_questions: List[dict] = []
        self.tools = Tools(name="question_gen")
        self.tools.register_tool(self.submit_question)

    def submit_question(
        self,
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
        normalized = _normalize_question(raw)
        if normalized:
            self.submitted_questions.append(normalized)
            return json.dumps({"status": "ok"}, ensure_ascii=False)
        return json.dumps(
            {"status": "invalid", "reason": "题目字段校验失败"},
            ensure_ascii=False,
        )

    def get_tools(self) -> Tools:
        """把工具包公开给 Agent 使用。"""
        return self.tools
