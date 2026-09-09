"""TCN 封闭学科名单：四个领域、抽目录判学科、目录接口带回判断。"""
import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.deps import get_current_active_user, get_db
from app.crud import toc as toc_crud
from app.models import Document, KbCollection, User
from app.services.knowledge import kb_service, segment_service
from app.services.tcn.domain_classifier import (
    classify_tcn_domain,
    classify_tcn_domain_sync,
    parse_domain_output,
)
from app.services.tcn.domains import (
    DEFAULT_TCN_DOMAINS,
    list_domains_public,
    normalize_domain,
    parse_user_domain,
)
from pgutil import make_sessionmaker
from server import app

CLOSED = ("higher_math", "math", "physics", "discrete_math")


@pytest.fixture()
def db_session():
    engine, SessionLocal = make_sessionmaker()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def kb_client(monkeypatch):
    engine, SessionLocal = make_sessionmaker()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    with SessionLocal() as db:
        user = User(
            email="tcn-domain@example.com",
            password_hash="hash",
            nickname="学科测试",
            is_active=True,
        )
        db.add(user)
        db.flush()
        collection = KbCollection(
            user_id=user.id, name="学习区", zone="study", is_default=True
        )
        db.add(collection)
        db.flush()
        doc = Document(
            user_id=user.id,
            collection_id=collection.id,
            display_name="高等数学讲义",
            zone="study",
            content_hash="hash-tcn-domain",
        )
        db.add(doc)
        db.commit()
        user_id = user.id
        doc_id = doc.id

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_user(authorization: str | None = Header(default=None)):
        if authorization != "Bearer tcn-domain-token":
            raise HTTPException(status_code=401, detail="Not authenticated")
        return {"user_id": user_id, "is_active": True}

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_user
    try:
        with TestClient(app) as client:
            yield client, SessionLocal, doc_id
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()


def _auth() -> dict:
    return {"Authorization": "Bearer tcn-domain-token"}


def test_closed_roster_is_four_domains():
    assert tuple(item["id"] for item in DEFAULT_TCN_DOMAINS) == CLOSED


@pytest.mark.parametrize("token", CLOSED)
def test_parse_accepts_closed_ids(token):
    assert parse_domain_output(token, list(CLOSED)) == token
    assert parse_domain_output(f"{token}\n", list(CLOSED)) == token
    assert normalize_domain(token, list(CLOSED)) == token


@pytest.mark.parametrize(
    "raw",
    ["", "none", "None", "null", "未知", "微积分", "calculus", "higher_math:夹逼准则"],
)
def test_parse_unknown_is_none(raw):
    assert parse_domain_output(raw, list(CLOSED)) is None
    assert normalize_domain(raw, list(CLOSED)) is None


def test_user_patch_rejects_invented_name():
    with pytest.raises(ValueError):
        parse_user_domain("微积分", list(CLOSED))
    assert parse_user_domain("none", list(CLOSED)) is None
    assert parse_user_domain("physics", list(CLOSED)) == "physics"


def test_seeded_domain_table(db_session):
    rows = list_domains_public(db_session)
    assert [r["id"] for r in rows] == list(CLOSED)
    assert {r["label"] for r in rows} == {"高等数学", "数学", "物理", "离散数学"}


def test_assign_skips_existing_human_value(db_session, monkeypatch):
    user = User(email="keep@example.com", password_hash="h", nickname="u", is_active=True)
    db_session.add(user)
    db_session.flush()
    collection = KbCollection(user_id=user.id, name="c", zone="study")
    db_session.add(collection)
    db_session.flush()
    doc = Document(
        user_id=user.id,
        collection_id=collection.id,
        display_name="普通物理",
        zone="study",
        content_hash="keep-domain",
        tcn_domain="physics",
    )
    db_session.add(doc)
    db_session.flush()

    def boom(**kwargs):
        raise AssertionError("已有学科时不应再调分类")

    import app.services.tcn.domain_classifier as classifier

    monkeypatch.setattr(classifier, "classify_tcn_domain_sync", boom)
    segment_service._assign_tcn_domain(db_session, doc, "正文", [{"title": "力学"}])
    assert doc.tcn_domain == "physics"


