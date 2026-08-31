"""Tina 派任务工具包（Issue #20 + #18 tip）。

只调 Goal / KB / Question / Task / Note 已有能力（积木），不新造数据通道：

- `user_id` 只来自登录：构造时由 Agent 注入（登录上下文），工具参数不带 user_id；
- 页码只来自目录（document_tocs）或入库分段页码（document_segments.page_start），
  超出范围的页码直接拒绝（禁止模型手填）；
- kind / 完成规则程序定（复用 task_service），模型只写标题和理由；
- tip（#18）：只读写当前用户的 tip；关联文档必须属于当前用户，否则拒绝；
- 展示题目 / tip：校验归属后写入 pending_ui，由 SSE 推给前端嵌卡；不含答案；
- 不暴露内部出题 Agent 的 `submit_question`。

提示词上下文（资料列表 / 当前目标 / 已布置今日任务）见 `build_user_context`。
"""
import json
import logging
import threading
from typing import List, Optional

from sqlalchemy import func
from tina import Tools

from app.core.database import short_session
from app.crud import kb as kb_crud
from app.crud import note as note_crud
from app.crud import question as question_crud
from app.crud import quiz as quiz_crud
from app.crud import toc as toc_crud
from app.models import Document, Goal, QuizAnswer, QuizSession, User, UserNote, UserQuestionRef
from app.services.quiz import question_gen_service, qgen_job_service
from app.services.tasks import task_service

logger = logging.getLogger(__name__)

_TYPE_LABEL = {
    "single_choice": "单选",
    "multiple_choice": "多选",
    "true_false": "判断",
    "fill_blank": "填空",
    "ordering": "排序",
    "matching": "匹配",
    "classification": "分类",
    "classify": "分类",
}
_STATUS_LABEL = {
    "correct": "做对",
    "wrong": "做错",
    "unknown": "不会",
}
_SEARCH_STATUSES = {"all", "undone", "wrong", "unknown"}


