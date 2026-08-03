"""学习分析 — 聚合知识库、题库与刷题记录"""
from collections import defaultdict
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.crud import kb as kb_crud
from app.crud import question as question_crud
from app.crud import quiz as quiz_crud
from app.schemas.analytics import (
    DocumentProgressOut,
    DocumentStatsOut,
    LearningStatsOut,
    QuestionStatsOut,
    RecentAnswerOut,
    RecentSessionOut,
    TagStatsListOut,
    TagStatsOut,
)
from app.services.quiz import question_gen_service


def _accuracy_rate(correct: int, wrong: int) -> Optional[int]:
    graded = correct + wrong
    if graded <= 0:
        return None
    return round(correct / graded * 100)


def get_learning_stats(db: Session, user_id: int) -> LearningStatsOut:
    docs, total_docs = kb_crud.list_documents(db, user_id, page=1, limit=500)
    doc_name_map: Dict[str, str] = {doc.id: doc.display_name for doc in docs}

    doc_stats = DocumentStatsOut(total=total_docs)
    for doc in docs:
        if doc.zone == "study":
            doc_stats.study_zone += 1
        status = (doc.indexing_status or "").lower()
        if status in ("completed", "indexed"):
            doc_stats.indexed += 1
        elif status in ("processing", "parsing", "splitting", "indexing"):
            doc_stats.processing += 1
        elif status in ("error", "failed"):
            doc_stats.failed += 1

    q_list = question_gen_service.list_questions(db, user_id)
    question_stats = QuestionStatsOut(
        total=q_list.total,
        answered=q_list.answered_count,
        correct=q_list.correct_count,
        wrong=q_list.wrong_count,
        unknown=q_list.unknown_count,
        accuracy_rate=_accuracy_rate(q_list.correct_count, q_list.wrong_count),
    )

    rows = question_crud.list_user_questions(db, user_id)
    question_ids = [q.id for _, q in rows]
    stats_map = quiz_crud.get_user_answer_stats_for_questions(db, user_id, question_ids)

    progress_map: Dict[str, Dict[str, int]] = {}
    doc_ids_with_questions: set[str] = set()
    for ref, q in rows:
        doc_id = ref.document_id
        if not doc_id:
            continue
        doc_ids_with_questions.add(doc_id)
        if doc_id not in progress_map:
            progress_map[doc_id] = {
                "question_total": 0,
                "answered_count": 0,
                "correct_count": 0,
                "wrong_count": 0,
                "unknown_count": 0,
            }
        entry = progress_map[doc_id]
        entry["question_total"] += 1
        latest_status, attempt_count = stats_map.get(q.id, (None, 0))
        if attempt_count > 0:
            entry["answered_count"] += 1
            if latest_status == "correct":
                entry["correct_count"] += 1
            elif latest_status == "wrong":
                entry["wrong_count"] += 1
            elif latest_status == "unknown":
                entry["unknown_count"] += 1

    doc_stats.with_questions = len(doc_ids_with_questions)

    document_progress: List[DocumentProgressOut] = []
    for doc_id, entry in progress_map.items():
        document_progress.append(
            DocumentProgressOut(
                document_id=doc_id,
                document_name=doc_name_map.get(doc_id, "未知文档"),
                question_total=entry["question_total"],
                answered_count=entry["answered_count"],
                correct_count=entry["correct_count"],
                wrong_count=entry["wrong_count"],
                unknown_count=entry["unknown_count"],
                accuracy_rate=_accuracy_rate(entry["correct_count"], entry["wrong_count"]),
            )
        )
    document_progress.sort(key=lambda x: (-x.answered_count, -x.question_total))

    recent_sessions: List[RecentSessionOut] = []
    for session in quiz_crud.list_recent_sessions(db, user_id, limit=5):
        total_q = quiz_crud.count_session_questions(db, session.id)
        answered = quiz_crud.count_answers(db, session.id)
        doc_name = None
        if session.document_id:
            doc_name = doc_name_map.get(session.document_id)
            if not doc_name:
                doc = kb_crud.get_document_by_id_internal(db, session.document_id)
                if doc:
                    doc_name = doc.display_name
        recent_sessions.append(
            RecentSessionOut(
                id=session.id,
                document_id=session.document_id,
                document_name=doc_name,
                status=session.status,
                total_questions=total_q,
                answered_count=answered,
                started_at=session.started_at,
                finished_at=session.finished_at,
            )
        )

    recent_answers: List[RecentAnswerOut] = []
    for answer, question, session in quiz_crud.list_recent_answers(db, user_id, limit=8):
        doc_id = session.document_id
        doc_name = doc_name_map.get(doc_id) if doc_id else None
        stem = question.stem
        if len(stem) > 80:
            stem = stem[:77] + "…"
        recent_answers.append(
            RecentAnswerOut(
                question_id=question.id,
                stem=stem,
                status=answer.status,
                document_id=doc_id,
                document_name=doc_name,
                answered_at=answer.answered_at,
            )
        )

    return LearningStatsOut(
        documents=doc_stats,
        questions=question_stats,
        document_progress=document_progress,
        recent_sessions=recent_sessions,
        recent_answers=recent_answers,
    )


