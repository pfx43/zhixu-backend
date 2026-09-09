"""任务 Agent 工具：只能从候选人派，或检索后用程序校验过的题号布置刷题。

不要加 from __future__ import annotations：Tina 用 inspect 读真实类型。
"""

from typing import Optional

from tina import Tools

from app.crud import kb as kb_crud
from app.services.tasks.candidates import (
    TYPE_PRACTICE,
    add_task_from_candidate,
    apply_candidate_quantity,
    document_toc_rows,
    search_questions_for_doc,
)


def _parse_id_list(raw: str) -> list[str]:
    text = "" if raw is None else str(raw)
    parts = []
    for chunk in text.replace(";", ",").replace("，", ",").replace("、", ",").split(","):
        s = chunk.strip()
        if s:
            parts.append(s)
    seen = set()
    out = []
    for p in parts:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


class TaskAssignTools:
    def __init__(self, user_id: int, candidates: list, db):
        self.user_id = user_id
        self.db = db
        self.candidates = {c["id"]: c for c in candidates}
        self.assigned: list[str] = []
        self.tools = Tools(name="task")
        self.tools.register_tool(tool=self.assign_task)
        self.tools.register_tool(tool=self.list_book_chapters)
        self.tools.register_tool(tool=self.search_book_questions)
        self.tools.register_tool(tool=self.assign_quiz_task)

    def get_tools(self):
        return self.tools

    def assign_task(
        self,
        candidate_id: str,
        title: str,
        reason: str,
        quantity: Optional[int] = None,
    ) -> str:
        """从候选人列表布置一条今日任务。candidate_id 必须来自候选人。
        Args:
            candidate_id: 候选人 id，例如 upload、gen-xxx、quiz-xxx
            title: 短、具体（哪本书、刷几道、出几页），对准目标，不要鸡汤
            reason: 一句学情：为什么今天派、为何这个量、和目标有什么关系
            quantity: 刷题道数或出题页数。不填则用候选人默认数量
        """
        cid = (candidate_id or "").strip()
        cand = self.candidates.get(cid)
        if not cand:
            ids = "、".join(self.candidates.keys()) or "无"
            return f"没有这个候选人：{cid}。只能用：{ids}"
        if cid in self.assigned:
            return "这条已经派过了。"
        qty = None
        if quantity is not None:
            try:
                qty = int(quantity)
            except (TypeError, ValueError):
                qty = None
        payload = apply_candidate_quantity(cand, qty)
        title_text = (title or "").strip() or cand["fallback_title"]
        reason_text = (reason or "").strip() or cand["fallback_reason"]
        row = add_task_from_candidate(
            self.db,
            user_id=self.user_id,
            cand=cand,
            title=title_text,
            reason=reason_text,
            payload=payload,
        )
        if not row:
            return "这条今天已经存在，或今天已满 3 件。换一个候选人，或停。"
        self.assigned.append(cid)
        used = (
            payload.get("need")
            or len(payload.get("page_numbers") or [])
            or len(payload.get("question_ids") or [])
            or 1
        )
        unit = cand.get("unit") or "项"
        return f"已布置 [{len(self.assigned)}] {title_text}（{used}{unit}）。还可以继续派，也可以停。可以一条都不继续。"

    def list_book_chapters(self, document_id: str) -> str:
        """列出某本资料的章节（id + 标题 + 页范围 + 已出题页数）。
        Args:
            document_id: 资料文档 id
        """
        doc_id = (document_id or "").strip()
        if not doc_id:
            return "缺少 document_id"
        doc = kb_crud.get_document_by_id_or_dify(self.db, self.user_id, doc_id)
        if not doc:
            return f"找不到文档或无权访问：{doc_id}"
        chapters = document_toc_rows(self.db, doc.id)
        if not chapters:
            return f"《{doc.display_name}》还没有目录。出题页码用来自分段的页，刷题用 search_book_questions。"
        from app.services.tasks.candidates import pages_with_questions

        have = pages_with_questions(self.db, self.user_id, doc.id)
        lines = [f"《{doc.display_name}》章节（页码来自目录，不是模型编的）："]
        for i, ch in enumerate(chapters, 1):
            have_n = sum(1 for p in range(ch.page_start, ch.page_end + 1) if p in have)
            total = max(0, ch.page_end - ch.page_start + 1)
            lines.append(
                f'{i}. id="{ch.id}" | {ch.title} | 页 {ch.page_start}-{ch.page_end} '
                f"| 已出题页 {have_n}/{total}"
            )
        return "\n".join(lines)

    def search_book_questions(
        self,
        document_id: str,
        chapter_id: str = "",
        tag: str = "",
        status: str = "all",
        limit: int = 20,
    ) -> str:
        """按书检索题目，返回题目 id，供 assign_quiz_task 使用。
        Args:
            document_id: 资料文档 id
            chapter_id: 章节 id（来自 list_book_chapters），可空
            tag: 知识点标签，可空
            status: all / undone / wrong / unknown
            limit: 最多返回多少道，默认 20，上限 50
        """
        doc_id = (document_id or "").strip()
        if not doc_id:
            return "缺少 document_id"
        doc = kb_crud.get_document_by_id_or_dify(self.db, self.user_id, doc_id)
        if not doc:
            return f"找不到文档或无权访问：{doc_id}"
        try:
            lim = int(limit)
        except (TypeError, ValueError):
            lim = 20
        rows = search_questions_for_doc(
            self.db,
            self.user_id,
            doc.id,
            chapter_id=chapter_id or "",
            tag=tag or "",
            status=status or "all",
            limit=lim,
        )
        if not rows:
            return "没有匹配的题目。可换章节、标签或 status 再试。"
        ids = [r["question_id"] for r in rows]
        lines = [
            f"《{doc.display_name}》检索到 {len(rows)} 题。"
            f"布置刷题请调用 assign_quiz_task(document_id, question_ids, title, reason)，"
            f"question_ids 用逗号拼接下面的 id。"
        ]
        for r in rows:
            tags = "、".join(r.get("tags") or []) or "-"
            lines.append(
                f'- [{r.get("status")}] {r.get("stem_preview")} | id="{r["question_id"]}"'
                f' | page={r.get("page_number") or "-"} | tags={tags}'
            )
        lines.append("question_ids 候选：" + ",".join(ids))
        return "\n".join(lines)

    def assign_quiz_task(
        self,
        document_id: str,
        question_ids: str,
        title: str,
        reason: str,
    ) -> str:
        """布置刷题：必须传入本题 id 列表（来自 search_book_questions 或候选人）。
        Args:
            document_id: 资料文档 id
            question_ids: 题目 id，逗号分隔
            title: 任务名称
            reason: 为什么派这些题、和目标有什么关系
        """
        doc_id = (document_id or "").strip()
        ids = _parse_id_list(question_ids)
        if not doc_id:
            return "缺少 document_id"
        if not ids:
            return "缺少 question_ids。请先 search_book_questions。"
        if len(ids) > 50:
            ids = ids[:50]
        doc = kb_crud.get_document_by_id_or_dify(self.db, self.user_id, doc_id)
        if not doc:
            return f"找不到文档或无权访问：{doc_id}"
        owned = search_questions_for_doc(
            self.db, self.user_id, doc.id, status="all", limit=200
        )
        owned_ids = {r["question_id"] for r in owned}
        valid = [qid for qid in ids if qid in owned_ids]
        if not valid:
            return "这些 question_id 都不属于该用户的这本书。"
        key = "quiz-ids-" + ",".join(valid[:5]) + f"-{len(valid)}"
        if key in self.assigned:
            return "同样的题目列表今天已经派过了。"
        from app.models import Goal

        active = (
            self.db.query(Goal)
            .filter(Goal.user_id == self.user_id, Goal.status == "active")
            .order_by(Goal.created_at.desc())
            .first()
        )
        cand = {
            "id": key,
            "task_type": TYPE_PRACTICE,
            "goal_id": active.id if active else None,
            "completion_rule": {
                "kind": "practice_count",
                "document_id": doc.id,
                "count": len(valid),
            },
            "fallback_title": title or "刷题",
            "fallback_reason": reason or "",
        }
        payload = {
            "document_id": doc.id,
            "document_name": doc.display_name,
            "question_ids": valid,
            "need": len(valid),
            "count": len(valid),
            "filter": "自选",
        }
        title_text = (title or "").strip() or f"刷《{doc.display_name}》"
        reason_text = (reason or "").strip() or "按章节或标签选题。"
        row = add_task_from_candidate(
            self.db,
            user_id=self.user_id,
            cand=cand,
            title=title_text,
            reason=reason_text,
            payload=payload,
        )
        if not row:
            return "同样的刷题任务今天已经存在，或今天已满 3 件。"
        self.assigned.append(key)
        _ = goal
        return (
            f"已布置 [{len(self.assigned)}] {title_text}（{len(valid)}题）。"
            f"还可以继续派，也可以停。"
        )
