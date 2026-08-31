"""刷题交卷挂钩 TCN predict：对/错才传，「不会」不传；失败降级。"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.job_runner import schedule_coro
from app.core.tcn_config import TCN_ENABLED
from app.crud import kb as kb_crud
from app.crud import question as question_crud
from app.qgen.tcn_tags import first_legal_node

logger = logging.getLogger(__name__)


def resolve_quiz_predict(
    *,
    user_hash: Optional[str],
    domain: Optional[str],
    tags: Optional[list],
    result_status: str,
) -> Optional[dict]:
    if not TCN_ENABLED:
        return None
    if result_status not in ("correct", "wrong"):
        return None
    if not (user_hash or "").strip():
        return None
    if not domain:
        return None
    node_id = first_legal_node(domain, tags)
    if not node_id:
        return None
    return {
        "user_hash": user_hash,
        "current_node": node_id,
        "user_action": "correct" if result_status == "correct" else "incorrect",
        "domain_id": domain,
    }


def schedule_quiz_predict(
    db: Session,
    *,
    user_hash: Optional[str],
    document_id: Optional[str],
    question_id: str,
    result_status: str,
    session_id: str,
) -> None:
    if result_status not in ("correct", "wrong"):
        return
    domain = None
    if document_id:
        doc = kb_crud.get_document_by_id_internal(db, document_id)
        domain = getattr(doc, "tcn_domain", None) if doc else None
    question = question_crud.get_question_by_id(db, question_id)
    tags = question_crud.parse_tags_json(question.tags) if question else None
    payload = resolve_quiz_predict(
        user_hash=user_hash,
        domain=domain,
        tags=tags,
        result_status=result_status,
    )
    if not payload:
        return

    async def _run():
        try:
            from app.services.tcn.tcn_client import tcn_client

            await tcn_client.predict(
                user_hash=payload["user_hash"],
                current_node=payload["current_node"],
                user_action=payload["user_action"],
                domain_id=payload["domain_id"],
                session_id=session_id,
            )
        except Exception:
            logger.warning(
                "TCN predict 失败，交卷不受影响 question=%s",
                question_id,
                exc_info=True,
            )

    schedule_coro(_run(), name="tcn-quiz-predict")
