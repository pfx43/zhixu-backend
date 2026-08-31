"""
辅导 Agent API — 创建会话、苏格拉底式对话、历史查询
"""
from typing import Union

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_current_token, get_db
from app.schemas.tutor import (
    TutorMessageCreate,
    TutorReplyOut,
    TutorSessionCreate,
    TutorSessionOut,
)
from app.services.tutor import tutor_service

router = APIRouter(tags=["辅导"])


@router.post(
    "/sessions",
    response_model=TutorSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: TutorSessionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """从题目创建辅导会话，绑定 question_provenance 分段上下文。"""
    result = tutor_service.create_tutor_session(
        db=db, user_id=current_user["user_id"], payload=payload
    )
    db.commit()
    return result


@router.get("/sessions/{session_id}", response_model=TutorSessionOut)
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """获取辅导会话元数据、分段摘要与对话历史。"""
    return tutor_service.get_tutor_session(
        db=db, user_id=current_user["user_id"], session_id=session_id
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=None,
)
async def send_message(
    session_id: str,
    payload: TutorMessageCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    token: str = Depends(get_current_token),
) -> Union[TutorReplyOut, StreamingResponse]:
    """用户发送消息，返回 Agent 辅导回复（支持 SSE 流式）。"""
    user_id = current_user["user_id"]

    if payload.stream:

        async def stream_with_commit():
            try:
                async for event in tutor_service.stream_tutor_message(
                    db=db,
                    user_id=user_id,
                    session_id=session_id,
                    content=payload.content,
                    token=token,
                ):
                    yield event
            finally:
                db.commit()

        return StreamingResponse(
            stream_with_commit(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    result = await tutor_service.send_tutor_message(
        db=db,
        user_id=user_id,
        session_id=session_id,
        content=payload.content,
        token=token,
    )
    db.commit()
    return result