def test_assign_writes_closed_id(db_session, monkeypatch):
    user = User(email="write@example.com", password_hash="h", nickname="u", is_active=True)
    db_session.add(user)
    db_session.flush()
    collection = KbCollection(user_id=user.id, name="c", zone="study")
    db_session.add(collection)
    db_session.flush()
    doc = Document(
        user_id=user.id,
        collection_id=collection.id,
        display_name="离散数学",
        zone="study",
        content_hash="write-domain",
    )
    db_session.add(doc)
    db_session.flush()

    import app.services.tcn.domain_classifier as classifier

    monkeypatch.setattr(
        classifier, "classify_tcn_domain_sync", lambda **kwargs: "discrete_math"
    )
    segment_service._assign_tcn_domain(
        db_session, doc, "图与树", [{"title": "命题逻辑"}]
    )
    assert doc.tcn_domain == "discrete_math"


def test_assign_none_when_unsure(db_session, monkeypatch):
    user = User(email="none@example.com", password_hash="h", nickname="u", is_active=True)
    db_session.add(user)
    db_session.flush()
    collection = KbCollection(user_id=user.id, name="c", zone="study")
    db_session.add(collection)
    db_session.flush()
    doc = Document(
        user_id=user.id,
        collection_id=collection.id,
        display_name="菜谱",
        zone="study",
        content_hash="none-domain",
    )
    db_session.add(doc)
    db_session.flush()

    import app.services.tcn.domain_classifier as classifier

    monkeypatch.setattr(classifier, "classify_tcn_domain_sync", lambda **kwargs: None)
    segment_service._assign_tcn_domain(db_session, doc, "红烧肉", [])
    assert doc.tcn_domain is None


def test_classify_returns_none_when_pool_empty(monkeypatch):
    class EmptyPool:
        def acquire(self):
            return None

    monkeypatch.setattr(
        "app.services.llm.llm_pool.llm_pool", EmptyPool(), raising=False
    )
    assert (
        asyncio.run(
            classify_tcn_domain(title="高等数学", toc_titles=["极限"], excerpt="夹逼")
        )
        is None
    )
    assert (
        classify_tcn_domain_sync(title="高等数学", toc_titles=["极限"], excerpt="夹逼")
        is None
    )


def test_classify_awaits_apredict_not_llm_runner(monkeypatch):
    class FakeLLM:
        async def apredict_no_stream(self, **kwargs):
            assert kwargs.get("temperature") == 0
            return {"content": "higher_math"}

        def predict(self, **kwargs):
            raise AssertionError("异步切段不应走 sync predict")

    class Pool:
        def acquire(self):
            return FakeLLM()

    monkeypatch.setattr("app.services.llm.llm_pool.llm_pool", Pool())
    monkeypatch.setattr(
        "app.utils.prompt_loader.load_prompt", lambda name: "prompt"
    )
    assert (
        asyncio.run(
            classify_tcn_domain(title="张宇高数", toc_titles=["极限"], excerpt="夹逼")
        )
        == "higher_math"
    )


def test_classify_sync_uses_predict_not_new_loop(monkeypatch):
    class FakeLLM:
        async def apredict_no_stream(self, **kwargs):
            raise AssertionError("同步切段不应走 apredict")

        def predict(self, **kwargs):
            assert kwargs.get("stream") is False
            return {"content": "physics"}

    class Pool:
        def acquire(self):
            return FakeLLM()

    monkeypatch.setattr("app.services.llm.llm_pool.llm_pool", Pool())
    monkeypatch.setattr(
        "app.utils.prompt_loader.load_prompt", lambda name: "prompt"
    )
    assert (
        classify_tcn_domain_sync(title="普通物理", toc_titles=["力学"], excerpt="牛顿")
        == "physics"
    )


