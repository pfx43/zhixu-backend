"""针对训练 API"""
import json
from typing import Optional, Union

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.schemas.training import (
    TargetedTrainingActiveSessionOut,
    TargetedTrainingStartIn,
    TargetedTrainingStartOut,
    TrainingTutorMessageCreate,
    TrainingTutorReplyOut,
)
from app.services import training_service

router = APIRouter(tags=["针对训练"])


@router.post(
    "/targeted/start",
    response_model=TargetedTrainingStartOut,
    status_code=status.HTTP_201_CREATED,
)
def start_targeted_training(
    payload: TargetedTrainingStartIn = TargetedTrainingStartIn(),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Agent 制定训练计划：选题 + rationale，并创建刷题会话。支持 report_id 与恢复未完成会话。"""
    result = training_service.start_targeted_training(
        db,
        current_user["user_id"],
        report_id=payload.report_id,
        force_new=payload.force_new,
    )
    db.commit()
    return result


@router.get(
    "/targeted/reports/{report_id}/active-session",
    response_model=Optional[TargetedTrainingActiveSessionOut],
)
def get_active_training_session(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """查询某份报告下未完成的针对训练会话。"""
    return training_service.get_active_session_for_report(
        db, current_user["user_id"], report_id
    )


@router.get(
    "/targeted/sessions/{session_id}",
    response_model=TargetedTrainingStartOut,
)
def resume_targeted_training(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """恢复针对训练会话（含 Agent 上下文与薄弱 tag）。"""
    return training_service.resume_targeted_training(
        db, current_user["user_id"], session_id
    )


@router.post(
    "/targeted/tutor/{agent_session_id}",
    response_model=None,
)
def training_tutor_message(
    agent_session_id: str,
    payload: TrainingTutorMessageCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
) -> Union[TrainingTutorReplyOut, StreamingResponse]:
    """针对训练页 AI 辅导 — 复用制定计划时的 Agent 上下文。"""
    user_id = current_user["user_id"]

    if payload.stream:

        def sse_stream():
            try:
                for chunk in training_service.stream_training_tutor(
                    db, user_id, agent_session_id, payload.content
                ):
                    data = json.dumps(
                        {
                            "agent_session_id": agent_session_id,
                            "role": chunk.get("role", "assistant"),
                            "content": chunk.get("content", ""),
                            **(
                                {"reasoning_content": chunk["reasoning_content"]}
                                if chunk.get("reasoning_content")
                                else {}
                            ),
                            **({"tool_name": chunk["tool_name"]} if chunk.get("tool_name") else {}),
                        },
                        ensure_ascii=False,
                    )
                    yield f"event: message\ndata: {data}\n\n"
            finally:
                db.commit()

        return StreamingResponse(
            sse_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    full_content = ""
    for chunk in training_service.stream_training_tutor(
        db, user_id, agent_session_id, payload.content
    ):
        if chunk.get("content"):
            full_content += chunk["content"]
    db.commit()
    return TrainingTutorReplyOut(
        content=full_content or "（无回复）",
        agent_session_id=agent_session_id,
    )
