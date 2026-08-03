"""
刷题会话服务 — 创建会话、答题判分、错题溯源
"""
import random
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud import kb as kb_crud
from app.crud import question as question_crud
from app.crud import quiz as quiz_crud
from app.models import DocumentSegment, GlobalQuestion, UserQuestionRef
from app.schemas.question import QuestionOption
from app.schemas.quiz import (
    AnswerResult,
    CitationOut,
    QuizResultsOut,
    QuizReviewItemOut,
    QuizSessionCreate,
    QuizSessionOut,
    QuizSessionQuestionOut,
)


def _build_citation(
    db: Session, question_id: str, document_id: Optional[str] = None
) -> Optional[CitationOut]:
    provs = question_crud.list_provenance_for_question(db, question_id)
    if not provs:
        return None

    prov = provs[0]
    if document_id:
        for p in provs:
            if p.document_id == document_id:
                prov = p
                break

    segment = None
    if prov.segment_id:
        segment = (
            db.query(DocumentSegment)
            .filter(DocumentSegment.id == prov.segment_id)
            .first()
        )

    snippet = prov.excerpt
    if not snippet and segment:
        snippet = segment.content[:500]

    return CitationOut(
        doc_id=prov.document_id,
        segment_id=prov.segment_id,
        title=segment.title if segment else None,
        char_start=segment.char_start if segment else None,
        char_end=segment.char_end if segment else None,
        snippet=snippet,
    )


