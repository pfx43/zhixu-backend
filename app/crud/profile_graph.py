"""画像图谱 + 推断任务 CRUD（Issue #5.X）。"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import ProfileGraph, ProfileInference


def get_or_create_graph(db: Session, user_id: int) -> ProfileGraph:
    g = (
        db.query(ProfileGraph)
        .filter(ProfileGraph.user_id == user_id)
        .first()
    )
    if g:
        return g
    g = ProfileGraph(user_id=user_id, version=1, graph_json={})
    db.add(g)
    db.flush()
    return g


def update_graph_json(db: Session, graph: ProfileGraph, graph_json: dict) -> None:
    graph.version = (graph.version or 0) + 1
    graph.graph_json = graph_json
    db.flush()


def start_inference(
    db: Session,
    *,
    user_id: int,
    graph_id: Optional[str] = None,
    trigger: str = "manual",
) -> ProfileInference:
    row = ProfileInference(
        id=str(uuid.uuid4()),
        user_id=user_id,
        graph_id=graph_id,
        status="running",
        trigger=trigger,
        started_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def finish_inference(
    db: Session,
    inference_id: str,
    *,
    user_id: int,
    status: str = "done",
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> Optional[ProfileInference]:
    row = (
        db.query(ProfileInference)
        .filter(
            ProfileInference.id == inference_id,
            ProfileInference.user_id == user_id,
        )
        .first()
    )
    if not row:
        return None
    row.status = status
    row.result_json = result
    row.error = error
    row.finished_at = datetime.now(timezone.utc)
    db.flush()
    return row


def get_inference(
    db: Session, user_id: int, inference_id: str
) -> Optional[ProfileInference]:
    return (
        db.query(ProfileInference)
        .filter(
            ProfileInference.id == inference_id,
            ProfileInference.user_id == user_id,
        )
        .first()
    )