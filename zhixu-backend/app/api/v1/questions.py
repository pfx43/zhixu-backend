"""
题目 API — 生成、列表、详情（含 provenance）
"""
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.schemas.page import PageExtractRequest, PageGenerateRequest
from app.schemas.question import (
    PageQuestionResponse,
    QuestionBulkDeleteRequest,
    QuestionDeleteResponse,
    QuestionDetailOut,
    QuestionGenerateRequest,
    QuestionGenerateResponse,
    QuestionListOut,
)
from app.services.quiz import question_gen_service

router = APIRouter(tags=["题目"])


@router.post(
    "/generate",
    response_model=QuestionGenerateResponse,
    status_code=status.HTTP_200_OK,
)
def generate_questions(
    payload: QuestionGenerateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """对文档或指定分段批量出题（学习区 + 分段已完成）。"""
    if question_gen_service.is_question_gen_async():
        result = question_gen_service.schedule_generate_questions(
            db=db,
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            segment_ids=payload.segment_ids,
        )
    else:
        result = question_gen_service.generate_questions(
            db=db,
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            segment_ids=payload.segment_ids,
        )
    db.commit()
    return result


@router.get("", response_model=QuestionListOut)
def list_questions(
    document_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """列出当前用户可见题目，支持 document_id / collection_id 过滤。"""
    return question_gen_service.list_questions(
        db=db,
        user_id=current_user["user_id"],
        document_id=document_id,
        collection_id=collection_id,
    )


@router.delete("", response_model=QuestionDeleteResponse)
def delete_questions_by_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """删除当前用户对指定文档的题库引用（不删 global_questions / quiz_answers）。"""
    result = question_gen_service.delete_user_questions(
        db=db,
        user_id=current_user["user_id"],
        document_id=document_id,
    )
    db.commit()
    return result


@router.delete("/bulk", response_model=QuestionDeleteResponse)
def delete_questions_bulk(
    payload: QuestionBulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """批量删除用户题库引用，可按 document_id / collection_id / question_ids 过滤。"""
    result = question_gen_service.delete_user_questions(
        db=db,
        user_id=current_user["user_id"],
        document_id=payload.document_id,
        collection_id=payload.collection_id,
        question_ids=payload.question_ids,
    )
    db.commit()
    return result


@router.get("/{question_id}", response_model=QuestionDetailOut)
def get_question(
    question_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """单题详情，含 provenance / citation 溯源信息。"""
    return question_gen_service.get_question_detail(
        db=db,
        user_id=current_user["user_id"],
        question_id=question_id,
    )


@router.post(
    "/generate-from-pages",
    response_model=PageQuestionResponse,
    status_code=status.HTTP_200_OK,
)
def generate_from_pages(
    payload: PageGenerateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """模式 B：对选中页批量 AI 出题。"""
    if question_gen_service.is_question_gen_async():
        result = question_gen_service.schedule_generate_from_pages(
            db=db,
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            page_numbers=payload.page_numbers,
            questions_per_page=payload.questions_per_page,
        )
    else:
        result = question_gen_service.generate_from_pages(
            db=db,
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            page_numbers=payload.page_numbers,
            questions_per_page=payload.questions_per_page,
        )
    db.commit()
    return result


@router.post(
    "/extract-from-pages",
    response_model=PageQuestionResponse,
    status_code=status.HTTP_200_OK,
)
def extract_from_pages(
    payload: PageExtractRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """模式 A：从选中页提取教材自带题目。"""
    if question_gen_service.is_question_gen_async():
        result = question_gen_service.schedule_extract_from_pages(
            db=db,
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            page_numbers=payload.page_numbers,
        )
    else:
        result = question_gen_service.extract_from_pages(
            db=db,
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            page_numbers=payload.page_numbers,
        )
    db.commit()
    return result
