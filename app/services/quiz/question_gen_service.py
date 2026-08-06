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

from app.core.config import MAX_QUESTIONS_PER_DOCUMENT, QUESTION_GEN_ASYNC
from app.core.database import SessionLocal
from app.core.job_runner import run_in_background

from app.crud import kb as kb_crud
from app.crud import question as question_crud
from app.crud import quiz as quiz_crud
from app.crud import segment as segment_crud
from app.crud import tag as tag_crud
from app.models import Document, DocumentSegment, UserQuestionRef
from app.schemas.question import (
    PageQuestionResponse,
    QuestionDeleteResponse,
    QuestionDetailOut,
    QuestionGenerateResponse,
    QuestionListOut,
    QuestionOption,
    QuestionOut,
    ProvenanceOut,
)
from app.services.knowledge.page_service import get_pages_by_numbers
from app.services.llm.llm_config import create_base_api
from app.services.quiz.question_hash import compute_content_hash
from app.services.llm.llm_runner import llm_predict_no_stream

logger = logging.getLogger(__name__)

QUESTIONS_PER_SEGMENT = 1
EXCERPT_MAX_LEN = 500

SYSTEM_PROMPT = """你是知拾学习助手，根据给定文档段落生成练习题。
严格输出 JSON 数组，每项格式：
{"stem":"题干","question_type":"single_choice","options":[{"key":"A","text":"..."},{"key":"B","text":"..."},{"key":"C","text":"..."},{"key":"D","text":"..."}],"answer":"A","explanation":"解析","tags":["标签"],"reference_text":"原文参考片段"}
question_type 可选：single_choice（单选）、short_answer（简答）、application（应用题）。
单选题 answer 必须是 A/B/C/D；简答/应用题 options 可为 []，answer 为标准答案要点。
reference_text 为题目所依据的原文关键片段（100-300字）。
tags 必须从用户已有 tag 列表中选择或复用相同含义的名称，避免同义不同名。
不要输出 markdown 代码块。"""

EXTRACT_SYSTEM_PROMPT = """你是知拾学习助手。给定教材页面内容，识别并提取其中自带的练习题。
严格输出 JSON 数组，每项格式：
{"stem":"题干","question_type":"single_choice","options":[{"key":"A","text":"..."},{"key":"B","text":"..."},{"key":"C","text":"..."},{"key":"D","text":"..."}],"answer":"A","explanation":"解析","tags":["标签"],"reference_text":"原文参考片段"}
若页面无现成题目，返回空数组 []。tags 优先复用已有 tag 名。不要输出 markdown 代码块。"""

QuestionProvider = Callable[[DocumentSegment], List[dict]]
PageProvider = Callable[[dict], List[dict]]

_llm_instance = None


def _get_llm():
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance
    try:
        _llm_instance = create_base_api()
        return _llm_instance
    except Exception:
        logger.warning("Tina LLM 不可用，将使用模板出题", exc_info=True)
        return None


def _extract_json_array(text: str) -> Optional[list]:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return None
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return None


def _normalize_question(raw: dict) -> Optional[dict]:
    stem = (raw.get("stem") or raw.get("question") or "").strip()
    answer = (raw.get("answer") or "").strip()
    qtype = (raw.get("question_type") or "single_choice").strip().lower()
    options = raw.get("options") or []
    if not stem or not answer:
        return None

    norm_options = []
    for opt in options:
        if isinstance(opt, dict):
            key = str(opt.get("key", "")).strip().upper()
            text = str(opt.get("text", "")).strip()
        else:
            continue
        if key and text:
            norm_options.append({"key": key, "text": text})

    if qtype == "single_choice":
        answer = answer.upper()
        if len(norm_options) < 2 or answer not in {o["key"] for o in norm_options}:
            return None
    elif qtype in ("short_answer", "application"):
        if not norm_options:
            norm_options = []
    else:
        qtype = "single_choice"
        answer = answer.upper()
        if len(norm_options) < 2:
            return None

    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    ref_text = (raw.get("reference_text") or "").strip() or None
    return {
        "stem": stem,
        "options": norm_options,
        "answer": answer,
        "explanation": (raw.get("explanation") or "").strip() or None,
        "tags": tags,
        "question_type": qtype,
        "reference_text": ref_text,
    }


