"""关键词检索 RAG — RAG_BACKEND=keyword 纯词法检索，不走向量。"""
import pytest
from types import SimpleNamespace
from unittest.mock import patch

from pgutil import make_sessionmaker

import app.core.config as config
from app.models import Document, DocumentSegment, KbCollection, User
from app.services.chat import keyword_retrieval_service

_CHROMA_HIT_FIELDS = (
    "score",
    "content",
    "document_id",
    "segment_id",
    "collection_id",
    "title",
    "display_name",
    "char_start",
    "char_end",
)


def _create_temp_db():
    return make_sessionmaker()


@pytest.fixture()
def keyword_db():
    engine, SessionLocal = _create_temp_db()
    with SessionLocal() as db:
        owner = User(
            email="kw-owner@example.com",
            password_hash="hash",
            nickname="Owner",
            is_active=True,
        )
        other = User(
            email="kw-other@example.com",
            password_hash="hash",
            nickname="Other",
            is_active=True,
        )
        db.add_all([owner, other])
        db.commit()
        db.refresh(owner)
        db.refresh(other)

        coll = KbCollection(user_id=owner.id, name="学习区", zone="study")
        db.add(coll)
        db.commit()
        db.refresh(coll)

        def add_document(
            user_id,
            collection_id,
            name,
            content,
            title="第一章",
            zone="study",
            segment_status="completed",
            indexing_status="completed",
        ):
            document = Document(
                user_id=user_id,
                collection_id=collection_id,
                display_name=name,
                zone=zone,
                content_hash=name,
                segment_status=segment_status,
                indexing_status=indexing_status,
            )
            db.add(document)
            db.flush()
            db.add(
                DocumentSegment(
                    document_id=document.id,
                    order_index=0,
                    title=title,
                    content=content,
                    char_start=0,
                    char_end=len(content),
                )
            )
            db.flush()
            return document

        owner_doc = add_document(
            owner.id,
            coll.id,
            "中国近代史.pdf",
            "中国近代史从鸦片战争开始，辛亥革命推翻了清王朝。",
        )
        unrelated_doc = add_document(
            owner.id,
            coll.id,
            "高等数学.pdf",
            "极限、导数与积分构成了高等数学的核心。",
        )
        other_doc = add_document(
            other.id,
            coll.id,
            "他人资料.pdf",
            "这段内容也包含中国近代史四个字，但属于其他用户。",
        )
        pending_doc = add_document(
            owner.id,
            coll.id,
            "待索引资料.pdf",
            "包含中国近代史但尚未完成索引。",
            segment_status="processing",
            indexing_status="processing",
        )
        db.commit()
        yield SessionLocal, owner.id, coll.id, owner_doc, unrelated_doc, other_doc, pending_doc
    engine.dispose()


def test_keyword_search_returns_matching_segment_with_chroma_hit_shape(keyword_db):
    SessionLocal, user_id, coll_id, owner_doc, *_ = keyword_db
    with SessionLocal() as db:
        hits = keyword_retrieval_service.search(
            db, "中国近代史", user_id=user_id
        )

    assert len(hits) == 1
    hit = hits[0]
    for field in _CHROMA_HIT_FIELDS:
        assert field in hit, f"hit 缺少字段 {field}"
    assert hit["document_id"] == owner_doc.id
    assert hit["collection_id"] == coll_id
    assert hit["segment_id"]
    assert "中国近代史" in hit["content"]
    assert hit["score"] == 1.0


def test_keyword_search_is_lexical_and_never_leaks_other_users(keyword_db):
    SessionLocal, user_id, coll_id, *_ = keyword_db
    with SessionLocal() as db:
        hits = keyword_retrieval_service.search(
            db, "中国近代史", user_id=user_id
        )

    assert len(hits) == 1
    assert "其他用户" not in hits[0]["content"]


