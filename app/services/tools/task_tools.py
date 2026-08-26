"""Tina 派任务工具包（Issue #20）。

只调 Goal / KB / Question / Task 已有能力（积木），不新造数据通道：

- `user_id` 只来自登录：构造时由 Agent 注入（登录上下文），工具参数不带 user_id；
- 页码只来自目录（document_tocs）或入库分段页码（document_segments.page_start），
  超出范围的页码直接拒绝（禁止模型手填）；
- kind / 完成规则程序定（复用 task_service），模型只写标题和理由；
- 不暴露内部出题 Agent 的 `submit_question`。

提示词上下文（资料列表 / 当前目标 / 已布置今日任务）见 `build_user_context`。
"""
import json
import logging
from typing import List, Optional

from sqlalchemy import func
from tina import Tools

from app.core.database import short_session
from app.crud import kb as kb_crud
from app.crud import question as question_crud
from app.crud import toc as toc_crud
from app.models import Document, Goal, QuizAnswer, QuizSession
from app.services.quiz import question_gen_service
from app.services.tasks import task_service

logger = logging.getLogger(__name__)


def _valid_pages_for_document(db, document_id: str) -> List[int]:
    """该文档的合法页码：目录页范围 ∪ 入库分段页码（程序提取，禁止手填）。"""
    pages: List[int] = []
    seen = set()
    entries = toc_crud.list_toc_for_document(db, document_id)
    for e in entries:
        for p in range(e.page_start, e.page_end + 1):
            if p >= 1 and p not in seen:
                seen.add(p)
                pages.append(p)
    for p in task_service._pages_from_segments(db, document_id):
        if p not in seen:
            seen.add(p)
            pages.append(p)
    return sorted(pages)


def _document_quiz_stats(db, user_id: int, document_id: str) -> dict:
    """该文档的刷题统计（correct / wrong / unknown 数量）。"""
    rows = (
        db.query(QuizAnswer.status, func.count(QuizAnswer.id))
        .join(QuizSession, QuizSession.id == QuizAnswer.session_id)
        .filter(
            QuizSession.user_id == user_id,
            QuizSession.document_id == document_id,
        )
        .group_by(QuizAnswer.status)
        .all()
    )
    stats = {"correct_count": 0, "wrong_count": 0, "unknown_count": 0}
    for status, cnt in rows:
        key = f"{status}_count"
        if key in stats:
            stats[key] = cnt
    return stats