def _existing_tag_names(db: Session, user_id: int, document_id: Optional[str] = None) -> List[str]:
    rows = tag_crud.list_tags_for_user(db, user_id, document_id=document_id)
    return [r.name for r in rows]


def _format_tag_hint(tag_names: List[str]) -> str:
    if not tag_names:
        return "（暂无已有 tag，请创建简洁、可复用的知识点标签）"
    return "已有 tag（请优先复用）：" + "、".join(tag_names[:40])


def _template_questions_for_page(page: dict) -> List[dict]:
    title = page.get("title") or f"第 {page.get('page_number', '?')} 页"
    snippet = page["content"][:120].replace("\n", " ").strip()
    return [
        {
            "stem": f"关于「{title}」，以下哪项最符合原文内容？",
            "options": [
                {"key": "A", "text": snippet or "与原文核心内容一致"},
                {"key": "B", "text": "与原文无关的干扰项"},
                {"key": "C", "text": "片面或不完整的描述"},
                {"key": "D", "text": "明显错误的描述"},
            ],
            "answer": "A",
            "explanation": "请参考原文页面。",
            "tags": ["自动生成", title],
        }
    ]


def _llm_generate_for_page(page: dict, *, count: int = 1, tag_hint: str = "") -> List[dict]:
    from app.services.quiz.question_gen_agent import agent_generate_for_page

    result = agent_generate_for_page(page, count=count, tag_hint=tag_hint)
    if result:
        return result[:count]

    llm = _get_llm()
    if not llm:
        return _template_questions_for_page(page)

    title = page.get("title") or f"第 {page.get('page_number', '?')} 页"
    user_input = (
        f"页面：{title}\n\n页面内容：\n{page['content'][:3000]}\n\n"
        f"{tag_hint}\n\n"
        f"请生成 {count} 道练习题，覆盖本页核心知识点。"
    )
    try:
        resp = llm_predict_no_stream(
            llm,
            input_text=user_input,
            sys_prompt=SYSTEM_PROMPT,
            format="json",
            temperature=0.3,
        )
        content = resp.get("content", "") if isinstance(resp, dict) else str(resp)
        items = _extract_json_array(content) or []
        normalized = [_normalize_question(item) for item in items]
        result = [q for q in normalized if q][:count]
        if result:
            return result
    except Exception:
        logger.warning(
            "LLM 按页出题失败，回退模板: page=%s",
            page.get("page_number"),
            exc_info=True,
        )
    return _template_questions_for_page(page)


def _llm_extract_for_page(page: dict, *, tag_hint: str = "") -> List[dict]:
    from app.services.quiz.question_gen_agent import agent_extract_for_page

    result = agent_extract_for_page(page, tag_hint=tag_hint)
    if result:
        return result

    llm = _get_llm()
    if not llm:
        return []

    title = page.get("title") or f"第 {page.get('page_number', '?')} 页"
    user_input = (
        f"页面：{title}\n\n页面内容：\n{page['content'][:4000]}\n\n"
        f"{tag_hint}\n\n请提取本页自带题目。"
    )
    try:
        resp = llm_predict_no_stream(
            llm,
            input_text=user_input,
            sys_prompt=EXTRACT_SYSTEM_PROMPT,
            format="json",
            temperature=0.2,
        )
        content = resp.get("content", "") if isinstance(resp, dict) else str(resp)
        items = _extract_json_array(content) or []
        normalized = [_normalize_question(item) for item in items]
        return [q for q in normalized if q]
    except Exception:
        logger.warning(
            "LLM 按页提取失败: page=%s", page.get("page_number"), exc_info=True
        )
        return []


def batch_generate_questions(
    pages: List[dict],
    *,
    questions_per_page: int = 1,
    provider: Optional[PageProvider] = None,
) -> List[tuple[dict, dict]]:
    """
    批量按页出题 — 可供 Tina Agent 工具注册。
    返回 [(page_dict, question_dict), ...]
    """
    gen = provider or (lambda p: _llm_generate_for_page(p, count=questions_per_page))
    results: List[tuple[dict, dict]] = []
    for page in pages:
        for qdata in gen(page)[:questions_per_page]:
            normalized = _normalize_question(qdata) if isinstance(qdata, dict) else None
            if normalized:
                results.append((page, normalized))
    return results


