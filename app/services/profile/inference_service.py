"""画像推断（Issue #37）：执行器。

contract-5 只提供 ``POST /profile/inferences`` 写 ``running`` 行，没有执行器，
导致任务永久 ``running``、``graph_json`` 永远是空。本模块补齐执行器：

- ``build_profile_graph``：读用户资料/目标/资料/tip/刷题会话，输出可渲染图结构
- ``run_profile_inference``：构建图 → 写回 ``profile_graphs.graph_json`` →
  把 inference 标 ``done``（或 ``failed`` + error）
- ``requeue_stale_inferences``：进程重启后恢复遗留的 pending/running 任务
"""
from __future__ import annotations

import logging
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crud import profile_graph as profile_crud
from app.models import Document, Goal, ProfileInference, QuizSession, User, UserNote

logger = logging.getLogger(__name__)


def build_profile_graph(db: Session, user_id: int) -> Dict[str, list]:
    """确定性聚合用户学习行为，输出可渲染画像图。

    结构：``{nodes: [{id, label, node_type, confidence, evidence[]}],
    edges: [{source, target}]}``。空账号至少有一个 user 节点；
    ``{}`` 只允许表示「未生成」，不在这里出现。
    """
    user = db.query(User).filter(User.id == user_id).first()
    nodes: List[dict] = []
    edges: List[dict] = []

    user_node_id = "user:1"
    nodes.append(
        {
            "id": user_node_id,
            "label": (user.nickname or "学习者") if user else "学习者",
            "node_type": "user",
            "confidence": 1.0,
            "evidence": [],
        }
    )

    # ── 目标（进行中） ──
    goals = (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status == "active")
        .all()
    )
    for goal in goals:
        goal_id = f"goal:{goal.id}"
        nodes.append(
            {
                "id": goal_id,
                "label": goal.text,
                "node_type": "goal",
                "confidence": 1.0,
                "evidence": [],
            }
        )
        edges.append({"source": user_node_id, "target": goal_id})

    # ── 资料（按刷题会话数加权） ──
    session_counts: Dict[str, int] = dict(
        db.query(QuizSession.document_id, func.count(QuizSession.id))
        .filter(
            QuizSession.user_id == user_id,
            QuizSession.document_id.isnot(None),
        )
        .group_by(QuizSession.document_id)
        .all()
    )
    docs = db.query(Document).filter(Document.user_id == user_id).all()
    for doc in docs:
        count = session_counts.get(doc.id, 0)
        nodes.append(
            {
                "id": f"doc:{doc.id}",
                "label": doc.display_name,
                "node_type": "document",
                "confidence": min(1.0, 0.3 + count * 0.1),
                "evidence": [f"quiz_sessions:{count}"],
            }
        )
        if goals:
            edges.append(
                {"source": f"goal:{goals[0].id}", "target": f"doc:{doc.id}"}
            )

    # ── tip 标签（用户自分类，按当前用户隔离） ──
    tips = (
        db.query(UserNote)
        .filter(
            UserNote.user_id == user_id,
            UserNote.note_type == "tip",
            UserNote.deleted_at.is_(None),
        )
        .all()
    )
    tag_counter: Dict[str, int] = {}
    tag_evidence: Dict[str, List[str]] = {}
    tag_docs: Dict[str, str] = {}
    for tip in tips:
        for tag in tip.tags or []:
            tag_counter[tag] = tag_counter.get(tag, 0) + 1
            tag_evidence.setdefault(tag, []).append(tip.id)
            if tip.document_id:
                tag_docs.setdefault(tag, tip.document_id)
    for tag, count in tag_counter.items():
        nodes.append(
            {
                "id": f"tag:{tag}",
                "label": tag,
                "node_type": "tag",
                "confidence": min(1.0, count / 10.0),
                "evidence": tag_evidence[tag][:50],
            }
        )
        edges.append({"source": user_node_id, "target": f"tag:{tag}"})
        if tag in tag_docs:
            edges.append({"source": f"tag:{tag}", "target": f"doc:{tag_docs[tag]}"})

    return {"nodes": nodes, "edges": edges}


def run_profile_inference(db: Session, user_id: int, inference_id: str) -> None:
    """执行一次推断：构建图写回图谱，并把任务标 done / failed。

    使用调用方传入的 session（生产走独立 SessionLocal，测试走请求会话）。
    """
    row = profile_crud.get_inference(db, user_id, inference_id)
    if not row:
        logger.warning("画像推断任务不存在: user=%s inference=%s", user_id, inference_id)
        return
    try:
        graph = build_profile_graph(db, user_id)
        graph_row = profile_crud.get_or_create_graph(db, user_id)
        profile_crud.update_graph_json(db, graph_row, graph)
        result = {
            "node_count": len(graph.get("nodes", [])),
            "edge_count": len(graph.get("edges", [])),
        }
        profile_crud.finish_inference(
            db, inference_id, user_id=user_id, status="done", result=result
        )
    except Exception as exc:  # noqa: BLE001 — 推断失败要落到 failed 而不是让任务悬空
        logger.exception("画像推断失败: user=%s inference=%s", user_id, inference_id)
        profile_crud.finish_inference(
            db, inference_id, user_id=user_id, status="failed", error=str(exc)
        )


def requeue_stale_inferences(db: Session) -> int:
    """进程重启后把遗留的 pending/running 推断任务重新执行。"""
    stale = (
        db.query(ProfileInference)
        .filter(ProfileInference.status.in_(["pending", "running"]))
        .all()
    )
    for row in stale:
        run_profile_inference(db, row.user_id, row.id)
    db.commit()
    if stale:
        logger.info("画像推断恢复执行 %s 个遗留任务", len(stale))
    return len(stale)


def dispatch_inference_async(user_id: int, inference_id: str) -> None:
    """后台线程执行推断（独立 SessionLocal，不占用请求会话）。"""
    from app.core.job_runner import run_db_worker_safe, run_in_background

    def _worker() -> None:
        def _inner(db: Session) -> None:
            run_profile_inference(db, user_id, inference_id)

        run_db_worker_safe(_inner)

    run_in_background(_worker, name=f"profile-inference-{inference_id[:8]}")