class TaskPlannerTools:
    """Tina 派任务工具包 — 读/改目标、看目录、按页出题、看缺口、写入今日任务。

    工具参数一律不含 user_id；user_id 由登录上下文在构造时注入。
    """

    def __init__(self, user_id: int, token: str = ""):
        self._user_id = user_id
        self._token = token

        self.tools = Tools(name="task_planner")
        for fn in (
            self.get_active_goal,
            self.revise_goal,
            self.get_document_toc,
            self.generate_questions,
            self.get_learning_gaps,
            self.ensure_today_tasks,
        ):
            self.tools.register_tool(fn)

    def get_tools(self) -> Tools:
        """把工具包公开给 Agent 使用。"""
        return self.tools

    # ── 目标（Goal） ──────────────────────────────────────────

    def get_active_goal(self) -> str:
        """
        读取当前进行中的目标。没有目标时返回 goal: null。

        Returns:
            JSON：{goal: {id, text, attributes, valid_until} | null}
        """
        with short_session() as db:
            goal = (
                db.query(Goal)
                .filter(Goal.user_id == self._user_id, Goal.status == "active")
                .order_by(Goal.created_at.desc())
                .first()
            )
            if not goal:
                return json.dumps({"goal": None}, ensure_ascii=False)
            return json.dumps(
                {
                    "goal": {
                        "id": goal.id,
                        "text": goal.text,
                        "attributes": goal.attributes,
                        "valid_until": (
                            goal.valid_until.isoformat() if goal.valid_until else None
                        ),
                    }
                },
                ensure_ascii=False,
            )

    def revise_goal(self, text: str, attributes_json: str = "") -> str:
        """
        设置或修改当前进行中的目标（一人一条 active：已存在则更新，否则新建）。

        Args:
            text (str): 目标描述，例如「研究生上岸」
            attributes_json (str): 可选，JSON 对象字符串，例如 {"subject":"计算机"}
        """
        attrs = None
        if attributes_json.strip():
            try:
                attrs = json.loads(attributes_json)
            except json.JSONDecodeError:
                return json.dumps(
                    {"error": "attributes_json 必须是合法的 JSON 对象字符串"},
                    ensure_ascii=False,
                )
        with short_session() as db:
            active = (
                db.query(Goal)
                .filter(Goal.user_id == self._user_id, Goal.status == "active")
                .with_for_update()
                .one_or_none()
            )
            if active is not None:
                active.text = text.strip()
                active.attributes = attrs
                goal = active
            else:
                goal = Goal(
                    user_id=self._user_id,
                    text=text.strip(),
                    attributes=attrs,
                    status="active",
                )
                db.add(goal)
            try:
                db.commit()
                db.refresh(goal)
            except Exception as e:  # pragma: no cover - 防御性
                db.rollback()
                logger.error("revise_goal 保存失败: %s", e)
                return json.dumps({"error": f"目标保存失败: {e}"}, ensure_ascii=False)
        return json.dumps(
            {"status": "ok", "goal": {"id": goal.id, "text": goal.text}},
            ensure_ascii=False,
        )

    # ── 目录（KB + Question） ────────────────────────────────

    def get_document_toc(self, document_id: str) -> str:
        """
        查看某本书的章节目录（章 → 页范围），并标出每章已有几道题。

        Args:
            document_id (str): 文档 ID（只允许访问当前登录用户自己的文档）
        """
        with short_session() as db:
            doc = kb_crud.get_document_by_id_or_dify(
                db, self._user_id, document_id
            )
            if not doc:
                return json.dumps(
                    {"error": "文档不存在或无权访问"}, ensure_ascii=False
                )
            entries = toc_crud.list_toc_for_document(db, doc.id)
            all_pages = [
                p
                for e in entries
                for p in range(e.page_start, e.page_end + 1)
            ]
            counts = (
                question_crud.count_questions_per_page(
                    db, self._user_id, doc.id, all_pages
                )
                if all_pages
                else {}
            )
            toc_out = [
                {
                    "title": e.title,
                    "page_start": e.page_start,
                    "page_end": e.page_end,
                    "question_count": sum(
                        counts.get(p, 0)
                        for p in range(e.page_start, e.page_end + 1)
                    ),
                }
                for e in entries
            ]
            segment_pages = task_service._pages_from_segments(db, doc.id)
            return json.dumps(
                {
                    "document_id": doc.id,
                    "document_name": doc.display_name,
                    "toc": toc_out,
                    "segment_pages": segment_pages,
                    "valid_pages": _valid_pages_for_document(db, doc.id),
                },
                ensure_ascii=False,
            )

    # ── 按页出题（KB + Question，页码必须来自目录/入库分段） ──

    async def generate_questions(
        self, document_id: str, page_numbers: str
    ) -> str:
        """
        对某本书的指定页按页出题（每页独立进度）。

        Args:
            document_id (str): 文档 ID（只允许访问当前登录用户自己的文档）
            page_numbers (str): 逗号分隔的页码，如 "1,2,3"。
                页码必须来自 get_document_toc 返回的 valid_pages，禁止自造页码。
        """
        try:
            pages = [int(x.strip()) for x in page_numbers.split(",") if x.strip()]
        except ValueError:
            return json.dumps(
                {"error": "page_numbers 必须是逗号分隔的页码，如 1,2,3"},
                ensure_ascii=False,
            )
        if not pages:
            return json.dumps(
                {"error": "至少提供一个页码"}, ensure_ascii=False
            )

        with short_session() as db:
            doc = kb_crud.get_document_by_id_or_dify(
                db, self._user_id, document_id
            )
            if not doc:
                return json.dumps(
                    {"error": "文档不存在或无权访问"}, ensure_ascii=False
                )
            valid_pages = _valid_pages_for_document(db, doc.id)
            invalid = [p for p in pages if p not in valid_pages]
            if invalid:
                return json.dumps(
                    {
                        "error": (
                            f"页码 {invalid} 不在目录/入库分段范围内，"
                            "禁止手填页码，只能使用 valid_pages"
                        ),
                        "valid_pages": valid_pages,
                    },
                    ensure_ascii=False,
                )
            doc_id = doc.id
            doc_name = doc.display_name

        try:
            if question_gen_service.is_question_gen_async():
                with short_session() as db:
                    result = await question_gen_service.schedule_generate_from_pages(
                        db=db,
                        user_id=self._user_id,
                        document_id=doc_id,
                        page_numbers=pages,
                        questions_per_page=1,
                        token=self._token,
                    )
                    db.commit()
                return json.dumps(
                    {
                        "status": "scheduled",
                        "document_id": doc_id,
                        "document_name": doc_name,
                        "page_numbers": pages,
                        "message": "已提交按页出题，稍后刷新目录可看到新题",
                    },
                    ensure_ascii=False,
                )
            with short_session() as db:
                result = await question_gen_service.generate_from_pages(
                    db=db,
                    user_id=self._user_id,
                    document_id=doc_id,
                    page_numbers=pages,
                    questions_per_page=1,
                    token=self._token,
                )
                db.commit()
            return json.dumps(
                {
                    "status": "completed",
                    "document_id": doc_id,
                    "document_name": doc_name,
                    "page_numbers": pages,
                    "questions_created": result.questions_created,
                    "questions_reused": result.questions_reused,
                    "total_questions": result.total_questions,
                },
                ensure_ascii=False,
            )
        except Exception as e:  # pragma: no cover - 出题链路错误透出给模型
            logger.error("generate_questions 出题失败: %s", e)
            return json.dumps(
                {"error": f"出题失败: {e}"}, ensure_ascii=False
            )

    # ── 缺口（书 / 题 / 刷） ─────────────────────────────────

    def get_learning_gaps(self) -> str:
        """
        查看当前学习缺口：有没有书、哪本没题、哪本已出题、错/不会统计。

        Returns:
            JSON：{has_book, documents: [{document_id, document_name,
                  question_count, pages_with_questions, wrong_count,
                  unknown_count, status}], gaps}
        """
        with short_session() as db:
            docs = (
                db.query(Document)
                .filter(Document.user_id == self._user_id)
                .order_by(Document.created_at.desc())
                .all()
            )
            if not docs:
                return json.dumps(
                    {
                        "has_book": False,
                        "documents": [],
                        "gaps": ["没有书：先上传一本能解析的学习资料"],
                    },
                    ensure_ascii=False,
                )

            items: List[dict] = []
            for doc in docs:
                question_count = task_service._count_user_questions_for_document(
                    db, self._user_id, doc.id
                )
                pages_with_questions = [
                    p
                    for p, c in question_crud.count_questions_per_page(
                        db,
                        self._user_id,
                        doc.id,
                        _valid_pages_for_document(db, doc.id),
                    ).items()
                    if c > 0
                ]
                stats = _document_quiz_stats(db, self._user_id, doc.id)
                items.append(
                    {
                        "document_id": doc.id,
                        "document_name": doc.display_name,
                        "question_count": question_count,
                        "pages_with_questions": pages_with_questions,
                        "wrong_count": stats["wrong_count"],
                        "unknown_count": stats["unknown_count"],
                        "status": "有题" if question_count > 0 else "没题",
                    }
                )

            gaps: List[str] = []
            no_question = [i for i in items if i["status"] == "没题"]
            if no_question:
                gaps.append(
                    "有书没题：" + "、".join(i["document_name"] for i in no_question)
                    + " 需要按页出题"
                )
            weak = [i for i in items if i["wrong_count"] > 0 or i["unknown_count"] > 0]
            if weak:
                gaps.append(
                    "有错/不会："
                    + "、".join(i["document_name"] for i in weak)
                    + " 需要刷题巩固"
                )
            if not gaps:
                gaps.append("没有明显缺口：可以继续按章刷题或出题")
            return json.dumps(
                {"has_book": True, "documents": items, "gaps": gaps},
                ensure_ascii=False,
            )

    # ── 写入今日任务（Task，kind/完成规则程序定） ──────────────

    def ensure_today_tasks(self) -> str:
        """
        按当前缺口确保今天有任务（没书→上传；有书没题→按页出题；有题→刷题）。
        当天已有未完成任务时不重复派。kind / 完成规则由程序定。

        Returns:
            JSON：{status, tasks: [{id, title, task_type, reason, payload, status}]}
        """
        with short_session() as db:
            tasks = task_service.ensure_today_tasks(db, self._user_id)
            out = [
                {
                    "id": t.id,
                    "title": t.title,
                    "task_type": t.task_type,
                    "reason": t.reason,
                    "payload": t.payload,
                    "status": t.status,
                }
                for t in tasks
            ]
        return json.dumps(
            {"status": "ok", "tasks": out}, ensure_ascii=False
        )


def build_user_context(user_id: int) -> str:
    """主对话提示词上下文：资料列表（没有写无）、当前目标、已布置的今日任务。"""
    with short_session() as db:
        docs = (
            db.query(Document)
            .filter(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .limit(20)
            .all()
        )
        doc_names = [d.display_name for d in docs] if docs else []
        goal = (
            db.query(Goal)
            .filter(Goal.user_id == user_id, Goal.status == "active")
            .order_by(Goal.created_at.desc())
            .first()
        )
        tasks = task_service.list_today(db, user_id)
        today = task_service.today_local().isoformat()

    lines = [f"今天是 {today}。"]
    lines.append("资料列表：" + ("、".join(doc_names) if doc_names else "无"))
    lines.append(
        "当前目标："
        + (goal.text if goal else "无（还没有目标，可引导用户写一条）")
    )
    if tasks:
        lines.append(
            "已布置的今日任务："
            + "；".join(
                f"({t.status}) {t.title}" for t in tasks
            )
        )
    else:
        lines.append("今日任务：未布置（可按缺口用 ensure_today_tasks 布置 1～3 件）")
    return "\n".join(lines)
