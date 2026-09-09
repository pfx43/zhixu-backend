"""今日任务候选人：程序算缺口，Agent 只从名单里挑。

出题只派「还没有题的页」；刷题带着 question_ids（未做 → 不会 → 错）。
同一天同一 fingerprint 不重插。模型不能编页码或题号。
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, timedelta
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from app.core.config import MAX_PAGES_PER_GEN
from app.crud import question as question_crud
from app.crud import quiz as quiz_crud
from app.crud import task as task_crud
from app.crud import toc as toc_crud
from app.models import DailyTask, Document, DocumentSegment, DocumentToc, Goal
from app.services.training import analytics_service

logger = logging.getLogger(__name__)

TYPE_UPLOAD = "upload"
TYPE_GENERATE = "generate_questions"
TYPE_PRACTICE = "practice"

_MAX_TASKS_PER_DAY = 3
_PRACTICE_COUNT_DEFAULT = 5
_STUDY_DOCS_CAP = 12


def today_local() -> date:
    from datetime import datetime

    return datetime.now().date()


def _active_goal(db: Session, user_id: int) -> Optional[Goal]:
    return (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status == "active")
        .order_by(Goal.created_at.desc())
        .first()
    )


def list_study_documents(db: Session, user_id: int) -> List[Document]:
    return (
        db.query(Document)
        .filter(Document.user_id == user_id, Document.zone == "study")
        .order_by(Document.created_at.desc())
        .all()
    )


def pages_from_toc(db: Session, document_id: str) -> List[int]:
    entries = toc_crud.list_toc_for_document(db, document_id)
    pages: List[int] = []
    seen = set()
    for entry in entries:
        for p in range(entry.page_start, entry.page_end + 1):
            if p >= 1 and p not in seen:
                seen.add(p)
                pages.append(p)
    return pages


def pages_from_segments(db: Session, document_id: str) -> List[int]:
    rows = (
        db.query(DocumentSegment.page_start, DocumentSegment.page_end)
        .filter(
            DocumentSegment.document_id == document_id,
            DocumentSegment.page_start.isnot(None),
        )
        .all()
    )
    pages: List[int] = []
    seen = set()
    for ps, pe in rows:
        start = max(1, ps or 1)
        end = max(start, pe or start)
        for p in range(start, end + 1):
            if p not in seen:
                seen.add(p)
                pages.append(p)
    return sorted(pages)


def document_pages(db: Session, document_id: str) -> List[int]:
    pages = pages_from_toc(db, document_id)
    if pages:
        return pages
    return pages_from_segments(db, document_id)


def pages_with_questions(
    db: Session, user_id: int, document_id: str
) -> set[int]:
    rows = question_crud.list_user_questions(db, user_id, document_id=document_id)
    have: set[int] = set()
    for _ref, q in rows:
        for prov in question_crud.list_provenance_for_question(db, q.id):
            if prov.document_id == document_id and prov.page_number:
                have.add(int(prov.page_number))
    return have


def document_toc_rows(db: Session, document_id: str) -> List[DocumentToc]:
    return toc_crud.list_toc_for_document(db, document_id)


def _question_stats(
    db: Session, user_id: int, document_id: str
) -> dict[str, Any]:
    rows = question_crud.list_user_questions(db, user_id, document_id=document_id)
    ids = [q.id for _ref, q in rows]
    stats_map = quiz_crud.get_user_answer_stats_for_questions(db, user_id, ids)
    undone: list[str] = []
    unknown: list[str] = []
    wrong: list[str] = []
    correct = 0
    tags_by_id: dict[str, list[str]] = {}
    stem_by_id: dict[str, str] = {}
    page_by_id: dict[str, Optional[int]] = {}
    for ref, q in rows:
        qid = q.id
        stem_by_id[qid] = (q.stem or "")[:80]
        tags_by_id[qid] = question_crud.parse_tags_json(q.tags) or []
        page_by_id[qid] = None
        for prov in question_crud.list_provenance_for_question(db, qid):
            if prov.document_id == document_id and prov.page_number:
                page_by_id[qid] = int(prov.page_number)
                break
        latest, attempts = stats_map.get(qid, (None, 0))
        if attempts <= 0 or not latest:
            undone.append(qid)
        elif latest == "unknown":
            unknown.append(qid)
        elif latest == "wrong":
            wrong.append(qid)
        elif latest == "correct":
            correct += 1
    return {
        "question_ids": ids,
        "undone": undone,
        "unknown": unknown,
        "wrong": wrong,
        "correct": correct,
        "tags_by_id": tags_by_id,
        "stem_by_id": stem_by_id,
        "page_by_id": page_by_id,
    }


def _pick_quiz_pool(stats: dict[str, Any]) -> tuple[list[str], str]:
    if stats["undone"]:
        return list(stats["undone"]), "没做"
    if stats["unknown"]:
        return list(stats["unknown"]), "不会"
    if stats["wrong"]:
        return list(stats["wrong"]), "错题"
    return [], ""


def fingerprint(task_type: str, payload: dict[str, Any]) -> str:
    blob = json.dumps(
        {
            "task_type": task_type,
            "document_id": payload.get("document_id"),
            "page_numbers": payload.get("page_numbers") or [],
            "question_ids": payload.get("question_ids") or [],
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]


def _today_fingerprints(db: Session, user_id: int, task_date: date) -> set[str]:
    rows = task_crud.list_tasks(db, user_id, task_date)
    out = set()
    for row in rows:
        payload = row.payload or {}
        fp = payload.get("_fingerprint")
        if fp:
            out.add(str(fp))
        else:
            out.add(fingerprint(row.task_type, payload))
    return out


def add_task_from_candidate(
    db: Session,
    *,
    user_id: int,
    cand: dict[str, Any],
    title: str,
    reason: str,
    payload: dict[str, Any],
    task_date: Optional[date] = None,
) -> Optional[DailyTask]:
    task_date = task_date or today_local()
    today_n = len(task_crud.list_tasks(db, user_id, task_date))
    if today_n >= _MAX_TASKS_PER_DAY:
        return None
    fp = fingerprint(cand["task_type"], payload)
    if fp in _today_fingerprints(db, user_id, task_date):
        return None
    stored = dict(payload)
    stored["_fingerprint"] = fp
    rule = dict(cand.get("completion_rule") or {})
    if cand["task_type"] == TYPE_GENERATE:
        rule["page_numbers"] = list(payload.get("page_numbers") or [])
        rule["document_id"] = payload.get("document_id")
        rule["kind"] = "pages_have_questions"
    elif cand["task_type"] == TYPE_PRACTICE:
        rule["count"] = int(payload.get("count") or payload.get("need") or 0)
        rule["document_id"] = payload.get("document_id")
        rule["kind"] = "practice_count"
    return task_crud.create_task(
        db,
        user_id=user_id,
        goal_id=cand.get("goal_id"),
        task_date=task_date,
        title=(title or cand["fallback_title"])[:255],
        reason=(reason or cand["fallback_reason"])[:1000],
        task_type=cand["task_type"],
        payload=stored,
        completion_rule=rule,
    )


def apply_candidate_quantity(
    cand: dict[str, Any], quantity: Optional[int]
) -> dict[str, Any]:
    payload = dict(cand.get("payload") or {})
    lo = int(cand.get("min_quantity") or 1)
    hi = int(cand.get("max_quantity") or lo)
    default = int(cand.get("default_quantity") or lo)
    n = default if not quantity else int(quantity)
    n = max(lo, min(hi, n))
    kind = cand["task_type"]
    if kind == TYPE_GENERATE:
        pages = list(payload.get("page_numbers") or [])[:n]
        payload["page_numbers"] = pages
        payload["need"] = len(pages)
    elif kind == TYPE_PRACTICE:
        ids = list(payload.get("question_ids") or [])[:n]
        payload["question_ids"] = ids
        payload["need"] = len(ids)
        payload["count"] = len(ids)
    return payload


def collect_task_candidates(db: Session, user_id: int) -> list[dict[str, Any]]:
    goal = _active_goal(db, user_id)
    goal_id = goal.id if goal else None
    out: list[dict[str, Any]] = []

    def _pack(**kwargs: Any) -> None:
        out.append(kwargs)

    docs = list_study_documents(db, user_id)
    if not docs:
        _pack(
            id="upload",
            task_type=TYPE_UPLOAD,
            goal_id=goal_id,
            payload={},
            completion_rule={"kind": "new_parsable_document"},
            fallback_title="上传一本学习资料",
            fallback_reason="学习区还没有可用的书，先上传一本能解析的资料，之后出题和刷题都从它来。",
            gap="学习区没有可用文档",
            min_quantity=1,
            max_quantity=1,
            default_quantity=1,
            unit="份",
        )
        return out

    for doc in docs[:8]:
        pages = document_pages(db, doc.id)
        have_q = pages_with_questions(db, user_id, doc.id)
        missing = [n for n in pages if n not in have_q]
        stats = _question_stats(db, user_id, doc.id)

        if missing:
            picked = missing[:MAX_PAGES_PER_GEN]
            n = len(picked)
            if n:
                _pack(
                    id=f"gen-{doc.id}",
                    task_type=TYPE_GENERATE,
                    goal_id=goal_id,
                    payload={
                        "document_id": doc.id,
                        "document_name": doc.display_name,
                        "page_numbers": picked,
                        "need": n,
                    },
                    completion_rule={
                        "kind": "pages_have_questions",
                        "document_id": doc.id,
                        "page_numbers": picked,
                    },
                    fallback_title=f"给《{doc.display_name}》还没题的页出题",
                    fallback_reason=f"还有 {len(missing)} 页没题，先出这些页才能按页刷。",
                    gap=(
                        f"《{doc.display_name}》{len(pages)} 页，已出题 {len(have_q)} 页，"
                        f"缺 {len(missing)} 页；这一次最多 {n} 页"
                    ),
                    min_quantity=1,
                    max_quantity=n,
                    default_quantity=n,
                    unit="页",
                )

        pool, label = _pick_quiz_pool(stats)
        if pool:
            n = len(pool)
            default_n = min(n, _PRACTICE_COUNT_DEFAULT)
            _pack(
                id=f"quiz-{doc.id}",
                task_type=TYPE_PRACTICE,
                goal_id=goal_id,
                payload={
                    "document_id": doc.id,
                    "document_name": doc.display_name,
                    "question_ids": pool,
                    "need": default_n,
                    "count": default_n,
                    "filter": label,
                },
                completion_rule={
                    "kind": "practice_count",
                    "document_id": doc.id,
                    "count": default_n,
                },
                fallback_title=f"刷《{doc.display_name}》的{label}题",
                fallback_reason=f"交够即可（含「不会」），不用全对。今日优先{label}。",
                gap=(
                    f"《{doc.display_name}》题 {len(stats['question_ids'])}："
                    f"未做 {len(stats['undone'])} / 不会 {len(stats['unknown'])} / "
                    f"错 {len(stats['wrong'])} / 对 {stats['correct']}；优先{label}，池子 {n} 道"
                ),
                min_quantity=1,
                max_quantity=n,
                default_quantity=default_n,
                unit="题",
            )
    return out


def fallback_assign(db: Session, user_id: int) -> List[DailyTask]:
    """Agent 不可用时：按缺口补，每类最多一条，不把已出题的页再派一遍。"""
    created: List[DailyTask] = []
    seen_types: set[str] = set()
    for cand in collect_task_candidates(db, user_id):
        if cand["task_type"] in seen_types:
            continue
        payload = apply_candidate_quantity(cand, cand.get("default_quantity"))
        row = add_task_from_candidate(
            db,
            user_id=user_id,
            cand=cand,
            title=cand["fallback_title"],
            reason=cand["fallback_reason"],
            payload=payload,
        )
        if row:
            created.append(row)
            seen_types.add(cand["task_type"])
        if len(created) >= 2:
            break
    return created


def search_questions_for_doc(
    db: Session,
    user_id: int,
    document_id: str,
    *,
    chapter_id: str = "",
    tag: str = "",
    status: str = "all",
    limit: int = 20,
) -> list[dict[str, Any]]:
    stats = _question_stats(db, user_id, document_id)
    want_pages: Optional[set[int]] = None
    if chapter_id.strip():
        cid = chapter_id.strip()
        for entry in document_toc_rows(db, document_id):
            if entry.id == cid or entry.title == cid:
                want_pages = set(range(entry.page_start, entry.page_end + 1))
                break
        if want_pages is None:
            return []

    status_set = {
        "undone": set(stats["undone"]),
        "unknown": set(stats["unknown"]),
        "wrong": set(stats["wrong"]),
        "all": set(stats["question_ids"]),
    }.get((status or "all").strip().lower(), set(stats["question_ids"]))

    tag_l = (tag or "").strip().lower()
    out: list[dict[str, Any]] = []
    for qid in stats["question_ids"]:
        if qid not in status_set:
            continue
        if want_pages is not None:
            page = stats["page_by_id"].get(qid)
            if page not in want_pages:
                continue
        tags = stats["tags_by_id"].get(qid) or []
        if tag_l and tag_l not in {str(t).strip().lower() for t in tags}:
            continue
        latest = "undone"
        if qid in stats["unknown"]:
            latest = "unknown"
        elif qid in stats["wrong"]:
            latest = "wrong"
        elif qid not in stats["undone"]:
            latest = "correct"
        out.append(
            {
                "question_id": qid,
                "status": latest,
                "stem_preview": stats["stem_by_id"].get(qid) or "",
                "tags": tags,
                "page_number": stats["page_by_id"].get(qid),
            }
        )
        if len(out) >= max(1, min(int(limit), 50)):
            break
    return out


def task_agent_context(
    db: Session, user_id: int, *, is_refill: bool = False
) -> dict[str, Any]:
    goal = _active_goal(db, user_id)
    task_date = today_local()
    today_rows = task_crud.list_tasks(db, user_id, task_date)
    pending = [t for t in today_rows if t.status == "pending"]
    done = [t for t in today_rows if t.status == "completed"]

    docs = list_study_documents(db, user_id)
    books = []
    for doc in docs[:_STUDY_DOCS_CAP]:
        pages = document_pages(db, doc.id)
        have_q = pages_with_questions(db, user_id, doc.id)
        stats = _question_stats(db, user_id, doc.id)
        chapters = []
        for entry in document_toc_rows(db, doc.id):
            ch_pages = list(range(entry.page_start, entry.page_end + 1))
            chapters.append(
                {
                    "id": entry.id,
                    "title": entry.title,
                    "page_start": entry.page_start,
                    "page_end": entry.page_end,
                    "pages_with_questions": sum(1 for p in ch_pages if p in have_q),
                    "page_count": len(ch_pages),
                }
            )
        books.append(
            {
                "document_id": doc.id,
                "name": doc.display_name,
                "pages": len(pages),
                "pages_with_questions": len(have_q),
                "missing_pages": max(0, len(pages) - len(have_q)),
                "question_count": len(stats["question_ids"]),
                "undone": len(stats["undone"]),
                "unknown": len(stats["unknown"]),
                "wrong": len(stats["wrong"]),
                "correct": stats["correct"],
                "chapters": chapters,
            }
        )

    history: list[dict[str, Any]] = []
    for delta in range(14):
        day = task_date - timedelta(days=delta)
        rows = task_crud.list_tasks(db, user_id, day)
        if not rows:
            continue
        history.append(
            {
                "date": day.isoformat(),
                "assigned": len(rows),
                "completed": sum(1 for r in rows if r.status == "completed"),
                "pending": sum(1 for r in rows if r.status == "pending"),
                "titles": [r.title for r in rows[:4]],
            }
        )

    assigned7 = sum(h["assigned"] for h in history if h["date"] >= (task_date - timedelta(days=7)).isoformat())
    completed7 = sum(h["completed"] for h in history if h["date"] >= (task_date - timedelta(days=7)).isoformat())
    rate7 = round(completed7 / assigned7, 2) if assigned7 else None

    weak_tags = []
    try:
        tag_stats = analytics_service.get_tag_stats(db, user_id)
        for item in (tag_stats.by_tag or [])[:8]:
            if (item.wrong_count or 0) <= 0 and (item.unknown_count or 0) <= 0:
                continue
            weak_tags.append(
                {
                    "tag": item.tag,
                    "accuracy_pct": int(round((item.accuracy_rate or 0) * 100)),
                    "wrong": item.wrong_count,
                    "attempts": item.total_attempts,
                }
            )
    except Exception:
        logger.warning("读取薄弱 tag 失败 user=%s", user_id, exc_info=True)

    stop_signals: list[str] = []
    if len(done) >= 3:
        stop_signals.append(f"今日已完成 {len(done)} 条")
    if rate7 is not None and rate7 < 0.4:
        stop_signals.append("近 7 天任务完成率偏低，宜减量")
    missing_pages = sum(int(b.get("missing_pages") or 0) for b in books)
    total_undone = sum(int(b.get("undone") or 0) for b in books)
    if books and total_undone < 5 and missing_pages < 2:
        stop_signals.append("主要资料缺口已不大")

    attrs = ""
    if goal and isinstance(goal.attributes, dict) and goal.attributes:
        attrs = json.dumps(goal.attributes, ensure_ascii=False)
    valid_until = ""
    if goal and goal.valid_until:
        valid_until = goal.valid_until.date().isoformat()

    return {
        "is_refill": is_refill,
        "goal_text": (goal.text if goal else "") or "",
        "goal_attributes": attrs,
        "valid_until": valid_until,
        "today": task_date.isoformat(),
        "today_assigned": len(today_rows),
        "today_completed": len(done),
        "pending_count": len(pending),
        "pending_titles": [t.title for t in pending],
        "today_done": [
            {"title": t.title, "kind": t.task_type, "reason": (t.reason or "")}
            for t in done
        ],
        "books": books,
        "history": history[:10],
        "assigned_7d": assigned7,
        "completed_7d": completed7,
        "completion_rate_7d": rate7,
        "weak_tags": weak_tags,
        "stop_signals": stop_signals,
    }