def test_update_document_domain(db_session):
    user = User(email="patch@example.com", password_hash="h", nickname="u", is_active=True)
    db_session.add(user)
    db_session.flush()
    collection = KbCollection(user_id=user.id, name="c", zone="study")
    db_session.add(collection)
    db_session.flush()
    doc = Document(
        user_id=user.id,
        collection_id=collection.id,
        display_name="书",
        zone="study",
        content_hash="patch-domain",
    )
    db_session.add(doc)
    db_session.commit()

    out = kb_service.update_document_tcn_domain(
        db_session, user.id, doc.id, "math"
    )
    assert out.tcn_domain == "math"
    assert out.tcn_domain_label == "数学"

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        kb_service.update_document_tcn_domain(
            db_session, user.id, doc.id, "微积分"
        )
    assert exc.value.status_code == 400

    cleared = kb_service.update_document_tcn_domain(
        db_session, user.id, doc.id, None
    )
    assert cleared.tcn_domain is None
    assert cleared.tcn_domain_label is None


def test_toc_and_config_return_domain(kb_client):
    client, SessionLocal, doc_id = kb_client
    with SessionLocal() as db:
        toc_crud.replace_toc_for_document(
            db,
            doc_id,
            [{"title": "极限", "page_start": 1, "page_end": 3}],
        )
        doc = db.query(Document).filter(Document.id == doc_id).one()
        doc.tcn_domain = "higher_math"
        db.commit()

    roster = client.get("/api/v1/kb/tcn-domains", headers=_auth())
    assert roster.status_code == 200
    assert [d["id"] for d in roster.json()["domains"]] == list(CLOSED)

    cfg = client.get("/api/v1/kb/config", headers=_auth())
    assert cfg.status_code == 200
    assert [d["id"] for d in cfg.json()["tcn_domains"]] == list(CLOSED)

    toc = client.get(f"/api/v1/kb/documents/{doc_id}/toc", headers=_auth())
    assert toc.status_code == 200
    body = toc.json()
    assert body["tcn_domain"] == "higher_math"
    assert body["tcn_domain_label"] == "高等数学"
    assert body["toc"][0]["title"] == "极限"

    patched = client.patch(
        f"/api/v1/kb/documents/{doc_id}/tcn-domain",
        headers=_auth(),
        json={"tcn_domain": "physics"},
    )
    assert patched.status_code == 200
    assert patched.json() == {
        "document_id": doc_id,
        "tcn_domain": "physics",
        "tcn_domain_label": "物理",
    }

    listed = client.get("/api/v1/kb/documents", headers=_auth())
    assert listed.status_code == 200
    docs = listed.json()["documents"]
    assert docs[0]["tcn_domain"] == "physics"
    assert docs[0]["tcn_domain_label"] == "物理"

    bad = client.patch(
        f"/api/v1/kb/documents/{doc_id}/tcn-domain",
        headers=_auth(),
        json={"tcn_domain": "微积分"},
    )
    assert bad.status_code == 400


def test_get_document_toc_tool_includes_domain(db_session, monkeypatch):
    from contextlib import contextmanager

    from sqlalchemy.orm import sessionmaker

    from app.services.tools.task_tools import TaskPlannerTools

    user = User(email="tool@example.com", password_hash="h", nickname="u", is_active=True)
    db_session.add(user)
    db_session.flush()
    collection = KbCollection(user_id=user.id, name="c", zone="study")
    db_session.add(collection)
    db_session.flush()
    doc = Document(
        user_id=user.id,
        collection_id=collection.id,
        display_name="普通物理",
        zone="study",
        content_hash="tool-domain",
        tcn_domain="physics",
    )
    db_session.add(doc)
    db_session.flush()
    toc_crud.replace_toc_for_document(
        db_session,
        doc.id,
        [{"title": "力学", "page_start": 1, "page_end": 2}],
    )
    db_session.commit()
    user_id = user.id
    doc_id = doc.id

    SessionLocal = sessionmaker(
        bind=db_session.get_bind(), autocommit=False, autoflush=False
    )

    @contextmanager
    def _short():
        db = SessionLocal()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    monkeypatch.setattr("app.services.tools.task_tools.short_session", _short)
    payload = json.loads(TaskPlannerTools(user_id=user_id).get_document_toc(doc_id))
    assert payload["tcn_domain"] == "physics"
    assert payload["tcn_domain_label"] == "物理"