def get_tag_stats(db: Session, user_id: int) -> TagStatsListOut:
    """按 tag 与 question_type 聚合 quiz_answers 统计。"""
    rows = question_crud.list_user_questions(db, user_id)
    question_ids = [q.id for _, q in rows]
    q_map = {q.id: q for _, q in rows}
    stats_map = quiz_crud.get_user_answer_stats_for_questions(db, user_id, question_ids)

    by_tag: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"correct": 0, "wrong": 0, "unknown": 0}
    )
    by_type: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"correct": 0, "wrong": 0, "unknown": 0}
    )

    for qid, q in q_map.items():
        latest_status, attempt_count = stats_map.get(qid, (None, 0))
        if attempt_count <= 0 or not latest_status:
            continue
        qtype = q.question_type or "unknown"
        type_bucket = by_type[qtype]
        if latest_status == "correct":
            type_bucket["correct"] += 1
        elif latest_status == "wrong":
            type_bucket["wrong"] += 1
        elif latest_status == "unknown":
            type_bucket["unknown"] += 1

        tags = question_crud.parse_tags_json(q.tags) or ["未分类"]
        for tag in tags:
            tag_name = str(tag).strip() or "未分类"
            bucket = by_tag[tag_name]
            if latest_status == "correct":
                bucket["correct"] += 1
            elif latest_status == "wrong":
                bucket["wrong"] += 1
            elif latest_status == "unknown":
                bucket["unknown"] += 1

    tag_out: List[TagStatsOut] = []
    for tag_name, counts in by_tag.items():
        graded = counts["correct"] + counts["wrong"]
        total = counts["correct"] + counts["wrong"] + counts["unknown"]
        tag_out.append(
            TagStatsOut(
                tag=tag_name,
                question_type="all",
                correct_count=counts["correct"],
                wrong_count=counts["wrong"],
                unknown_count=counts["unknown"],
                total_attempts=total,
                accuracy_rate=_accuracy_rate(counts["correct"], counts["wrong"]),
            )
        )
    tag_out.sort(key=lambda x: (-x.wrong_count, -(x.accuracy_rate or 0)))

    type_out: List[TagStatsOut] = []
    for qtype, counts in by_type.items():
        total = counts["correct"] + counts["wrong"] + counts["unknown"]
        type_out.append(
            TagStatsOut(
                tag=qtype,
                question_type=qtype,
                correct_count=counts["correct"],
                wrong_count=counts["wrong"],
                unknown_count=counts["unknown"],
                total_attempts=total,
                accuracy_rate=_accuracy_rate(counts["correct"], counts["wrong"]),
            )
        )

    return TagStatsListOut(by_tag=tag_out, by_question_type=type_out)

