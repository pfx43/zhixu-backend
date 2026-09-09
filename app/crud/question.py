import json
import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import GlobalQuestion, QuestionProvenance, UserQuestionRef
from app.services.quiz.question_generation_guard import (
    FallbackTemplateRejected,
    is_fixed_fallback_template,
    is_quarantined_question,
)

logger = logging.getLogger(__name__)


def get_question_by_content_hash(
    db: Session, content_hash: str
) -> Optional[GlobalQuestion]:
    return (
        db.query(GlobalQuestion)
        .filter(GlobalQuestion.content_hash == content_hash)
        .first()
    )


def get_question_by_id(db: Session, question_id: str) -> Optional[GlobalQuestion]:
    question = (
        db.query(GlobalQuestion).filter(GlobalQuestion.id == question_id).first()
    )
    if question and is_quarantined_question(question):
        return None
    return question


def create_global_question(
    db: Session,
    *,
    content_hash: str,
    stem: str,
    question_type: str,
    options_json: Optional[str],
    answer: str,
    explanation: Optional[str],
    tags_json: Optional[str],
    source_type: str = "generated",
) -> GlobalQuestion:
    if source_type == "generated" and is_fixed_fallback_template(
        stem=stem,
        options=options_json,
        answer=answer,
        question_type=question_type,
        explanation=explanation,
    ):
        logger.warning(
            "拒绝固定占位模板写入 global_questions: classification=invalid_output"
        )
        raise FallbackTemplateRejected(
            "generated question matched the fixed fallback template signature"
        )

    row = GlobalQuestion(
        content_hash=content_hash,
        stem=stem,
        question_type=question_type,
        options=options_json,
        answer=answer,
        explanation=explanation,
        tags=tags_json,
        source_type=source_type,
    )
    db.add(row)
    db.flush()
    return row


def get_provenance_for_segment(
    db: Session, question_id: str, segment_id: str
) -> Optional[QuestionProvenance]:
    return (
        db.query(QuestionProvenance)
        .filter(
            QuestionProvenance.question_id == question_id,
            QuestionProvenance.segment_id == segment_id,
        )
        .first()
    )


def get_provenance_for_document_excerpt(
    db: Session, question_id: str, document_id: str, excerpt: str
) -> Optional[QuestionProvenance]:
    return (
        db.query(QuestionProvenance)
        .filter(
            QuestionProvenance.question_id == question_id,
            QuestionProvenance.document_id == document_id,
            QuestionProvenance.excerpt == excerpt,
        )
        .first()
    )


def create_provenance(
    db: Session,
    *,
    question_id: str,
    document_id: str,
    segment_id: Optional[str],
    excerpt: Optional[str],
    global_document_id: Optional[str] = None,
    page_number: Optional[int] = None,
) -> QuestionProvenance:
    row = QuestionProvenance(
        question_id=question_id,
        document_id=document_id,
        segment_id=segment_id,
        excerpt=excerpt,
        global_document_id=global_document_id,
        page_number=page_number,
    )
    db.add(row)
    db.flush()
    return row


def count_questions_per_page(
    db: Session,
    user_id: int,
    document_id: str,
    page_numbers: List[int],
) -> dict[int, int]:
    """统计当前用户在某文档若干页上已有的题目数（用户隔离）。

    按页出题落库后，题目通过 user_question_refs 关联到用户，页码记在
    question_provenance.page_number；这里 join 两个表按页码聚合。
    返回 {page_number: question_count}，未命中页不出现。
    """
    if not page_numbers:
        return {}
    rows = (
        db.query(
            QuestionProvenance.page_number,
            func.count(func.distinct(UserQuestionRef.question_id)),
        )
        .join(
            UserQuestionRef,
            (UserQuestionRef.question_id == QuestionProvenance.question_id)
            & (UserQuestionRef.document_id == QuestionProvenance.document_id),
        )
        .filter(
            UserQuestionRef.user_id == user_id,
            QuestionProvenance.document_id == document_id,
            QuestionProvenance.page_number.in_(page_numbers),
        )
        .group_by(QuestionProvenance.page_number)
        .all()
    )
    return {page_num: count for page_num, count in rows}