def test_keyword_search_excludes_pending_and_unrelated_documents(keyword_db):
    SessionLocal, user_id, *_ = keyword_db
    with SessionLocal() as db:
        hits = keyword_retrieval_service.search(
            db, "中国近代史", user_id=user_id
        )
    assert len(hits) == 1
    assert "待索引" not in hits[0]["content"]
    assert "高等数学" not in hits[0]["content"]


def test_keyword_search_honors_collection_filter(keyword_db):
    SessionLocal, user_id, coll_id, *_ = keyword_db
    with SessionLocal() as db:
        hits = keyword_retrieval_service.search(
            db,
            "中国近代史",
            user_id=user_id,
            collection_id="nonexistent-collection",
        )
    assert hits == []


def test_keyword_search_returns_empty_for_no_match(keyword_db):
    SessionLocal, user_id, *_ = keyword_db
    with SessionLocal() as db:
        hits = keyword_retrieval_service.search(
            db, "完全没有出现过的关键词", user_id=user_id
        )
    assert hits == []


def test_keyword_search_returns_empty_without_db_or_blank_query(keyword_db):
    SessionLocal, user_id, *_ = keyword_db
    with SessionLocal() as db:
        assert keyword_retrieval_service.search(db, "  ", user_id=user_id) == []
    assert keyword_retrieval_service.search(None, "词", user_id=user_id) == []


def test_keyword_search_matches_segment_title_and_display_name(keyword_db):
    """只出现在 segment title / document display_name 的关键词必须能命中。"""
    SessionLocal, user_id, coll_id, *_ = keyword_db
    with SessionLocal() as db:
        title_doc = Document(
            user_id=user_id, collection_id=coll_id, display_name="普通文件名.pdf",
            zone="study", content_hash="t1",
            segment_status="completed", indexing_status="completed",
        )
        db.add(title_doc)
        db.flush()
        db.add(DocumentSegment(
            document_id=title_doc.id, order_index=0, title="光合作用详解",
            content="正文完全没有关键词", char_start=0, char_end=9,
        ))
        name_doc = Document(
            user_id=user_id, collection_id=coll_id, display_name="牛顿力学.pdf",
            zone="study", content_hash="t2",
            segment_status="completed", indexing_status="completed",
        )
        db.add(name_doc)
        db.flush()
        db.add(DocumentSegment(
            document_id=name_doc.id, order_index=0, title="第一章",
            content="正文也没有关键词", char_start=0, char_end=8,
        ))
        db.commit()

        hits_title = keyword_retrieval_service.search(db, "光合作用", user_id=user_id)
        hits_name = keyword_retrieval_service.search(db, "牛顿力学", user_id=user_id)

    assert len(hits_title) == 1
    assert hits_title[0]["title"] == "光合作用详解"
    assert hits_title[0]["score"] > 0
    assert len(hits_name) == 1
    assert hits_name[0]["display_name"] == "牛顿力学.pdf"


def test_keyword_search_bounded_candidates(keyword_db):
    """大量匹配段时有界查询仍返回 top_k，不炸内存。"""
    SessionLocal, user_id, coll_id, *_ = keyword_db
    with SessionLocal() as db:
        for i in range(205):
            doc = Document(
                user_id=user_id, collection_id=coll_id, display_name=f"批量{i}.pdf",
                zone="study", content_hash=f"b{i}",
                segment_status="completed", indexing_status="completed",
            )
            db.add(doc)
            db.flush()
            db.add(DocumentSegment(
                document_id=doc.id, order_index=0, title="第一章",
                content=f"批量文档内容 {i} 都包含关键词", char_start=0, char_end=16,
            ))
        db.commit()
        hits = keyword_retrieval_service.search(db, "关键词", user_id=user_id)

    assert len(hits) == 5  # top_k 默认 5


def test_config_helpers_track_backend(monkeypatch):
    monkeypatch.setattr(config, "RAG_BACKEND", "keyword")
    assert config.is_keyword_rag() is True
    assert config.is_local_rag() is True
    assert config.is_dify_rag() is False

    monkeypatch.setattr(config, "RAG_BACKEND", "local")
    assert config.is_keyword_rag() is False
    assert config.is_local_rag() is True
    assert config.is_dify_rag() is False

    monkeypatch.setattr(config, "RAG_BACKEND", "dify")
    assert config.is_keyword_rag() is False
    assert config.is_local_rag() is False
    assert config.is_dify_rag() is True