def _template_questions(segment: DocumentSegment) -> List[dict]:
    title = segment.title or "本节内容"
    snippet = segment.content[:120].replace("\n", " ").strip()
    return [
        {
            "stem": f"关于「{title}」，以下哪项最符合原文内容？",
            "options": [
                {"key": "A", "text": snippet or "与原文核心内容一致"},
                {"key": "B", "text": "与原文无关的干扰项"},
                {"key": "C", "text": "片面或不完整的描述"},
                {"key": "D", "text": "明显错误的描述"},
            ],
            "answer": "A",
            "explanation": "请参考原文段落。",
            "tags": ["自动生成"],
        }
    ]


def _llm_generate(segment: DocumentSegment, *, tag_hint: str = "") -> List[dict]:
    from app.services.quiz.question_gen_agent import agent_generate_for_segment

    result = agent_generate_for_segment(segment, tag_hint=tag_hint)
    if result:
        return result[:QUESTIONS_PER_SEGMENT]

    llm = _get_llm()
    if not llm:
        return _template_questions(segment)

    title = segment.title or "（无标题）"
    user_input = (
        f"段落标题：{title}\n\n段落内容：\n{segment.content[:3000]}\n\n"
        f"{tag_hint}\n\n"
        f"请生成 {QUESTIONS_PER_SEGMENT} 道练习题。"
    )
    try:
        resp = llm_predict_no_stream(
            llm,
            input_text=user_input,
            sys_prompt=SYSTEM_PROMPT,
            format="json",
            temperature=0.3,
        )
        content = resp.get("content", "") if isinstance(resp, dict) else str(resp)
        items = _extract_json_array(content) or []
        normalized = [_normalize_question(item) for item in items]
        result = [q for q in normalized if q][:QUESTIONS_PER_SEGMENT]
        if result:
            return result
    except Exception:
        logger.warning(
            "LLM 出题失败，回退模板: segment_id=%s", segment.id, exc_info=True
        )
    return _template_questions(segment)


def _make_excerpt(segment: DocumentSegment) -> str:
    text = segment.content.strip()
    if len(text) <= EXCERPT_MAX_LEN:
        return text
    return text[:EXCERPT_MAX_LEN] + "…"


