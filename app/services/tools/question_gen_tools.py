"""出题工具包 — 通过 submit_question 工具结构化收集题目（避免从 LLM 文本解析 JSON）"""
import json
import logging
from typing import Dict, List, Optional, Set

from tina import Tools

logger = logging.getLogger(__name__)


class QuestionGenTools:
    """出题工具包 — 收集 Agent 通过 submit_question 提交的结构化题目。

    工具调用即完成归一化并落到 submitted_questions，无需再依赖事件钩子。

    按页出题时额外注册 get_near_page：Agent 可查看当前出题页相邻页（offset ±1）
    的原文，避免正文截断后丢失上下文。页码必须落在本次选中范围 ±1 内
    （allowed_page_numbers），且有查询次数上限（max_near_lookups），
    防止 Agent 借邻页翻到范围外。
    """

    def __init__(
        self,
        *,
        pages: Optional[Dict[int, dict]] = None,
        allowed_page_numbers: Optional[Set[int]] = None,
        max_near_lookups: int = 3,
    ):
        self.pages: Dict[int, dict] = pages or {}
        self.allowed_page_numbers: Optional[Set[int]] = allowed_page_numbers
        self.max_near_lookups = max(1, max_near_lookups)
        self.near_lookup_count = 0
        self.submitted_questions: List[dict] = []
        self.tools = Tools(name="question_gen")
        self.tools.register_tool(self.submit_question)
        self.tools.register_tool(self.get_near_page)

    def get_near_page(self, page_number: int, offset: int) -> str:
        """查看当前出题页相邻一页的原文（每次只翻一页，offset 仅允许 +1 或 -1）。

        Args:
            page_number (int): 想看的相邻页页码（目标页 = page_number + offset）
            offset (int): 方向，只能 +1（下一页）或 -1（上一页）
        """
        if offset not in (-1, 1):
            return json.dumps(
                {"error": "offset 仅允许 -1 或 +1"}, ensure_ascii=False
            )
        target = page_number + offset
        if (
            self.allowed_page_numbers is not None
            and target not in self.allowed_page_numbers
        ):
            return json.dumps(
                {"error": f"页码 {target} 不在允许范围内"}, ensure_ascii=False
            )
        if self.near_lookup_count >= self.max_near_lookups:
            return json.dumps(
                {"error": "邻页查询次数已达上限"}, ensure_ascii=False
            )
        self.near_lookup_count += 1
        page = self.pages.get(target)
        if not page:
            return json.dumps(
                {"error": f"页码 {target} 不存在"}, ensure_ascii=False
            )
        content = (page.get("content") or "")[:1500]
        return json.dumps(
            {
                "page_number": target,
                "title": page.get("title") or f"第 {target} 页",
                "content": content,
            },
            ensure_ascii=False,
        )

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
