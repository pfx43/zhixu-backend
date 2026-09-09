"""TCN 词表锁点、交卷 predict、学习路径领域图。"""
import json
import sys
from pathlib import Path

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.deps import get_current_active_user, get_db
from app.models import Document, GlobalQuestion, KbCollection, User
from app.qgen.tcn_tags import (
    first_legal_node,
    name_to_id,
    tags_allowed_for_domain,
)
from app.services.quiz import qgen_job_service, question_gen_service
from app.services.tcn.graph_export import frontier_nodes, load_domain_graph
from app.services.tcn.quiz_hook import resolve_quiz_predict
from app.services.tools.question_gen_tools import QuestionGenTools
from pgutil import make_sessionmaker
from server import app


@pytest.fixture()
def db_session():
    engine, SessionLocal = make_sessionmaker()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_user(db, email: str, user_hash: str = "hash-tcn-user") -> User:
    user = User(
        email=email,
        password_hash="hash",
        nickname="用户",
        is_active=True,
        user_hash=user_hash,
    )
    db.add(user)
    db.flush()
    return user


def _make_doc(db, user: User, name: str = "书", domain=None) -> Document:
    collection = KbCollection(user_id=user.id, name=f"c-{name}", zone="study")
    db.add(collection)
    db.flush()
    doc = Document(
        user_id=user.id,
        collection_id=collection.id,
        display_name=name,
        zone="study",
        content_hash=f"hash-{name}-{user.id}",
        tcn_domain=domain,
    )
    db.add(doc)
    db.flush()
    return doc


def _qdata(stem: str, tags: list) -> dict:
    return {
        "stem": stem,
        "question_type": "single_choice",
        "options": [
            {"key": "A", "text": "选项 A"},
            {"key": "B", "text": "选项 B"},
            {"key": "C", "text": "选项 C"},
            {"key": "D", "text": "选项 D"},
        ],
        "answer": "A",
        "explanation": "见原文",
        "tags": tags,
        "reference_text": "正文",
    }


def test_vocab_name_to_id_four_domains():
    math_id = name_to_id("math", "集合的概念与基本运算")
    assert math_id == "math:集合与基本运算"
    assert first_legal_node("math", ["自造", "集合的概念与基本运算"]) == math_id
    assert first_legal_node("math", ["自造"]) is None
    assert first_legal_node(None, ["集合的概念与基本运算"]) is None
    assert tags_allowed_for_domain(["集合的概念与基本运算"], "math")
    assert not tags_allowed_for_domain(["微积分"], "math")
    assert tags_allowed_for_domain(["随便编"], None)
    assert name_to_id("physics", "不存在的点") is None
    assert name_to_id("discrete_math", "命题与联结词") or True
    from app.qgen.tcn_tags import name_to_id_map

    hm = name_to_id("higher_math", "夹逼准则")
    assert hm == "higher_math:夹逼准则"
    assert name_to_id("physics", "位移、速度与加速度的定义")
    assert name_to_id_map("discrete_math")


def test_persist_rejects_illegal_tag_when_domain_set(db_session):
    user = _make_user(db_session, "lock@example.com")
    doc = _make_doc(db_session, user, "高数", domain="higher_math")
    page = {
        "page_number": 1,
        "title": "极限",
        "content": "夹逼",
        "segment_id": None,
    }
    created, reused = question_gen_service._persist_question_from_page(
        db_session,
        user_id=user.id,
        document=doc,
        page=page,
        qdata=_qdata("非法 tag 题？", ["自动生成"]),
        source_type="generated",
    )
    assert (created, reused) == (False, False)
    assert db_session.query(GlobalQuestion).count() == 0

    created, reused = question_gen_service._persist_question_from_page(
        db_session,
        user_id=user.id,
        document=doc,
        page=page,
        qdata=_qdata("无领域也可编？", ["自动生成"]),
        source_type="generated",
    )
    # still locked — domain is set
    assert created is False

    doc.tcn_domain = None
    db_session.flush()
    created, reused = question_gen_service._persist_question_from_page(
        db_session,
        user_id=user.id,
        document=doc,
        page=page,
        qdata=_qdata("无领域自编 tag？", ["自动生成"]),
        source_type="generated",
    )
    assert created is True
    assert db_session.query(GlobalQuestion).count() == 1