def _grade_short_answer(question: GlobalQuestion, user_answer: Optional[str]) -> str:
    if not user_answer or not user_answer.strip():
        return "wrong"
    user = user_answer.strip().lower()
    correct = question.answer.strip().lower()
    if user == correct:
        return "correct"
    if correct in user or user in correct:
        return "correct"
    key_parts = [p.strip() for p in correct.replace("；", ";").split(";") if p.strip()]
    if key_parts:
        hit = sum(1 for p in key_parts if p in user)
        if hit >= max(1, len(key_parts) // 2):
            return "correct"
    try:
        from app.services.quiz.question_gen_service import _get_llm
        from app.services.llm.llm_runner import llm_predict_no_stream

        llm = _get_llm()
        if llm:
            prompt = (
                f"题干：{question.stem}\n标准答案：{question.answer}\n学生答案：{user_answer}\n"
                "仅回答 correct 或 wrong。"
            )
            resp = llm_predict_no_stream(
                llm, input_text=prompt, sys_prompt="你是判题助手，只输出 correct 或 wrong。", temperature=0
            )
            content = (resp.get("content", "") if isinstance(resp, dict) else str(resp)).strip().lower()
            if "correct" in content and "wrong" not in content:
                return "correct"
    except Exception:
        pass
    return "wrong"


def _grade_answer(
    question: GlobalQuestion, user_answer: Optional[str], status_hint: Optional[str]
) -> str:
    if status_hint == "unknown":
        return "unknown"
    qtype = (question.question_type or "single_choice").lower()
    if qtype in ("short_answer", "application"):
        return _grade_short_answer(question, user_answer)
    if not user_answer or not user_answer.strip():
        return "wrong"

    correct = question.answer.strip().upper()
    user = user_answer.strip().upper()
    return "correct" if user == correct else "wrong"


def _resolve_question_ids(
    db: Session,
    user_id: int,
    *,
    document_id: Optional[str],
    collection_id: Optional[str],
    question_ids: Optional[List[str]],
) -> Tuple[List[str], Optional[str], Optional[str]]:
    resolved_doc_id = document_id
    resolved_coll_id = collection_id

    if question_ids:
        owned = (
            db.query(UserQuestionRef.question_id)
            .filter(
                UserQuestionRef.user_id == user_id,
                UserQuestionRef.question_id.in_(question_ids),
            )
            .all()
        )
        owned_ids = {row[0] for row in owned}
        missing = [qid for qid in question_ids if qid not in owned_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"题目不存在: {missing[0]}")
        return list(question_ids), resolved_doc_id, resolved_coll_id

    if document_id:
        doc = kb_crud.get_document_by_id_or_dify(db, user_id, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        resolved_doc_id = doc.id
        if doc.question_gen_status != "completed":
            raise HTTPException(
                status_code=409,
                detail="文档尚未出题完成，请先生成题目",
            )

    if collection_id:
        coll = kb_crud.get_collection(db, user_id, collection_id)
        if not coll:
            raise HTTPException(status_code=404, detail="知识库不存在")

    rows = question_crud.list_user_questions(
        db,
        user_id,
        document_id=resolved_doc_id,
        collection_id=collection_id,
    )
    ids = [q.id for _, q in rows]
    random.shuffle(ids)
    return ids, resolved_doc_id, resolved_coll_id


def _to_session_question_out(
    sq, question: GlobalQuestion
) -> QuizSessionQuestionOut:
    options_raw = question_crud.parse_options_json(question.options)
    options = (
        [QuestionOption(**o) for o in options_raw] if options_raw else None
    )
    return QuizSessionQuestionOut(
        question_id=question.id,
        order_index=sq.order_index,
        stem=question.stem,
        question_type=question.question_type,
        options=options,
    )


def _build_session_out(db: Session, session) -> QuizSessionOut:
    rows = quiz_crud.list_session_questions(db, session.id)
    answered_count = quiz_crud.count_answers(db, session.id)
    questions = [_to_session_question_out(sq, q) for sq, q in rows]
    return QuizSessionOut(
        id=session.id,
        title=session.title,
        status=session.status,
        document_id=session.document_id,
        collection_id=session.collection_id,
        total_questions=len(questions),
        answered_count=answered_count,
        started_at=session.started_at,
        finished_at=session.finished_at,
        questions=questions,
    )


def create_quiz_session(
    db: Session, user_id: int, payload: QuizSessionCreate
) -> QuizSessionOut:
    question_ids, doc_id, coll_id = _resolve_question_ids(
        db,
        user_id,
        document_id=payload.document_id,
        collection_id=payload.collection_id,
        question_ids=payload.question_ids,
    )

    if not question_ids:
        raise HTTPException(status_code=409, detail="没有可用题目，请先生成题目")

    title = payload.title
    if not title and doc_id:
        doc = kb_crud.get_document_by_id_or_dify(db, user_id, doc_id)
        if doc:
            title = f"刷题 · {doc.display_name}"

    session = quiz_crud.create_session(
        db,
        user_id=user_id,
        document_id=doc_id,
        collection_id=coll_id or payload.collection_id,
        title=title,
    )
    quiz_crud.add_session_questions(db, session.id, question_ids)
    db.flush()
    return _build_session_out(db, session)


def get_quiz_session(db: Session, user_id: int, session_id: str) -> QuizSessionOut:
    session = quiz_crud.get_session(db, session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="刷题会话不存在")
    return _build_session_out(db, session)


def submit_answer(
    db: Session,
    user_id: int,
    session_id: str,
    *,
    question_id: str,
    user_answer: Optional[str] = None,
    status_hint: Optional[str] = None,
    time_spent_seconds: Optional[int] = None,
) -> AnswerResult:
    session = quiz_crud.get_session(db, session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="刷题会话不存在")
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="会话已结束")

    sq = quiz_crud.get_session_question(db, session_id, question_id)
    if not sq:
        raise HTTPException(status_code=400, detail="题目不在当前会话中")

    question = question_crud.get_question_by_id(db, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    if status_hint and status_hint not in ("unknown",):
        raise HTTPException(status_code=400, detail="无效的 status 值")

    result_status = _grade_answer(question, user_answer, status_hint)
    quiz_crud.upsert_answer(
        db,
        session_id=session_id,
        question_id=question_id,
        user_id=user_id,
        user_answer=user_answer,
        status=result_status,
        time_spent_seconds=time_spent_seconds,
    )

    total = len(quiz_crud.list_session_questions(db, session_id))
    answered_count = quiz_crud.count_answers(db, session_id)
    if answered_count >= total:
        quiz_crud.complete_session(db, session)

    explanation = None
    citation = None
    correct_answer = None

    if result_status in ("wrong", "unknown"):
        explanation = question.explanation
        citation = _build_citation(db, question_id, session.document_id)
        correct_answer = question.answer
    elif result_status == "correct":
        correct_answer = question.answer

    return AnswerResult(
        question_id=question_id,
        status=result_status,
        correct_answer=correct_answer,
        explanation=explanation,
        citation=citation,
        answered_count=answered_count,
        total_questions=total,
        session_status=session.status,
    )


def get_session_results(
    db: Session, user_id: int, session_id: str
) -> QuizResultsOut:
    session = quiz_crud.get_session(db, session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="刷题会话不存在")

    rows = quiz_crud.list_session_questions(db, session_id)
    question_map = {q.id: q for _, q in rows}
    answers = quiz_crud.list_answers_for_session(db, session_id)

    correct_count = sum(1 for a in answers if a.status == "correct")
    wrong_count = sum(1 for a in answers if a.status == "wrong")
    unknown_count = sum(1 for a in answers if a.status == "unknown")

    items: List[QuizReviewItemOut] = []
    for ans in answers:
        if ans.status not in ("wrong", "unknown"):
            continue
        question = question_map.get(ans.question_id)
        if not question:
            continue
        citation = _build_citation(db, ans.question_id, session.document_id)
        items.append(
            QuizReviewItemOut(
                question_id=ans.question_id,
                stem=question.stem,
                user_answer=ans.user_answer,
                status=ans.status,
                correct_answer=question.answer,
                explanation=question.explanation,
                citation=citation,
            )
        )

    return QuizResultsOut(
        session_id=session.id,
        status=session.status,
        total_questions=len(rows),
        correct_count=correct_count,
        wrong_count=wrong_count,
        unknown_count=unknown_count,
        items=items,
    )
