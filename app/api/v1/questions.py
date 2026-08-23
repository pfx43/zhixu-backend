"""
题目 API — 生成、列表、详情（含 provenance）
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_active_user,
    get_current_token,
    get_db,
    get_streaming_user,
)
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
async def generate_questions(
    payload: QuestionGenerateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    token: str = Depends(get_current_token),
):
    """对文档或指定分段批量出题（学习区 + 分段已完成）。"""
    if question_gen_service.is_question_gen_async():
        result = await question_gen_service.schedule_generate_questions(
            db=db,
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            segment_ids=payload.segment_ids,
            token=token,
        )
    else:
        result = await question_gen_service.generate_questions(
            db=db,
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            segment_ids=payload.segment_ids,
            token=token,
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
async def generate_from_pages(
    payload: PageGenerateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    token: str = Depends(get_current_token),
):
    """模式 B：对选中页批量 AI 出题。"""
    if question_gen_service.is_question_gen_async():
        result = await question_gen_service.schedule_generate_from_pages(
            db=db,
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            page_numbers=payload.page_numbers,
            questions_per_page=payload.questions_per_page,
            token=token,
        )
    else:
        result = await question_gen_service.generate_from_pages(
            db=db,
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            page_numbers=payload.page_numbers,
            questions_per_page=payload.questions_per_page,
            token=token,
        )
    db.commit()
    return result


@router.post("/generate-stream")
async def generate_stream_from_pages(
    payload: PageGenerateRequest,
    current_user: dict = Depends(get_streaming_user),
    token: str = Depends(get_current_token),
):
    """模式 B（SSE）：对选中页逐页出题，推送每页进度。

    事件（`event: message`，data 内 `type` 区分）：
      page_start / page_complete / page_failed / done
    """

    async def _event_stream():
        async for event_name, data in question_gen_service.stream_generate_from_pages(
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            page_numbers=payload.page_numbers,
            questions_per_page=payload.questions_per_page,
            token=token,
        ):
            yield f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/extract-from-pages",
    response_model=PageQuestionResponse,
    status_code=status.HTTP_200_OK,
)
async def extract_from_pages(
    payload: PageExtractRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """模式 A：从选中页提取教材自带题目。"""
    if question_gen_service.is_question_gen_async():
        result = await question_gen_service.schedule_extract_from_pages(
            db=db,
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            page_numbers=payload.page_numbers,
        )
    else:
        result = await question_gen_service.extract_from_pages(
            db=db,
            user_id=current_user["user_id"],
            document_id=payload.document_id,
            page_numbers=payload.page_numbers,
        )
    db.commit()
    return result