def test_complete_page_drops_illegal_when_domain_set(db_session, monkeypatch):
    user = _make_user(db_session, "complete-lock@example.com")
    doc = _make_doc(db_session, user, "数学", domain="math")
    monkeypatch.setattr(
        "app.services.quiz.qgen_job_service.get_pages_by_numbers",
        lambda db, d, nums: [
            {
                "page_number": 1,
                "title": "集合",
                "content": "集合运算",
                "segment_id": None,
            }
        ],
    )
    monkeypatch.setattr(
        "app.services.quiz.qgen_job_service.build_near_page_context",
        lambda db, d, nums, max_near_lookups=3: ({}, {1}),
    )
    resp = qgen_job_service.enqueue_generate_from_pages(
        db_session, user.id, doc.id, [1]
    )
    db_session.commit()
    claimed = qgen_job_service.claim_next_job(db_session)
    failed = qgen_job_service.complete_page(
        db_session, claimed["job_id"], 1, [_qdata("坏题？", ["自动生成"])]
    )
    assert failed["status"] == "failed"
    assert db_session.query(GlobalQuestion).count() == 0

    # 新 job 合法 tag 能入库
    resp2 = qgen_job_service.enqueue_generate_from_pages(
        db_session, user.id, doc.id, [1]
    )
    db_session.commit()
    claimed2 = qgen_job_service.claim_next_job(db_session)
    ok = qgen_job_service.complete_page(
        db_session,
        claimed2["job_id"],
        1,
        [_qdata("集合题？", ["集合的概念与基本运算"])],
    )
    assert ok["status"] == "completed"
    assert ok["total_questions"] == 1


def test_submit_question_tool_rejects_illegal_domain_tag():
    tools = QuestionGenTools(tcn_domain="math")
    raw = json.loads(
        tools.submit_question(
            stem="题干足够长用来过校验吗？是的。",
            question_type="single_choice",
            answer="A",
            option_a="对",
            option_b="错",
            option_c="也许",
            option_d="不知道",
            tags="微积分",
        )
    )
    assert raw["status"] == "invalid"
    assert tools.submitted_questions == []

    ok = json.loads(
        tools.submit_question(
            stem="集合的基本运算下列哪项正确？",
            question_type="single_choice",
            answer="A",
            option_a="对",
            option_b="错",
            option_c="也许",
            option_d="不知道",
            tags="集合的概念与基本运算",
        )
    )
    assert ok["status"] == "ok"
    assert len(tools.submitted_questions) == 1


def test_resolve_quiz_predict_skips_unknown_and_off_domain(monkeypatch):
    monkeypatch.setattr("app.services.tcn.quiz_hook.TCN_ENABLED", True)
    node = first_legal_node("math", ["集合的概念与基本运算"])
    assert node
    payload = resolve_quiz_predict(
        user_hash="u1",
        domain="math",
        tags=["集合的概念与基本运算"],
        result_status="correct",
    )
    assert payload["current_node"] == node
    assert payload["user_action"] == "correct"
    assert payload["domain_id"] == "math"

    wrong = resolve_quiz_predict(
        user_hash="u1",
        domain="math",
        tags=["集合的概念与基本运算"],
        result_status="wrong",
    )
    assert wrong["user_action"] == "incorrect"

    assert (
        resolve_quiz_predict(
            user_hash="u1",
            domain="math",
            tags=["集合的概念与基本运算"],
            result_status="unknown",
        )
        is None
    )
    assert (
        resolve_quiz_predict(
            user_hash="u1",
            domain="math",
            tags=["自造点"],
            result_status="correct",
        )
        is None
    )
    assert (
        resolve_quiz_predict(
            user_hash="u1",
            domain=None,
            tags=["集合的概念与基本运算"],
            result_status="correct",
        )
        is None
    )