def _persist_question(
    db: Session,
    *,
    user_id: int,
    document: Document,
    segment: DocumentSegment,
    qdata: dict,
    source_type: str = "generated",
) -> Tuple[bool, bool]:
    """返回 (created, reused)。"""
    return _persist_question_core(
        db,
        user_id=user_id,
        document=document,
        qdata=qdata,
        source_type=source_type,
        segment_id=segment.id,
        excerpt=_make_excerpt(segment),
    )


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
) -> Tuple[bool, bool]:
    """返回 (created, reused)。"""
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

    if segment_id:
        if not question_crud.get_provenance_for_segment(db, question.id, segment_id):
            question_crud.create_provenance(
                db,
                question_id=question.id,
                document_id=document.id,
                segment_id=segment_id,
                excerpt=excerpt,
                global_document_id=document.global_document_id,
            )
    elif not question_crud.get_provenance_for_document_excerpt(
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


def _validate_document_for_generation(doc: Optional[Document]) -> Document:
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.zone != "study":
        raise HTTPException(status_code=400, detail="仅学习区文档可出题")
    if doc.segment_status != "completed":
        raise HTTPException(status_code=400, detail="文档分段未完成，无法出题")
    return doc


def _validate_document_for_page_ops(doc: Optional[Document]) -> Document:
    """按页出题/提取：仅需学习区 + 可读 parsed 文本，不依赖 segment。"""
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.zone != "study":
        raise HTTPException(status_code=400, detail="仅学习区文档可出题")
    return doc


def generate_questions(
    db: Session,
    user_id: int,
    document_id: Optional[str] = None,
    segment_ids: Optional[List[str]] = None,
    provider: Optional[QuestionProvider] = None,
) -> QuestionGenerateResponse:
    """
    对文档或指定分段批量出题。
    provider 可注入 mock（测试用）；默认走 LLM + 模板回退。
    """
    gen_provider = provider or _llm_generate
    created_count = 0
    reused_count = 0
    target_doc_id = document_id

    if segment_ids:
        segments: List[DocumentSegment] = []
        document: Optional[Document] = None
        for sid in segment_ids:
            seg = db.query(DocumentSegment).filter(DocumentSegment.id == sid).first()
            if not seg:
                raise HTTPException(status_code=404, detail=f"分段不存在: {sid}")
            doc = kb_crud.get_document_by_id_or_dify(db, user_id, seg.document_id)
            doc = _validate_document_for_generation(doc)
            if document is None:
                document = doc
            elif document.id != doc.id:
                raise HTTPException(
                    status_code=400, detail="segment_ids 必须属于同一文档"
                )
            segments.append(seg)
        target_doc_id = document.id if document else None
    else:
        document = kb_crud.get_document_by_id_or_dify(db, user_id, document_id)
        document = _validate_document_for_generation(document)
        segments = segment_crud.list_segments_for_document(db, document.id)
        target_doc_id = document.id

    if not segments:
        if document:
            document.question_gen_status = "failed"
            db.flush()
        return QuestionGenerateResponse(
            document_id=target_doc_id,
            question_gen_status="failed",
            questions_created=0,
            questions_reused=0,
            total_questions=0,
        )

    if provider is None:
        _require_question_generation_ready()
    tag_hint_global = _format_tag_hint(
        _existing_tag_names(db, user_id, document_id=target_doc_id)
    )
    document.question_gen_status = "processing"
    db.flush()

    total_questions = 0

    try:
        for segment in segments:
            if total_questions >= MAX_QUESTIONS_PER_DOCUMENT:
                break
            try:
                if provider:
                    raw_questions = gen_provider(segment)
                else:
                    raw_questions = _llm_generate(segment, tag_hint=tag_hint_global)
            except Exception:
                logger.warning(
                    "分段出题失败，跳过: segment_id=%s", segment.id, exc_info=True
                )
                continue

            for qdata in raw_questions[:QUESTIONS_PER_SEGMENT]:
                if total_questions >= MAX_QUESTIONS_PER_DOCUMENT:
                    break
                normalized = _normalize_question(qdata) if isinstance(qdata, dict) else None
                if not normalized:
                    continue
                created, reused = _persist_question(
                    db,
                    user_id=user_id,
                    document=document,
                    segment=segment,
                    qdata=normalized,
                )
                if created:
                    created_count += 1
                if reused:
                    reused_count += 1
                total_questions += 1

        if total_questions > 0:
            document.question_gen_status = "completed"
        else:
            document.question_gen_status = "failed"
        db.flush()

        return QuestionGenerateResponse(
            document_id=target_doc_id,
            question_gen_status=document.question_gen_status,
            questions_created=created_count,
            questions_reused=reused_count,
            total_questions=total_questions,
        )
    except Exception:
        logger.exception("generate_questions failed: document_id=%s", target_doc_id)
        document.question_gen_status = "failed"
        db.flush()
        raise


def _start_question_gen_thread(worker) -> None:
    run_in_background(worker, name="question-gen")


def get_question_agent_readiness(*, probe: bool = True) -> dict:
    from app.services.quiz.question_gen_agent import (
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


def schedule_generate_questions(
    db: Session,
    user_id: int,
    document_id: Optional[str] = None,
    segment_ids: Optional[List[str]] = None,
) -> QuestionGenerateResponse:
    """校验后立即返回 processing，后台线程执行出题。"""
    document: Optional[Document] = None
    target_doc_id: Optional[str] = None

    if segment_ids:
        for sid in segment_ids:
            seg = db.query(DocumentSegment).filter(DocumentSegment.id == sid).first()
            if not seg:
                raise HTTPException(status_code=404, detail=f"分段不存在: {sid}")
            doc = kb_crud.get_document_by_id_or_dify(db, user_id, seg.document_id)
            doc = _validate_document_for_generation(doc)
            if document is None:
                document = doc
            elif document.id != doc.id:
                raise HTTPException(
                    status_code=400, detail="segment_ids 必须属于同一文档"
                )
        target_doc_id = document.id if document else None
    else:
        document = kb_crud.get_document_by_id_or_dify(db, user_id, document_id)
        document = _validate_document_for_generation(document)
        target_doc_id = document.id

    _require_question_generation_ready()
    document.question_gen_status = "processing"
    db.flush()

    def worker() -> None:
        wdb = SessionLocal()
        try:
            generate_questions(
                wdb,
                user_id=user_id,
                document_id=document_id,
                segment_ids=segment_ids,
            )
            wdb.commit()
        except Exception:
            wdb.rollback()
            logger.exception(
                "async generate_questions failed: document_id=%s", target_doc_id
            )
            try:
                doc = kb_crud.get_document_by_id_internal(wdb, target_doc_id)
                if doc:
                    doc.question_gen_status = "failed"
                    wdb.commit()
            except Exception:
                wdb.rollback()
        finally:
            wdb.close()

    _start_question_gen_thread(worker)
    return QuestionGenerateResponse(
        document_id=target_doc_id,
        question_gen_status="processing",
        questions_created=0,
        questions_reused=0,
        total_questions=0,
    )


def schedule_generate_from_pages(
    db: Session,
    user_id: int,
    document_id: str,
    page_numbers: List[int],
    questions_per_page: int = 1,
    provider: Optional[PageProvider] = None,
) -> PageQuestionResponse:
    doc = kb_crud.get_document_by_id_or_dify(db, user_id, document_id)
    doc = _validate_document_for_page_ops(doc)
    get_pages_by_numbers(db, doc, page_numbers)

    if provider is None:
        _require_question_generation_ready()
    doc.question_gen_status = "processing"
    db.flush()

    def worker() -> None:
        wdb = SessionLocal()
        try:
            generate_from_pages(
                wdb,
                user_id=user_id,
                document_id=doc.id,
                page_numbers=page_numbers,
                questions_per_page=questions_per_page,
                provider=provider,
            )
            wdb.commit()
        except Exception:
            wdb.rollback()
            logger.exception(
                "async generate_from_pages failed: document_id=%s", doc.id
            )
            try:
                failed = kb_crud.get_document_by_id_internal(wdb, doc.id)
                if failed:
                    failed.question_gen_status = "failed"
                    wdb.commit()
            except Exception:
                wdb.rollback()
        finally:
            wdb.close()

    _start_question_gen_thread(worker)
    return PageQuestionResponse(
        document_id=doc.id,
        page_numbers=page_numbers,
        mode="generate",
        question_gen_status="processing",
        questions_created=0,
        questions_reused=0,
        total_questions=0,
    )


def schedule_extract_from_pages(
    db: Session,
    user_id: int,
    document_id: str,
    page_numbers: List[int],
    provider: Optional[PageProvider] = None,
) -> PageQuestionResponse:
    doc = kb_crud.get_document_by_id_or_dify(db, user_id, document_id)
    doc = _validate_document_for_page_ops(doc)
    get_pages_by_numbers(db, doc, page_numbers)

    if provider is None:
        _require_question_generation_ready()
    doc.question_gen_status = "processing"
    db.flush()

    def worker() -> None:
        wdb = SessionLocal()
        try:
            extract_from_pages(
                wdb,
                user_id=user_id,
                document_id=doc.id,
                page_numbers=page_numbers,
                provider=provider,
            )
            wdb.commit()
        except Exception:
            wdb.rollback()
            logger.exception(
                "async extract_from_pages failed: document_id=%s", doc.id
            )
            try:
                failed = kb_crud.get_document_by_id_internal(wdb, doc.id)
                if failed:
                    failed.question_gen_status = "failed"
                    wdb.commit()
            except Exception:
                wdb.rollback()
        finally:
            wdb.close()

    _start_question_gen_thread(worker)
    return PageQuestionResponse(
        document_id=doc.id,
        page_numbers=page_numbers,
        mode="extract",
        question_gen_status="processing",
        questions_created=0,
        questions_reused=0,
        total_questions=0,
    )


def is_question_gen_async() -> bool:
    return QUESTION_GEN_ASYNC


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


def generate_from_pages(
    db: Session,
    user_id: int,
    document_id: str,
    page_numbers: List[int],
    questions_per_page: int = 1,
    provider: Optional[PageProvider] = None,
) -> PageQuestionResponse:
    """模式 B：对选中页批量 AI 出题。"""
    doc = kb_crud.get_document_by_id_or_dify(db, user_id, document_id)
    doc = _validate_document_for_page_ops(doc)

    pages = get_pages_by_numbers(db, doc, page_numbers)
    if provider is None:
        _require_question_generation_ready()
    created_count = 0
    reused_count = 0
    total_questions = 0
    tag_hint = _format_tag_hint(_existing_tag_names(db, user_id, document_id=doc.id))

    doc.question_gen_status = "processing"
    db.flush()

    try:
        if provider:
            pairs = batch_generate_questions(
                pages,
                questions_per_page=questions_per_page,
                provider=provider,
            )
        else:
            page_provider = lambda p: _llm_generate_for_page(
                p, count=questions_per_page, tag_hint=tag_hint
            )
            pairs = batch_generate_questions(
                pages,
                questions_per_page=questions_per_page,
                provider=page_provider,
            )
        for page, qdata in pairs:
            if total_questions >= MAX_QUESTIONS_PER_DOCUMENT:
                break
            created, reused = _persist_question_from_page(
                db,
                user_id=user_id,
                document=doc,
                page=page,
                qdata=qdata,
                source_type="generated",
            )
            if created:
                created_count += 1
            if reused:
                reused_count += 1
            total_questions += 1

        doc.question_gen_status = "completed" if total_questions > 0 else "failed"
        db.flush()
        return PageQuestionResponse(
            document_id=doc.id,
            page_numbers=page_numbers,
            mode="generate",
            question_gen_status=doc.question_gen_status,
            questions_created=created_count,
            questions_reused=reused_count,
            total_questions=total_questions,
        )
    except Exception:
        doc.question_gen_status = "failed"
        db.flush()
        raise


def extract_from_pages(
    db: Session,
    user_id: int,
    document_id: str,
    page_numbers: List[int],
    provider: Optional[PageProvider] = None,
) -> PageQuestionResponse:
    """模式 A：从选中页提取教材自带题目。"""
    doc = kb_crud.get_document_by_id_or_dify(db, user_id, document_id)
    doc = _validate_document_for_page_ops(doc)

    pages = get_pages_by_numbers(db, doc, page_numbers)
    if provider is None:
        _require_question_generation_ready()
    extract_fn = provider or (lambda p: _llm_extract_for_page(
        p, tag_hint=_format_tag_hint(_existing_tag_names(db, user_id, document_id=doc.id))
    ))
    created_count = 0
    reused_count = 0
    total_questions = 0

    doc.question_gen_status = "processing"
    db.flush()

    try:
        for page in pages:
            if total_questions >= MAX_QUESTIONS_PER_DOCUMENT:
                break
            raw_questions = extract_fn(page)
            for qdata in raw_questions:
                if total_questions >= MAX_QUESTIONS_PER_DOCUMENT:
                    break
                normalized = _normalize_question(qdata) if isinstance(qdata, dict) else None
                if not normalized:
                    continue
                created, reused = _persist_question_from_page(
                    db,
                    user_id=user_id,
                    document=doc,
                    page=page,
                    qdata=normalized,
                    source_type="extracted",
                )
                if created:
                    created_count += 1
                if reused:
                    reused_count += 1
                total_questions += 1

        doc.question_gen_status = "completed" if total_questions > 0 else "failed"
        db.flush()
        return PageQuestionResponse(
            document_id=doc.id,
            page_numbers=page_numbers,
            mode="extract",
            question_gen_status=doc.question_gen_status,
            questions_created=created_count,
            questions_reused=reused_count,
            total_questions=total_questions,
        )
    except Exception:
        doc.question_gen_status = "failed"
        db.flush()
        raise


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
