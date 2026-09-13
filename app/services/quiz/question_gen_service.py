"""
文档分段 → 题目生成服务
写入 global_questions / question_provenance / user_question_refs
"""
import json
import logging
import re
from typing import Callable, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import (
    MAX_QUESTIONS_PER_DOCUMENT,
    QUESTION_GEN_WORKER,
)

from app.crud import kb as kb_crud
from app.crud import question as question_crud
from app.qgen.tcn_tags import build_tag_hint, tags_allowed_for_domain
from app.crud import quiz as quiz_crud
from app.crud import tag as tag_crud
from app.models import Document, UserQuestionRef
from app.schemas.question import (
    QuestionDeleteResponse,
    QuestionDetailOut,
    QuestionListOut,
    QuestionOption,
    QuestionOut,
    ProvenanceOut,
)
from app.services.quiz.question_hash import compute_content_hash
from app.services.quiz.question_normalize import normalize_question as _normalize_question

logger = logging.getLogger(__name__)

EXCERPT_MAX_LEN = 500

PageProvider = Callable[[dict], List[dict]]


def _existing_tag_names(db: Session, user_id: int, document_id: Optional[str] = None) -> List[str]:
    rows = tag_crud.list_tags_for_user(db, user_id, document_id=document_id)
    return [r.name for r in rows]


def _format_tag_hint(tag_names: List[str], tcn_domain: Optional[str] = None) -> str:
    existing = (
        "（暂无已有 tag，请创建简洁、可复用的知识点标签）"
        if not tag_names
        else "已有 tag（请优先复用）：" + "、".join(tag_names[:40])
    )
    return build_tag_hint(existing, tcn_domain)


def _persist_question_from_page(
    db: Session,
    *,
    user_id: int,
    document: Document,
    page: dict,
    qdata: dict,
    source_type: str = "generated",
) -> Tuple[bool, bool]:
    title = page.get("title") or f"第 {page.get('page_number', '?')} 页"
    excerpt = page["content"].strip()
    if len(excerpt) > EXCERPT_MAX_LEN:
        excerpt = excerpt[:EXCERPT_MAX_LEN] + "…"
    excerpt = f"[{title}] {excerpt}"
    return _persist_question_core(
        db,
        user_id=user_id,
        document=document,
        qdata=qdata,
        source_type=source_type,
        segment_id=page.get("segment_id"),
        excerpt=excerpt,
        page_number=page.get("page_number"),
    )


def _persist_question_core(
    db: Session,
    *,
    user_id: int,
    document: Document,
    qdata: dict,
    source_type: str,
    segment_id: Optional[str],
    excerpt: str,
    page_number: Optional[int] = None,
) -> Tuple[bool, bool]:
    """返回 (created, reused)。非法 TCN tag 时 (False, False) 且不入库。"""
    domain = getattr(document, "tcn_domain", None)
    if not tags_allowed_for_domain(qdata.get("tags") or [], domain):
        logger.warning(
            "拒绝入库非法 TCN tag: document=%s domain=%s tags=%s",
            document.id,
            domain,
            qdata.get("tags"),
        )
        return False, False

    tag_crud.ensure_tags(
        db,
        user_id=user_id,
        tag_names=qdata.get("tags") or [],
        document_id=document.id,
    )

    ref_text = qdata.get("reference_text")
    if ref_text:
        excerpt = ref_text[:EXCERPT_MAX_LEN] + ("…" if len(ref_text) > EXCERPT_MAX_LEN else "")

    options_json = json.dumps(qdata["options"], ensure_ascii=False) if qdata.get("options") else None
    tags_json = json.dumps(qdata.get("tags") or [], ensure_ascii=False)
    qtype = qdata.get("question_type") or "single_choice"
    content_hash = compute_content_hash(qdata["stem"], qdata.get("options") or [], qdata["answer"])

    existing = question_crud.get_question_by_content_hash(db, content_hash)
    created = False
    if existing:
        question = existing
        reused = True
    else:
        question = question_crud.create_global_question(
            db,
            content_hash=content_hash,
            stem=qdata["stem"],
            question_type=qtype,
            options_json=options_json,
            answer=qdata["answer"],
            explanation=qdata.get("explanation"),
            tags_json=tags_json,
            source_type=source_type,
        )
        created = True
        reused = False

    # 建立 / 补全 provenance（含 page_number）。
    # 按页出题落库必须写页码；旧数据 provenance 无页码时尽量补上。
    _ensure_provenance(
        db,
        question=question,
        document=document,
        segment_id=segment_id,
        excerpt=excerpt,
        page_number=page_number,
    )

    if not question_crud.get_user_ref(db, user_id, question.id, document.id):
        question_crud.create_user_ref(
            db,
            user_id=user_id,
            question_id=question.id,
            document_id=document.id,
            segment_id=segment_id,
            collection_id=document.collection_id,
        )

    return created, reused


