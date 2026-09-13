"""
题目 API — 生成、列表、详情（含 provenance）
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_active_user,
    get_db,
    get_streaming_user,
)
from app.core.database import short_session
from app.crud import kb as kb_crud
from app.schemas.page import PageGenerateRequest
from app.schemas.question import (
    QuestionBulkDeleteRequest,
    QuestionDeleteResponse,
    QuestionDetailOut,
    QuestionListOut,
)
from app.services.quiz import question_gen_service, qgen_job_service
from app.services.tasks import task_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["题目"])


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


@router.get("/jobs/{job_id}")
def get_qgen_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """查询按页出题 job 进度（出题服务不面向用户）。"""
    return qgen_job_service.get_job_for_user(db, current_user["user_id"], job_id)


def _enqueue_qgen_job_sync(
    user_id: int, payload: PageGenerateRequest
) -> tuple[str, str]:
    """入队独立出题服务（纯同步，供线程池调用）。返回 (job_id, document_name)。"""
    with short_session() as db:
        resp = qgen_job_service.enqueue_generate_from_pages(
            db=db,
            user_id=user_id,
            document_id=payload.document_id,
            page_numbers=payload.page_numbers,
            questions_per_page=payload.questions_per_page,
        )
        doc = kb_crud.get_document_by_id_internal(db, payload.document_id)
        document_name = doc.display_name if doc is not None else ""
        db.commit()
        return resp.job_id, document_name


@router.post("/generate-stream")
async def generate_stream_from_pages(
    payload: PageGenerateRequest,
    current_user: dict = Depends(get_streaming_user),
):
    """模式 B（SSE）：对选中页逐页出题，推送每页进度。

    事件（`event: message`，data 内 `type` 区分）：
      page_start / page_complete / page_failed / done

    按页 AI 出题一律入队给独立出题服务；主进程只轮询进度，不跑 Agent。
    """
    user_id = current_user["user_id"]

    async def _queued_event_stream():
        try:
            job_id, document_name = await asyncio.to_thread(
                _enqueue_qgen_job_sync, user_id, payload
            )
        except HTTPException as exc:
            data = {
                "type": "done",
                "document_id": payload.document_id,
                "document_name": "",
                "status": "failed",
                "page_numbers": payload.page_numbers,
                "total_pages": len(payload.page_numbers),
                "questions_created": 0,
                "questions_reused": 0,
                "total_questions": 0,
                "error": exc.detail,
            }
            yield f"event: message\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            return
        except Exception as e:
            logger.exception("出题入队失败: document_id=%s", payload.document_id)
            data = {
                "type": "done",
                "document_id": payload.document_id,
                "document_name": "",
                "status": "failed",
                "page_numbers": payload.page_numbers,
                "total_pages": len(payload.page_numbers),
                "questions_created": 0,
                "questions_reused": 0,
                "total_questions": 0,
                "error": str(e),
            }
            yield f"event: message\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            return

        async for event_name, data in qgen_job_service.stream_job_events(
            user_id=user_id,
            job_id=job_id,
            document_id=payload.document_id,
            document_name=document_name,
            page_numbers=payload.page_numbers,
        ):
            # 检查器：流结束后看 payload 页是否已有题，done 事件带 completed_tasks
            if event_name == "message" and data.get("type") == "done":
                try:
                    with short_session() as db:
                        data["completed_tasks"] = task_service.run_completion_checks(
                            db, user_id, "questions_generated"
                        )
                except Exception as e:
                    logger.warning(f"出题检查器执行失败: {e}")
            yield f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _queued_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