def test_knowledge_retriever_search_is_async_and_keeps_hit_shape():
    import asyncio
    import inspect
    import json

    from app.services.tools.knowledge_retriever import KnowledgeRetriever

    async def retrieve(user_id, query, top_k=5):
        assert user_id == 0
        assert query == "中国近代史"
        return [
            {
                "score": 1.0,
                "content": "命中",
                "title": "第一章",
                "display_name": "史.pdf",
                "document_id": "d1",
                "segment_id": "s1",
            }
        ]

    retriever = KnowledgeRetriever(retrieve_fn=retrieve)
    assert inspect.iscoroutinefunction(retriever.search)
    payload = json.loads(asyncio.run(retriever.search("中国近代史")))
    assert payload["count"] == 1
    assert payload["hits"][0]["segment_id"] == "s1"
    assert retriever.last_hits[0]["content"] == "命中"


def test_zhixu_agent_retrieve_dispatches_to_keyword_search(monkeypatch):
    from contextlib import asynccontextmanager

    from app.services.agents import zhixu_agent

    monkeypatch.setattr(config, "RAG_BACKEND", "keyword")
    fake_hits = [{"score": 1.0, "content": "命中内容", "segment_id": "s1"}]
    seen = {}

    async def fake_keyword_search(db, query, **kwargs):
        seen["db"] = db
        seen["query"] = query
        seen["kwargs"] = kwargs
        return fake_hits

    @asynccontextmanager
    async def fake_async_short_session():
        yield "short-async-db"

    monkeypatch.setattr(zhixu_agent, "keyword_search_async", fake_keyword_search)
    monkeypatch.setattr(zhixu_agent, "async_short_session", fake_async_short_session)

    agent = zhixu_agent.ZhixuAgent(user_id=7, dataset_id="")
    retrieve = agent._make_retrieve_fn(collection_id="collection-1")

    import asyncio

    hits = asyncio.run(retrieve(7, "中国近代史", top_k=3))
    assert hits == fake_hits
    assert seen["db"] == "short-async-db"
    assert seen["query"] == "中国近代史"
    assert seen["kwargs"]["user_id"] == 7
    assert seen["kwargs"]["collection_id"] == "collection-1"
    assert seen["kwargs"]["top_k"] == 3


class _FakeDb:
    def flush(self):
        pass


def test_segment_document_skips_chroma_and_completes_in_keyword_mode(monkeypatch):
    from app.services.knowledge import segment_service

    monkeypatch.setattr(config, "RAG_BACKEND", "keyword")
    doc = SimpleNamespace(
        id="doc-1",
        zone="study",
        segment_status="not_started",
        indexing_status="pending",
        parsed_cache_key="parsed.txt",
        global_document=None,
    )
    db = _FakeDb()

    monkeypatch.setattr(
        segment_service.segment_crud, "get_document_by_id", lambda db, did: doc
    )
    monkeypatch.setattr(
        segment_service,
        "_load_document_text",
        lambda document: ("第一章 中国近代史 文本", None),
    )
    monkeypatch.setattr(
        segment_service,
        "split_text",
        lambda text: [{"content": "中国近代史 文本", "order_index": 0}],
    )
    monkeypatch.setattr(
        segment_service.segment_crud,
        "delete_segments_for_document",
        lambda db, did: None,
    )
    monkeypatch.setattr(
        segment_service.segment_crud,
        "bulk_create_segments",
        lambda db, did, segs: None,
    )

    with patch(
        "app.services.knowledge.index_service.index_document_segments",
        side_effect=AssertionError("keyword 模式不得写入 Chroma"),
    ) as index_call:
        result = segment_service.segment_document("doc-1", db)

    assert result == 1
    assert doc.segment_status == "completed"
    assert doc.indexing_status == "completed"
    index_call.assert_not_called()
