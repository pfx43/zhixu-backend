import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_active_user, get_db
from app.core.database import Base
from server import app
from app.models import Document, DocumentSegment, KbCollection, User, UserNote


def _create_temp_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def search_client(monkeypatch):
    engine, SessionLocal = _create_temp_db()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    with SessionLocal() as db:
        first_user = User(
            email="search-first@example.com",
            password_hash="hash",
            nickname="Search First",
            is_active=True,
        )
        second_user = User(
            email="search-second@example.com",
            password_hash="hash",
            nickname="Search Second",
            is_active=True,
        )
        db.add_all([first_user, second_user])
        db.commit()
        db.refresh(first_user)
        db.refresh(second_user)
        users = {"first": first_user.id, "second": second_user.id}

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    tokens = {
        "Bearer search-first-token": users["first"],
        "Bearer search-second-token": users["second"],
    }

    def override_current_active_user(
        authorization: str | None = Header(default=None),
    ):
        user_id = tokens.get(authorization)
        if user_id is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return {"user_id": user_id, "is_active": True}

    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_current_active_user

    try:
        with TestClient(app) as client:
            yield client, SessionLocal, users
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()


def _auth(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer search-{user}-token"}


def _add_document(
    db,
    *,
    user_id: int,
    collection_id: str,
    name: str,
    content_hash: str,
    segment_content: str | None = None,
    zone: str = "study",
    segment_status: str = "completed",
    indexing_status: str = "completed",
):
    document = Document(
        user_id=user_id,
        collection_id=collection_id,
        display_name=name,
        zone=zone,
        content_hash=content_hash,
        segment_status=segment_status,
        indexing_status=indexing_status,
    )
    db.add(document)
    db.flush()
    if segment_content is not None:
        db.add(
            DocumentSegment(
                document_id=document.id,
                order_index=0,
                title="测试分段",
                content=segment_content,
                char_start=0,
                char_end=len(segment_content),
            )
        )
    return document


def test_search_returns_note_and_completed_document_body_hits(search_client):
    client, SessionLocal, users = search_client
    with SessionLocal() as db:
        collection = KbCollection(
            user_id=users["first"],
            name="历史学习",
            zone="study",
        )
        db.add(collection)
        db.flush()
        db.add(
            UserNote(
                user_id=users["first"],
                collection_id=collection.id,
                title="复习安排",
                content_md="本周复习中国近代史的关键事件。",
            )
        )
        document = Document(
            user_id=users["first"],
            collection_id=collection.id,
            display_name="历史课程资料.pdf",
            zone="study",
            content_hash="search-red-document",
            segment_status="completed",
            indexing_status="completed",
        )
        db.add(document)
        db.flush()
        db.add(
            DocumentSegment(
                document_id=document.id,
                order_index=0,
                title="第一章",
                content="中国近代史从鸦片战争开始。",
                char_start=0,
                char_end=15,
            )
        )
        db.commit()

    response = client.get(
        "/api/v1/search",
        params={"q": "中国近代史"},
        headers=_auth("first"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "中国近代史"
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["limit"] == 20
    assert payload["partial"] is False
    assert payload["pending_document_count"] == 0
    assert {item["type"] for item in payload["items"]} == {"note", "document"}
    assert {item["match_source"] for item in payload["items"]} == {"content"}
    for item in payload["items"]:
        assert {"id", "type", "title", "subtitle", "updated_at", "collection_id", "match_source"} <= set(item)


def test_search_requires_bearer_auth(search_client):
    client, _, _ = search_client

    response = client.get("/api/v1/search", params={"q": "中国近代史"})

    assert response.status_code == 401


def test_search_never_leaks_other_users_notes_documents_or_segments(search_client):
    client, SessionLocal, users = search_client
    with SessionLocal() as db:
        own_collection = KbCollection(
            user_id=users["first"], name="本人分区", zone="study"
        )
        other_collection = KbCollection(
            user_id=users["second"], name="他人分区", zone="study"
        )
        db.add_all([own_collection, other_collection])
        db.flush()
        own_collection_id = own_collection.id
        db.add(
            UserNote(
                user_id=users["first"],
                collection_id=own_collection.id,
                title="本人笔记",
                content_md="隔离关键词只属于当前用户。",
            )
        )
        db.add(
            UserNote(
                user_id=users["second"],
                collection_id=other_collection.id,
                title="他人笔记",
                content_md="隔离关键词绝不能泄露。",
            )
        )
        _add_document(
            db,
            user_id=users["first"],
            collection_id=own_collection.id,
            name="本人资料.pdf",
            content_hash="search-isolation-first",
            segment_content="隔离关键词出现在本人的正文。",
        )
        _add_document(
            db,
            user_id=users["second"],
            collection_id=other_collection.id,
            name="他人资料.pdf",
            content_hash="search-isolation-second",
            segment_content="隔离关键词出现在他人的正文。",
        )
        db.commit()

    response = client.get(
        "/api/v1/search",
        params={"q": "隔离关键词"},
        headers=_auth("first"),
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["title"] for item in items} == {"本人笔记", "本人资料.pdf"}
    assert {item["collection_id"] for item in items} == {own_collection_id}


def test_search_scopes_notes_documents_and_returns_empty_results(search_client):
    client, SessionLocal, users = search_client
    with SessionLocal() as db:
        collection = KbCollection(
            user_id=users["first"], name="范围分区", zone="study"
        )
        db.add(collection)
        db.flush()
        db.add(
            UserNote(
                user_id=users["first"],
                collection_id=collection.id,
                title="范围关键词笔记",
                content_md="笔记正文",
            )
        )
        _add_document(
            db,
            user_id=users["first"],
            collection_id=collection.id,
            name="范围关键词资料.pdf",
            content_hash="search-scope-document",
            segment_content="资料正文",
        )
        db.commit()

    notes_response = client.get(
        "/api/v1/search",
        params={"q": "范围关键词", "scope": "notes"},
        headers=_auth("first"),
    )
    documents_response = client.get(
        "/api/v1/search",
        params={"q": "范围关键词", "scope": "documents"},
        headers=_auth("first"),
    )
    empty_response = client.get(
        "/api/v1/search",
        params={"q": "没有任何匹配"},
        headers=_auth("first"),
    )

    assert notes_response.status_code == 200
    assert [item["type"] for item in notes_response.json()["items"]] == ["note"]
    assert documents_response.status_code == 200
    assert [item["type"] for item in documents_response.json()["items"]] == ["document"]
    assert empty_response.status_code == 200
    assert empty_response.json()["items"] == []
    assert empty_response.json()["total"] == 0


def test_search_filters_current_user_collection_and_paginates(search_client):
    client, SessionLocal, users = search_client
    with SessionLocal() as db:
        selected_collection = KbCollection(
            user_id=users["first"], name="指定分区", zone="study"
        )
        other_collection = KbCollection(
            user_id=users["first"], name="其他分区", zone="study"
        )
        db.add_all([selected_collection, other_collection])
        db.flush()
        selected_collection_id = selected_collection.id
        db.add_all(
            [
                UserNote(
                    user_id=users["first"],
                    collection_id=selected_collection.id,
                    title="分页检索笔记一",
                    content_md="正文",
                ),
                UserNote(
                    user_id=users["first"],
                    collection_id=selected_collection.id,
                    title="分页检索笔记二",
                    content_md="正文",
                ),
                UserNote(
                    user_id=users["first"],
                    collection_id=other_collection.id,
                    title="分页检索其他分区笔记",
                    content_md="正文",
                ),
            ]
        )
        db.commit()

    response = client.get(
        "/api/v1/search",
        params={
            "q": "分页检索",
            "scope": "notes",
            "collection_id": selected_collection_id,
            "page": 2,
            "limit": 1,
        },
        headers=_auth("first"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["page"] == 2
    assert payload["limit"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["collection_id"] == selected_collection_id


def test_search_rejects_empty_query_and_invalid_scope(search_client):
    client, _, _ = search_client

    empty_response = client.get(
        "/api/v1/search", params={"q": ""}, headers=_auth("first")
    )
    whitespace_response = client.get(
        "/api/v1/search", params={"q": "   "}, headers=_auth("first")
    )
    scope_response = client.get(
        "/api/v1/search",
        params={"q": "中国近代史", "scope": "everything"},
        headers=_auth("first"),
    )

    assert empty_response.status_code == 422
    assert whitespace_response.status_code == 422
    assert scope_response.status_code == 422


def test_search_marks_pending_study_documents_as_partial_without_body_claim(search_client):
    client, SessionLocal, users = search_client
    with SessionLocal() as db:
        collection = KbCollection(
            user_id=users["first"], name="待处理分区", zone="study"
        )
        db.add(collection)
        db.flush()
        _add_document(
            db,
            user_id=users["first"],
            collection_id=collection.id,
            name="量子力学草稿.pdf",
            content_hash="search-pending-document",
            segment_content="量子力学正文即使已有片段也不得被当作可搜索正文。",
            segment_status="processing",
            indexing_status="processing",
        )
        db.commit()

    response = client.get(
        "/api/v1/search",
        params={"q": "量子力学"},
        headers=_auth("first"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["partial"] is True
    assert payload["pending_document_count"] == 1
    assert payload["total"] == 1
    assert payload["items"][0]["match_source"] == "title"
    assert payload["items"][0]["indexing_status"] == "processing"


def test_search_returns_only_exact_lexical_matches_without_vector_fallback(search_client):
    client, SessionLocal, users = search_client
    with SessionLocal() as db:
        collection = KbCollection(
            user_id=users["first"], name="降级分区", zone="study"
        )
        db.add(collection)
        db.flush()
        _add_document(
            db,
            user_id=users["first"],
            collection_id=collection.id,
            name="近代课程资料.pdf",
            content_hash="search-fallback-match",
            segment_content="中国近代史研究需要使用可靠史料。",
        )
        _add_document(
            db,
            user_id=users["first"],
            collection_id=collection.id,
            name="无关资料.pdf",
            content_hash="search-fallback-unrelated",
            segment_content="这是完全不同的数学资料。",
        )
        db.commit()

    response = client.get(
        "/api/v1/search",
        params={"q": "中国近代史"},
        headers=_auth("first"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "近代课程资料.pdf"
    assert payload["items"][0]["match_source"] == "content"


def test_search_title_hit_has_readable_subtitle_when_note_body_is_empty(search_client):
    client, SessionLocal, users = search_client
    with SessionLocal() as db:
        db.add(
            UserNote(
                user_id=users["first"],
                title="中国近代史标题笔记",
                content_md="",
            )
        )
        db.commit()

    response = client.get(
        "/api/v1/search",
        params={"q": "中国近代史"},
        headers=_auth("first"),
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["match_source"] == "title"
    assert item["subtitle"].strip()


def test_search_openapi_declares_response_model(search_client):
    client, _, _ = search_client

    openapi = client.get("/openapi.json").json()
    response_schema = openapi["paths"]["/api/v1/search"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    response_model_name = response_schema["$ref"].rsplit("/", 1)[-1]
    response_model = openapi["components"]["schemas"][response_model_name]

    assert {
        "query",
        "items",
        "total",
        "page",
        "limit",
        "partial",
        "pending_document_count",
    } <= set(response_model["properties"])


def test_search_is_mounted_on_production_server_entrypoint():
    from server import app as production_app

    openapi = production_app.openapi()

    assert "/api/v1/search" in openapi["paths"]
    assert "get" in openapi["paths"]["/api/v1/search"]