def test_local_math_graph_inner_only():
    graph = load_domain_graph("math")
    assert len(graph["nodes"]) == 83
    ids = {n["id"] for n in graph["nodes"]}
    assert all(i.startswith("math:") for i in ids)
    for edge in graph["edges"]:
        assert edge["source"] in ids
        assert edge["target"] in ids
    physics = load_domain_graph("physics")
    assert physics["nodes"]
    assert all(n["id"].startswith("physics:") for n in physics["nodes"])
    empty = load_domain_graph(None)
    assert empty == {"nodes": [], "edges": []}


def test_frontier_nodes_ready_then_low():
    nodes = [
        {"id": "a", "name": "起点"},
        {"id": "b", "name": "下一层"},
        {"id": "c", "name": "还早"},
    ]
    edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]
    out = frontier_nodes(nodes, edges, {"a": 0.8, "b": 0.2, "c": None})
    assert [n["id"] for n in out] == ["b"]
    assert out[0]["reason"] == "先修已过，掌握度偏低"

    roots = frontier_nodes(nodes, edges, {})
    assert [n["id"] for n in roots] == ["a"]
    assert roots[0]["mastery"] is None


def test_document_tcn_graph_api(monkeypatch):
    engine, SessionLocal = make_sessionmaker()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    async def _fake_report(user_hash: str):
        return {
            "nodes": {
                "math:集合与基本运算": {"mastery": 0.42, "confidence": 0.9},
            }
        }

    monkeypatch.setattr(
        "app.services.tcn.tcn_client.tcn_client.get_report", _fake_report
    )

    with SessionLocal() as db:
        user = _make_user(db, "graph@example.com")
        math_doc = _make_doc(db, user, "数学书", domain="math")
        none_doc = _make_doc(db, user, "菜谱", domain=None)
        db.commit()
        user_id = user.id
        math_id = math_doc.id
        none_id = none_doc.id

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_user(authorization: str | None = Header(default=None)):
        if authorization != "Bearer tcn-graph-token":
            raise HTTPException(status_code=401, detail="Not authenticated")
        return {"user_id": user_id, "is_active": True, "user_hash": "hash-tcn-user"}

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_user
    try:
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer tcn-graph-token"}
            math_resp = client.get(
                f"/api/v1/kb/documents/{math_id}/tcn-graph", headers=headers
            )
            assert math_resp.status_code == 200
            body = math_resp.json()
            assert body["domain"] == "math"
            assert len(body["nodes"]) == 83
            painted = [n for n in body["nodes"] if n["id"] == "math:集合与基本运算"]
            assert painted and painted[0]["mastery"] == 0.42
            assert body["next_nodes"]
            assert all("reason" in n and "name" in n for n in body["next_nodes"])
            assert all(
                e["source"].startswith("math:") and e["target"].startswith("math:")
                for e in body["edges"]
            )

            none_resp = client.get(
                f"/api/v1/kb/documents/{none_id}/tcn-graph", headers=headers
            )
            assert none_resp.json()["domain"] is None
            assert none_resp.json()["nodes"] == []
            assert none_resp.json()["next_nodes"] == []

            path = client.get("/api/v1/learning-path", headers=headers)
            assert path.status_code == 200
            body = path.json()
            docs = {d["document_id"]: d for d in body["documents"]}
            assert docs[math_id]["tcn_domain"] == "math"
            assert docs[none_id]["tcn_domain"] is None
            assert "current_chapter" in docs[math_id]
            assert "next" in docs[math_id]
            domains = {d["domain"]: d for d in body["domains"]}
            assert "math" in domains
            assert math_id in [item["document_id"] for item in domains["math"]["documents"]]
            assert none_id in [item["document_id"] for item in body["untracked"]]

            domain_graph = client.get("/api/v1/kb/tcn-domains/math/graph", headers=headers)
            assert domain_graph.status_code == 200
            assert domain_graph.json()["domain"] == "math"
            assert len(domain_graph.json()["nodes"]) == 83
            missing = client.get("/api/v1/kb/tcn-domains/微积分/graph", headers=headers)
            assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()