def _ensure_provenance(
    db: Session,
    *,
    question,
    document: Document,
    segment_id: Optional[str],
    excerpt: str,
    page_number: Optional[int],
) -> None:
    """创建题目来源记录；同一条已存在且缺页码时补写页码。"""
    if segment_id:
        existing = question_crud.get_provenance_for_segment(
            db, question.id, segment_id
        )
        if existing is None:
            question_crud.create_provenance(
                db,
                question_id=question.id,
                document_id=document.id,
                segment_id=segment_id,
                excerpt=excerpt,
                global_document_id=document.global_document_id,
                page_number=page_number,
            )
        elif existing.page_number is None and page_number is not None:
            existing.page_number = page_number
        return

    if page_number is not None:
        existing = question_crud.get_provenance_for_document_excerpt(
            db, question.id, document.id, excerpt
        )
        if existing is None:
            question_crud.create_provenance(
                db,
                question_id=question.id,
                document_id=document.id,
                segment_id=None,
                excerpt=excerpt,
                global_document_id=document.global_document_id,
                page_number=page_number,
            )
        elif existing.page_number is None:
            existing.page_number = page_number
        return

    if not question_crud.get_provenance_for_document_excerpt(
        db, question.id, document.id, excerpt
    ):
        question_crud.create_provenance(
            db,
            question_id=question.id,
            document_id=document.id,
            segment_id=None,
            excerpt=excerpt,
            global_document_id=document.global_document_id,
        )


def _validate_document_for_page_ops(doc: Optional[Document]) -> Document:
    """按页出题/提取：仅需学习区 + 可读 parsed 文本，不依赖 segment。"""
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.zone != "study":
        raise HTTPException(status_code=400, detail="仅学习区文档可出题")
    return doc


def get_question_agent_readiness(*, probe: bool = True) -> dict:
    from app.services.agents.question_gen_agent import (
        get_question_agent_readiness as read_question_agent_readiness,
    )

    return read_question_agent_readiness(probe=probe)


def _require_question_generation_ready() -> None:
    try:
        readiness = get_question_agent_readiness(probe=True)
    except Exception:
        logger.exception("Question Agent readiness 探测失败")
        readiness = {"ready": False}
    if readiness.get("ready"):
        return
    raise HTTPException(
        status_code=503,
        detail={
            "code": "question_generation_unavailable",
            "message": "题目生成服务暂时不可用，请稍后重试。",
        },
    )


def is_question_gen_worker() -> bool:
    """True：按页出题入队给出题 FastAPI，主进程不再 create_task 跑 Agent。"""
    return QUESTION_GEN_WORKER


def _to_question_out(
    ref,
    question,
    *,
    user_answer_status: Optional[str] = None,
    attempt_count: int = 0,
) -> QuestionOut:
    options_raw = question_crud.parse_options_json(question.options)
    options = (
        [QuestionOption(**o) for o in options_raw] if options_raw else None
    )
    tags = question_crud.parse_tags_json(question.tags)
    return QuestionOut(
        id=question.id,
        stem=question.stem,
        question_type=question.question_type,
        options=options,
        answer=question.answer,
        explanation=question.explanation,
        tags=tags,
        source_type=question.source_type,
        document_id=ref.document_id,
        collection_id=ref.collection_id,
        created_at=question.created_at,
        user_answer_status=user_answer_status,
        attempt_count=attempt_count,
    )


def list_questions(
    db: Session,
    user_id: int,
    document_id: Optional[str] = None,
    collection_id: Optional[str] = None,
) -> QuestionListOut:
    if document_id:
        doc = kb_crud.get_document_by_id_or_dify(db, user_id, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        document_id = doc.id

    rows = question_crud.list_user_questions(
        db, user_id, document_id=document_id, collection_id=collection_id
    )
    question_ids = [q.id for _, q in rows]
    stats_map = quiz_crud.get_user_answer_stats_for_questions(
        db, user_id, question_ids
    )

    questions: List[QuestionOut] = []
    answered_count = 0
    correct_count = 0
    wrong_count = 0
    unknown_count = 0

    for ref, q in rows:
        latest_status, attempt_count = stats_map.get(q.id, (None, 0))
        questions.append(
            _to_question_out(
                ref,
                q,
                user_answer_status=latest_status,
                attempt_count=attempt_count,
            )
        )
        if attempt_count > 0:
            answered_count += 1
            if latest_status == "correct":
                correct_count += 1
            elif latest_status == "wrong":
                wrong_count += 1
            elif latest_status == "unknown":
                unknown_count += 1

    return QuestionListOut(
        questions=questions,
        total=len(questions),
        document_id=document_id,
        collection_id=collection_id,
        answered_count=answered_count,
        correct_count=correct_count,
        wrong_count=wrong_count,
        unknown_count=unknown_count,
    )


def delete_user_questions(
    db: Session,
    user_id: int,
    *,
    document_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    question_ids: Optional[List[str]] = None,
) -> QuestionDeleteResponse:
    if not document_id and not collection_id and not question_ids:
        raise HTTPException(
            status_code=400,
            detail="至少提供 document_id、collection_id 或 question_ids 之一",
        )

    if document_id:
        doc = kb_crud.get_document_by_id_or_dify(db, user_id, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        document_id = doc.id

    deleted_count = question_crud.delete_user_question_refs(
        db,
        user_id,
        document_id=document_id,
        collection_id=collection_id,
        question_ids=question_ids,
    )
    return QuestionDeleteResponse(
        deleted_count=deleted_count,
        document_id=document_id,
        collection_id=collection_id,
    )


def get_question_detail(
    db: Session, user_id: int, question_id: str
) -> QuestionDetailOut:
    ref_row = (
        db.query(UserQuestionRef)
        .filter(
            UserQuestionRef.user_id == user_id,
            UserQuestionRef.question_id == question_id,
        )
        .first()
    )
    if not ref_row:
        raise HTTPException(status_code=404, detail="题目不存在")

    question = question_crud.get_question_by_id(db, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    base = _to_question_out(ref_row, question)
    prov_rows = question_crud.list_provenance_for_question(db, question_id)
    provenance = [ProvenanceOut.model_validate(p) for p in prov_rows]

    return QuestionDetailOut(**base.model_dump(), provenance=provenance)