def count_user_questions_for_documents(
    db: Session,
    user_id: int,
    document_ids: List[str],
) -> Dict[str, int]:
    """当前用户在若干文档上已入库的题目数（按 document_id 聚合，用户隔离）。"""
    if not document_ids:
        return {}
    rows = (
        db.query(
            UserQuestionRef.document_id,
            func.count(func.distinct(UserQuestionRef.question_id)),
        )
        .filter(
            UserQuestionRef.user_id == user_id,
            UserQuestionRef.document_id.in_(document_ids),
        )
        .group_by(UserQuestionRef.document_id)
        .all()
    )
    return {doc_id: int(cnt) for doc_id, cnt in rows}


def get_user_ref(
    db: Session, user_id: int, question_id: str, document_id: str
) -> Optional[UserQuestionRef]:
    return (
        db.query(UserQuestionRef)
        .filter(
            UserQuestionRef.user_id == user_id,
            UserQuestionRef.question_id == question_id,
            UserQuestionRef.document_id == document_id,
        )
        .first()
    )


def create_user_ref(
    db: Session,
    *,
    user_id: int,
    question_id: str,
    document_id: str,
    segment_id: Optional[str],
    collection_id: Optional[str],
) -> UserQuestionRef:
    question = (
        db.query(GlobalQuestion).filter(GlobalQuestion.id == question_id).first()
    )
    if question and is_quarantined_question(question):
        logger.warning(
            "拒绝固定占位模板进入用户题库: classification=invalid_output"
        )
        raise FallbackTemplateRejected(
            "fallback question cannot be referenced by a formal user library"
        )

    row = UserQuestionRef(
        user_id=user_id,
        question_id=question_id,
        document_id=document_id,
        segment_id=segment_id,
        collection_id=collection_id,
    )
    db.add(row)
    db.flush()
    return row


def delete_user_question_refs(
    db: Session,
    user_id: int,
    *,
    document_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    question_ids: Optional[List[str]] = None,
) -> int:
    query = db.query(UserQuestionRef).filter(UserQuestionRef.user_id == user_id)
    if document_id:
        query = query.filter(UserQuestionRef.document_id == document_id)
    if collection_id:
        query = query.filter(UserQuestionRef.collection_id == collection_id)
    if question_ids:
        query = query.filter(UserQuestionRef.question_id.in_(question_ids))
    return query.delete(synchronize_session=False)


def list_user_questions(
    db: Session,
    user_id: int,
    document_id: Optional[str] = None,
    collection_id: Optional[str] = None,
) -> List[Tuple[UserQuestionRef, GlobalQuestion]]:
    query = (
        db.query(UserQuestionRef, GlobalQuestion)
        .join(GlobalQuestion, UserQuestionRef.question_id == GlobalQuestion.id)
        .filter(UserQuestionRef.user_id == user_id)
    )
    if document_id:
        query = query.filter(UserQuestionRef.document_id == document_id)
    if collection_id:
        query = query.filter(UserQuestionRef.collection_id == collection_id)

    rows = query.order_by(UserQuestionRef.added_at.desc()).all()
    return [(ref, question) for ref, question in rows if not is_quarantined_question(question)]


def list_provenance_for_question(
    db: Session, question_id: str
) -> List[QuestionProvenance]:
    return (
        db.query(QuestionProvenance)
        .filter(QuestionProvenance.question_id == question_id)
        .all()
    )


def parse_options_json(raw: Optional[str]) -> Optional[list]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def parse_tags_json(raw: Optional[str]) -> Optional[list]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def search_questions_by_tags(
    db: Session,
    user_id: int,
    tags: List[str],
    *,
    limit: int = 30,
    question_types: Optional[List[str]] = None,
) -> List[Tuple[UserQuestionRef, GlobalQuestion]]:
    """在用户题库中按 tag 名检索题目（tags 字段 JSON 包含任一 tag 即命中）。"""
    if not tags:
        return []

    rows = list_user_questions(db, user_id)
    tag_set = {t.strip().lower() for t in tags if t and t.strip()}
    matched: List[Tuple[UserQuestionRef, GlobalQuestion]] = []

    for ref, question in rows:
        if question_types and question.question_type not in question_types:
            continue
        q_tags = parse_tags_json(question.tags) or []
        q_tag_lower = {str(t).strip().lower() for t in q_tags}
        if tag_set & q_tag_lower:
            matched.append((ref, question))
        if len(matched) >= limit:
            break

    return matched