def _stem_preview(stem: str, limit: int = 40) -> str:
    text = (stem or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _public_options(raw: Optional[str]):
    parsed = question_crud.parse_options_json(raw)
    if isinstance(parsed, dict):
        return {
            "items": parsed.get("items") or [],
            "categories": parsed.get("categories") or [],
        }
    if not isinstance(parsed, list):
        return None
    out = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        opt = {}
        if item.get("key") is not None:
            opt["key"] = item["key"]
        if item.get("text") is not None:
            opt["text"] = item["text"]
        if item.get("side") is not None:
            opt["side"] = item["side"]
        if opt:
            out.append(opt)
    return out or None


def _public_question(gq, document_id: Optional[str], document_name: Optional[str]) -> dict:
    """给前端嵌卡用的题目公开字段；不含 answer / explanation。"""
    return {
        "question_id": gq.id,
        "stem": gq.stem,
        "question_type": gq.question_type,
        "options": _public_options(gq.options),
        "document_id": document_id,
        "document_name": document_name,
        "tags": question_crud.parse_tags_json(gq.tags) or [],
    }


def _public_tip(note: UserNote) -> dict:
    return {
        "id": note.id,
        "title": note.title,
        "content_md": note.content_md,
        "tags": note.tags or [],
        "document_id": note.document_id,
        "source": note.source,
    }


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
        self._pending_ui: List[dict] = []
        self._lock = threading.Lock()

        self.tools = Tools(name="task_planner")
        for fn in (
            self.get_active_goal,
            self.revise_goal,
            self.get_document_toc,
            self.generate_questions,
            self.get_learning_gaps,
            self.ensure_today_tasks,
            self.list_tips,
            self.create_tip,
            self.search_questions,
            self.show_question,
            self.show_tip,
        ):
            self.tools.register_tool(fn)

    def drain_ui(self) -> List[dict]:
        with self._lock:
            items = list(self._pending_ui)
            self._pending_ui.clear()
        return items

    def _emit(self, item: dict) -> None:
        with self._lock:
            self._pending_ui.append(item)

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
        查看某本书的章节目录（章 → 页范围），并标出每章已有几道题、哪些页已出过题。
        出题前先调用本工具：结合章节标题判断哪些页有考点，不要把 valid_pages 整份交给 generate_questions。

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
            segment_pages = task_service._pages_from_segments(db, doc.id)
            valid_pages = _valid_pages_for_document(db, doc.id)
            count_pages = sorted(set(all_pages) | set(valid_pages))
            counts = (
                question_crud.count_questions_per_page(
                    db, self._user_id, doc.id, count_pages
                )
                if count_pages
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
            pages_with_questions = sorted(
                p for p, c in counts.items() if c > 0
            )
            from app.services.tcn.domains import label_for_domain

            domain_id = getattr(doc, "tcn_domain", None)
            return json.dumps(
                {
                    "document_id": doc.id,
                    "document_name": doc.display_name,
                    "toc": toc_out,
                    "segment_pages": segment_pages,
                    "valid_pages": valid_pages,
                    "pages_with_questions": pages_with_questions,
                    "tcn_domain": domain_id,
                    "tcn_domain_label": (
                        label_for_domain(db, domain_id) if domain_id else None
                    ),
                },
                ensure_ascii=False,
            )

    # ── 按页出题（KB + Question，页码必须来自目录/入库分段） ──

    async def generate_questions(
        self, document_id: str, page_numbers: str
    ) -> str:
        """
        对某本书的指定页按页出题（每页独立进度）。

        调用前必须先自己判断页码：get_document_toc（必要时 search 抽看原文），
        只选出真正有考点、且尚未出题的页。选中的页一次全部传入即可（可一整章），
        出题队列同时最多跑 10 个 Agent（一页一个），不会截断页列表。

        Args:
            document_id (str): 文档 ID（只允许访问当前登录用户自己的文档）
            page_numbers (str): 逗号分隔的页码，如 "1,2,3"。
                页码必须来自 get_document_toc 返回的 valid_pages，禁止自造页码。
                跳过封面、目录、已有题的页（见 pages_with_questions）。
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
            if question_gen_service.is_question_gen_worker():
                with short_session() as db:
                    result = qgen_job_service.enqueue_generate_from_pages(
                        db=db,
                        user_id=self._user_id,
                        document_id=doc_id,
                        page_numbers=pages,
                        questions_per_page=None,
                    )
                    db.commit()
                return json.dumps(
                    {
                        "status": "scheduled",
                        "document_id": doc_id,
                        "document_name": doc_name,
                        "page_numbers": pages,
                        "job_id": result.job_id,
                        "message": "已提交按页出题，稍后刷新目录可看到新题",
                    },
                    ensure_ascii=False,
                )
            if question_gen_service.is_question_gen_async():
                with short_session() as db:
                    result = await question_gen_service.schedule_generate_from_pages(
                        db=db,
                        user_id=self._user_id,
                        document_id=doc_id,
                        page_numbers=pages,
                        questions_per_page=None,
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
                    questions_per_page=None,
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

    async def ensure_today_tasks(self) -> str:
        """
        按当前缺口确保今天有任务（没书→上传；有书没题→按页出题；有题→刷题）。
        当天已有未完成任务时不重复派。kind / 完成规则由程序定。

        Returns:
            JSON：{status, tasks: [{id, title, task_type, reason, payload, status}]}
        """
        with short_session() as db:
            tasks = await task_service.ensure_today_tasks_async(db, self._user_id)
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

    # ── tip（#18：走笔记接口 note_type=tip，只动当前用户） ──────

    def list_tips(self, tag: str = "", limit: int = 20) -> str:
        """
        查看当前用户收的 tip（note_type=tip，新的在前），可按用户给的类型筛选。

        Args:
            tag (str): 可选，按用户给 tip 打的类型筛选（难词 / 易错点…），
                       不传或为空则返回最近的全部 tip
            limit (int): 最多返回条数，默认 20
        """
        with short_session() as db:
            rows = note_crud.list_notes(
                db,
                self._user_id,
                note_type="tip",
                tag=(tag.strip() or None),
                limit=max(1, min(int(limit), 50)),
            )
            tips = [
                {
                    "id": r.id,
                    "title": r.title,
                    "content_md": r.content_md,
                    "tags": r.tags,
                    "document_id": r.document_id,
                    "source": r.source,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
        return json.dumps({"tips": tips, "count": len(tips)}, ensure_ascii=False)

    def create_tip(
        self,
        title: str,
        content_md: str = "",
        tags: str = "",
        document_id: str = "",
    ) -> str:
        """
        代做一张 tip（note_type=tip，写入当前用户的笔记）。

        Args:
            title (str): tip 标题（用用户话里的简短说法）
            content_md (str): 划选原文 / 那句要收的话
            tags (str): 可选，逗号分隔的用户分类（难词 / 易错点…）。
                        用户没说要归哪类就留空，不要替用户乱分类
            document_id (str): 可选，关联哪本资料。只能填当前用户自己
                                资料列表里出现过的 id；填他人文档会被拒绝
        """
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags.strip() else None
        doc_id = document_id.strip() or None

        with short_session() as db:
            if doc_id:
                doc = kb_crud.get_document_by_id_or_dify(db, self._user_id, doc_id)
                if not doc:
                    return json.dumps(
                        {"error": "文档不存在或无权访问，只能关联当前用户自己的资料"},
                        ensure_ascii=False,
                    )
            note = note_crud.create_note(
                db,
                user_id=self._user_id,
                title=(title or "").strip()[:255],
                content_md=content_md,
                note_type="tip",
                tags=tag_list,
                document_id=doc_id,
                source="tina",
            )
            db.commit()
            db.refresh(note)
        tip = _public_tip(note)
        self._emit({"kind": "show_tip", "tip": tip})
        return json.dumps(
            {
                "status": "ok",
                "tip": {
                    "id": note.id,
                    "title": note.title,
                    "tags": note.tags,
                    "document_id": note.document_id,
                },
                "message": "已向用户展示 tip 卡片。不必再调用 show_tip。",
            },
            ensure_ascii=False,
        )

    # ── 对话嵌卡：搜题 / 展示题目 / 展示 tip ─────────────────

    def search_questions(
        self,
        keyword: str = "",
        document_id: str = "",
        tag: str = "",
        status: str = "all",
    ) -> str:
        """
        按书 / 关键词 / 知识点 tag / 作答状态检索当前用户题库，只返回摘要和 id，不含答案。
        要在聊天里嵌可作答题卡时，再调用 show_question(question_id)。

        Args:
            keyword (str): 题干关键词，可空
            document_id (str): 某一本书的 id，可空（空则在当前用户全部题里搜）
            tag (str): 题目知识点 tag，可空
            status (str): all / undone / wrong / unknown
        """
        keyword = "" if keyword is None else str(keyword)
        document_id = "" if document_id is None else str(document_id)
        tag = "" if tag is None else str(tag)
        status_key = ("" if status is None else str(status)).strip().lower() or "all"
        if status_key not in _SEARCH_STATUSES:
            status_key = "all"

        with short_session() as db:
            scoped_doc_id = None
            if document_id.strip():
                doc = kb_crud.get_document_by_id_or_dify(
                    db, self._user_id, document_id.strip()
                )
                if not doc:
                    return json.dumps(
                        {"error": "文档不存在或无权访问"}, ensure_ascii=False
                    )
                scoped_doc_id = doc.id
            rows = question_crud.list_user_questions(
                db, self._user_id, document_id=scoped_doc_id
            )
            qids = [gq.id for _, gq in rows]
            stats = quiz_crud.get_user_answer_stats_for_questions(
                db, self._user_id, qids
            )
            keyword_l = keyword.strip()
            tag_l = tag.strip().lower()
            matched = []
            for ref, gq in rows:
                if keyword_l and keyword_l not in (gq.stem or ""):
                    continue
                tags = question_crud.parse_tags_json(gq.tags) or []
                if tag_l and tag_l not in {str(t).strip().lower() for t in tags}:
                    continue
                latest, attempts = stats.get(gq.id, (None, 0))
                if status_key == "undone" and attempts:
                    continue
                if status_key == "wrong" and latest != "wrong":
                    continue
                if status_key == "unknown" and latest != "unknown":
                    continue
                st = "未做"
                if attempts:
                    st = _STATUS_LABEL.get(latest or "", "已做")
                kind = _TYPE_LABEL.get(gq.question_type, gq.question_type)
                matched.append(
                    {
                        "question_id": gq.id,
                        "stem_preview": _stem_preview(gq.stem),
                        "question_type": kind,
                        "status": st,
                        "document_id": ref.document_id,
                        "tags": tags,
                    }
                )
                if len(matched) >= 8:
                    break

        if not matched:
            return json.dumps(
                {"questions": [], "count": 0, "message": "没有匹配的题目。"},
                ensure_ascii=False,
            )
        lines = [
            f'- [{item["question_type"]}][{item["status"]}] {item["stem_preview"]} '
            f'| id="{item["question_id"]}" | book="{item["document_id"] or "-"}"'
            for item in matched
        ]
        return json.dumps(
            {
                "questions": matched,
                "count": len(matched),
                "message": (
                    "检索到的题目（不含答案）。要用可答题卡片展示给用户时，"
                    "调用 show_question(question_id)。"
                ),
                "lines": lines,
            },
            ensure_ascii=False,
        )

    def show_question(self, question_id: str) -> str:
        """
        在对话里向用户展示一道可作答的题（前端渲染答题卡）。不要把答案写进回复。

        Args:
            question_id (str): 题目 id，来自 search_questions 或用户指定
        """
        qid = (question_id or "").strip()
        if not qid:
            return json.dumps({"error": "缺少 question_id"}, ensure_ascii=False)
        with short_session() as db:
            ref = (
                db.query(UserQuestionRef)
                .filter(
                    UserQuestionRef.user_id == self._user_id,
                    UserQuestionRef.question_id == qid,
                )
                .first()
            )
            if not ref:
                return json.dumps(
                    {"error": "题目不存在或无权访问"}, ensure_ascii=False
                )
            gq = question_crud.get_question_by_id(db, qid)
            if not gq:
                return json.dumps(
                    {"error": "题目不存在或无权访问"}, ensure_ascii=False
                )
            doc_name = None
            if ref.document_id:
                doc = kb_crud.get_document_by_id_or_dify(
                    db, self._user_id, ref.document_id
                )
                doc_name = doc.display_name if doc else None
            payload = _public_question(gq, ref.document_id, doc_name)
        self._emit({"kind": "show_question", "question": payload})
        kind = _TYPE_LABEL.get(gq.question_type, gq.question_type)
        return json.dumps(
            {
                "status": "ok",
                "question_id": gq.id,
                "message": (
                    f"已向用户展示可答题卡片。题型={kind} id={gq.id} "
                    f"题干={_stem_preview(gq.stem)}。"
                    "等待用户作答，不要把答案或选项对错写进文字。"
                ),
            },
            ensure_ascii=False,
        )

    def show_tip(self, tip_id: str) -> str:
        """
        在对话里向用户摊开一张 tip 卡片。只能展示当前用户自己的 tip。

        Args:
            tip_id (str): tip 的笔记 id，来自 list_tips 或刚 create_tip 的返回
        """
        nid = (tip_id or "").strip()
        if not nid:
            return json.dumps({"error": "缺少 tip_id"}, ensure_ascii=False)
        with short_session() as db:
            note = note_crud.get_note_by_id(db, self._user_id, nid)
            if not note or note.note_type != "tip":
                return json.dumps(
                    {"error": "tip 不存在或无权访问"}, ensure_ascii=False
                )
            payload = _public_tip(note)
        self._emit({"kind": "show_tip", "tip": payload})
        return json.dumps(
            {
                "status": "ok",
                "tip_id": note.id,
                "message": f"已向用户展示 tip 卡片：{note.title or note.id}。",
            },
            ensure_ascii=False,
        )


def build_user_context(user_id: int) -> str:
    """主对话提示词上下文：资料学情、当前目标、已布置的今日任务。"""
    from app.services.tasks.candidates import task_agent_context

    with short_session() as db:
        ctx = task_agent_context(db, user_id)
        tasks = task_service.list_today(db, user_id)
        user = db.query(User).filter(User.id == user_id).one_or_none()

    nickname = (user.nickname if user else "") or "还不知道"
    role = (user.signature if user else "") or "还不知道"
    lines = [
        f"今天是 {ctx['today']}。",
        f"称呼：{nickname}",
        f"身份：{role}",
    ]
    books = ctx.get("books") or []
    if books:
        names = [b["name"] for b in books]
        lines.append("资料列表：" + "、".join(names))
        for b in books:
            lines.append(
                f"  《{b['name']}》页={b['pages']} 已出题页={b['pages_with_questions']} "
                f"缺页={b['missing_pages']} 题={b['question_count']} "
                f"未做={b['undone']} 不会={b['unknown']} 错={b['wrong']}"
            )
    else:
        lines.append("资料列表：无")
    goal = ctx.get("goal_text") or ""
    if goal:
        extra = []
        if ctx.get("goal_attributes"):
            extra.append(ctx["goal_attributes"])
        if ctx.get("valid_until"):
            extra.append("有效期 " + ctx["valid_until"])
        suffix = f"（{'；'.join(extra)}）" if extra else ""
        lines.append("当前目标：" + goal + suffix)
    else:
        lines.append("当前目标：无（还没有目标，可引导用户写一条）")
    if tasks:
        lines.append(
            "已布置的今日任务："
            + "；".join(f"({t.status}) {t.title}" for t in tasks)
        )
    else:
        lines.append("今日任务：未布置（可按缺口用 ensure_today_tasks 布置；由任务 Agent 看目标和学情决定，也可以 0 条）")
    return "\n".join(lines)
