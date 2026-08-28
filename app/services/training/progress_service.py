"""进度 / 学习路径聚合服务（纯聚合现有表，不新增表、不依赖 TCN）。

全部查询按当前 user_id 隔离，数据来源：
- documents（上传）
- user_question_refs + global_questions（题库）
- question_provenance.page_number（题目来源页，功能 B/#17 已入库）
- document_tocs（章 → 页，功能 B）
- quiz_answers（刷题记录）
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crud import kb as kb_crud
from app.crud import question as question_crud
from app.crud import quiz as quiz_crud
from app.crud import toc as toc_crud
from app.models import Document, GlobalQuestion, Goal, QuestionProvenance, QuizAnswer
from app.schemas.progress import (
    ChapterProgressOut,
    DocumentLearningPathOut,
    HeatmapDayOut,
    LearningPathOut,
    ProgressHeatmapOut,
    ProgressOverviewOut,
    ProgressTimelineOut,
    TagProgressOut,
    TimelineItemOut,
)


def _accuracy(correct: int, wrong: int) -> Optional[int]:
    graded = correct + wrong
    if graded <= 0:
        return None
    return round(correct / graded * 100)


def _counts_from_stats(
    question_ids: List[str], stats_map: Dict[str, Tuple[Optional[str], int]]
) -> Dict[str, int]:
    result = {
        "answered": 0,
        "correct": 0,
        "wrong": 0,
        "unknown": 0,
    }
    for qid in question_ids:
        latest_status, attempt_count = stats_map.get(qid, (None, 0))
        if attempt_count <= 0:
            continue
        result["answered"] += 1
        if latest_status == "correct":
            result["correct"] += 1
        elif latest_status == "wrong":
            result["wrong"] += 1
        elif latest_status == "unknown":
            result["unknown"] += 1
    return result


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_progress_overview(db: Session, user_id: int) -> ProgressOverviewOut:
    docs, total_docs = kb_crud.list_documents(db, user_id, page=1, limit=10000)
    study_docs = [d for d in docs if d.zone == "study"]

    rows = question_crud.list_user_questions(db, user_id)
    question_ids = [q.id for _, q in rows]
    stats_map = quiz_crud.get_user_answer_stats_for_questions(db, user_id, question_ids)
    counts = _counts_from_stats(question_ids, stats_map)

    total_study_seconds = (
        db.query(func.coalesce(func.sum(QuizAnswer.time_spent_seconds), 0))
        .filter(QuizAnswer.user_id == user_id)
        .scalar()
        or 0
    )

    answer_dates = db.query(func.count(func.distinct(func.date(QuizAnswer.answered_at)))) \
        .filter(QuizAnswer.user_id == user_id).scalar() or 0

    return ProgressOverviewOut(
        document_count=len(study_docs),
        question_count=len(rows),
        answered_count=counts["answered"],
        correct_count=counts["correct"],
        wrong_count=counts["wrong"],
        unknown_count=counts["unknown"],
        accuracy_rate=_accuracy(counts["correct"], counts["wrong"]),
        study_days=int(answer_dates),
        total_study_seconds=int(total_study_seconds),
    )


def get_progress_heatmap(db: Session, user_id: int, days: int) -> ProgressHeatmapOut:
    days = max(1, min(days, 365))
    start = (_utc_now() - timedelta(days=days - 1)).date()

    rows = (
        db.query(func.date(QuizAnswer.answered_at), func.count(QuizAnswer.id))
        .filter(
            QuizAnswer.user_id == user_id,
            QuizAnswer.answered_at >= datetime.combine(start, datetime.min.time()),
        )
        .group_by(func.date(QuizAnswer.answered_at))
        .all()
    )
    count_by_day = {str(d): int(c) for d, c in rows}

    items: List[HeatmapDayOut] = []
    for i in range(days):
        day = start + timedelta(days=i)
        key = day.isoformat()
        items.append(HeatmapDayOut(date=key, count=count_by_day.get(key, 0)))

    return ProgressHeatmapOut(days=days, items=items)


def get_progress_timeline(db: Session, user_id: int, limit: int) -> ProgressTimelineOut:
    limit = max(1, min(limit, 100))

    doc_rows = (
        db.query(Document.id, Document.display_name, Document.created_at)
        .filter(Document.user_id == user_id, Document.zone == "study")
        .all()
    )
    doc_name_map = {doc_id: name for doc_id, name, _ in doc_rows}

    events: List[TimelineItemOut] = []
    for doc_id, name, created_at in doc_rows:
        events.append(
            TimelineItemOut(
                event_type="upload",
                occurred_at=created_at.isoformat() if created_at else None,
                document_id=doc_id,
                document_name=name,
            )
        )

    gen_rows = question_crud.list_user_questions(db, user_id)
    for ref, _q in gen_rows:
        events.append(
            TimelineItemOut(
                event_type="generate",
                occurred_at=ref.added_at.isoformat() if ref.added_at else None,
                document_id=ref.document_id,
                document_name=doc_name_map.get(ref.document_id),
                question_id=ref.question_id,
            )
        )

    answer_rows = (
        db.query(QuizAnswer)
        .filter(QuizAnswer.user_id == user_id)
        .order_by(QuizAnswer.answered_at.desc())
        .limit(limit * 3)
        .all()
    )
    for ans in answer_rows:
        events.append(
            TimelineItemOut(
                event_type="answer",
                occurred_at=ans.answered_at.isoformat() if ans.answered_at else None,
                question_id=ans.question_id,
                status=ans.status,
            )
        )

    events = [e for e in events if e.occurred_at]
    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return ProgressTimelineOut(items=events[:limit])


def _provenance_page_map(
    db: Session, question_ids: List[str], document_id: str
) -> Dict[str, Optional[int]]:
    if not question_ids:
        return {}
    rows = (
        db.query(QuestionProvenance.question_id, QuestionProvenance.page_number)
        .filter(
            QuestionProvenance.question_id.in_(question_ids),
            QuestionProvenance.document_id == document_id,
        )
        .all()
    )
    return {qid: page for qid, page in rows}


def get_learning_path(
    db: Session, user_id: int, goal_id: Optional[int] = None
) -> LearningPathOut:
    # #34：goal_id 传入时仅校验归属，暂不做范围过滤。
    if goal_id is not None:
        goal = (
            db.query(Goal)
            .filter(Goal.id == goal_id, Goal.user_id == user_id)
            .first()
        )
        if not goal:
            raise HTTPException(status_code=404, detail="目标不存在或不属于当前用户")

    docs, _ = kb_crud.list_documents(db, user_id, page=1, limit=10000)
    study_docs = [d for d in docs if d.zone == "study"]

    document_paths: List[DocumentLearningPathOut] = []
    tag_stat_map: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"question": 0, "answered": 0, "correct": 0, "wrong": 0, "unknown": 0}
    )

    for doc in study_docs:
        rows = question_crud.list_user_questions(db, user_id, document_id=doc.id)
        question_ids = [q.id for _, q in rows]
        q_by_id: Dict[str, GlobalQuestion] = {q.id: q for _, q in rows}
        stats_map = quiz_crud.get_user_answer_stats_for_questions(db, user_id, question_ids)
        page_map = _provenance_page_map(db, question_ids, doc.id)

        toc = toc_crud.list_toc_for_document(db, doc.id)
        chapter_buckets = {
            t.order_index: [] for t in toc
        }
        uncategorized: List[str] = []
        for qid in question_ids:
            page = page_map.get(qid)
            if page is None:
                uncategorized.append(qid)
                continue
            matched = False
            for t in toc:
                if t.page_start <= page <= t.page_end:
                    chapter_buckets[t.order_index].append(qid)
                    matched = True
                    break
            if not matched:
                uncategorized.append(qid)

        chapters: List[ChapterProgressOut] = []
        for t in toc:
            c = _counts_from_stats(chapter_buckets[t.order_index], stats_map)
            chapters.append(
                ChapterProgressOut(
                    order_index=t.order_index,
                    title=t.title,
                    page_start=t.page_start,
                    page_end=t.page_end,
                    question_count=len(chapter_buckets[t.order_index]),
                    answered_count=c["answered"],
                    correct_count=c["correct"],
                    wrong_count=c["wrong"],
                    unknown_count=c["unknown"],
                    accuracy_rate=_accuracy(c["correct"], c["wrong"]),
                )
            )

        uc = _counts_from_stats(uncategorized, stats_map)
        document_paths.append(
            DocumentLearningPathOut(
                document_id=doc.id,
                document_name=doc.display_name,
                has_toc=len(toc) > 0,
                chapters=chapters,
                uncategorized_question_count=len(uncategorized),
                uncategorized_answered_count=uc["answered"],
                uncategorized_correct_count=uc["correct"],
                uncategorized_wrong_count=uc["wrong"],
                uncategorized_unknown_count=uc["unknown"],
            )
        )

        # tag 维度聚合
        for qid in question_ids:
            q = q_by_id[qid]
            tags = question_crud.parse_tags_json(q.tags) or ["未分类"]
            latest_status, attempt_count = stats_map.get(qid, (None, 0))
            for raw_tag in tags:
                tag = str(raw_tag).strip() or "未分类"
                bucket = tag_stat_map[tag]
                bucket["question"] += 1
                if attempt_count > 0:
                    bucket["answered"] += 1
                    if latest_status == "correct":
                        bucket["correct"] += 1
                    elif latest_status == "wrong":
                        bucket["wrong"] += 1
                    elif latest_status == "unknown":
                        bucket["unknown"] += 1

    tag_paths: List[TagProgressOut] = []
    for tag, b in tag_stat_map.items():
        tag_paths.append(
            TagProgressOut(
                tag=tag,
                question_count=b["question"],
                answered_count=b["answered"],
                correct_count=b["correct"],
                wrong_count=b["wrong"],
                unknown_count=b["unknown"],
                accuracy_rate=_accuracy(b["correct"], b["wrong"]),
            )
        )
    tag_paths.sort(key=lambda x: (-x.wrong_count, -(x.accuracy_rate or 0), x.tag))

    return LearningPathOut(documents=document_paths, tags=tag_paths)