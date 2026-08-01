"""
本地 Chroma RAG 单元测试 — mock embedding，不下载模型
运行: cd backend && python test_local_rag.py
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud import kb as kb_crud
from app.crud import segment as segment_crud
from app.models import User
from app.services.citation_service import build_citations_from_hits
from app.services.chroma_store import ChromaStore
from app.services.segment_service import segment_document
from app.services.storage_service import storage_service


def _mock_embed(texts):
    return [[float((i + j) % 7) / 7.0 for j in range(8)] for i, _ in enumerate(texts)]


def test_chroma_upsert_and_search():
    store = ChromaStore()
    with patch("app.services.chroma_store.embed_texts", side_effect=_mock_embed):
        with patch.object(store, "_collection", None):
            with patch.object(store, "_client", None):
                import chromadb

                store._client = chromadb.EphemeralClient()
                store._collection = store._client.get_or_create_collection(
                    name="zhishi_segments_test",
                    metadata={"hnsw:space": "cosine"},
                )
                segments = [
                    {
                        "id": "seg-1",
                        "content": "微积分是研究变化率的数学分支",
                        "title": "微积分",
                        "char_start": 0,
                        "char_end": 20,
                    },
                    {
                        "id": "seg-2",
                        "content": "牛顿和莱布尼茨独立发明微积分",
                        "title": "历史",
                        "char_start": 20,
                        "char_end": 40,
                    },
                ]
                n = store.upsert_segments(
                    document_id="doc-1",
                    segments=segments,
                    user_id=1,
                    collection_id="coll-1",
                    display_name="calc.md",
                )
                assert n == 2

                hits = store.search(
                    "什么是微积分",
                    user_id=1,
                    collection_id="coll-1",
                    top_k=2,
                )
                assert len(hits) >= 1
                assert hits[0]["document_id"] == "doc-1"
                assert hits[0]["segment_id"]
                assert "微积分" in hits[0]["content"]

                store.delete_by_document("doc-1")
                hits_after = store.search(
                    "微积分", user_id=1, collection_id="coll-1", top_k=2
                )
                assert len(hits_after) == 0

    print("OK chroma_upsert_and_search")


def test_local_citation_from_metadata():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(
        email="rag@test.local",
        password_hash="x",
        username="raguser",
        nickname="RAG",
        is_active=True,
        plan_level=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cols = kb_crud.seed_default_collections(db, user.id, None)
    db.commit()
    study_coll = cols[0]

    md = "# 向量检索\nChroma 本地 RAG 测试段落。\n"
    parsed_path = storage_service.save_global_parsed("hash_rag_test", md)
    global_doc = kb_crud.create_global_document(
        db,
        content_hash="hash_rag_test",
        original_filename="rag.md",
        file_size=len(md.encode()),
        storage_path="/tmp/rag.md",
        parsed_text_path=parsed_path,
    )
    doc = kb_crud.create_document(
        db,
        user_id=user.id,
        collection_id=study_coll.id,
        zone="study",
        display_name="rag.md",
        content_hash="hash_rag_test",
        global_document_id=global_doc.id,
        parsed_cache_key=parsed_path,
        indexing_status="processing",
    )
    db.commit()
    segment_document(doc.id, db)
    db.commit()

    segments = segment_crud.list_segments_for_document(db, doc.id)
    target = segments[0]

    local_hits = [
        {
            "score": 0.95,
            "content": target.content,
            "document_id": doc.id,
            "segment_id": target.id,
            "collection_id": study_coll.id,
            "title": target.title,
            "char_start": target.char_start,
            "char_end": target.char_end,
            "display_name": doc.display_name,
        }
    ]

    citations = build_citations_from_hits(
        db, user.id, study_coll.id, local_hits
    )
    assert len(citations) == 1
    c = citations[0]
    assert c.doc_id == doc.id
    assert c.segment_id == target.id
    assert c.char_start == target.char_start
    assert c.char_end == target.char_end

    print("OK local_citation_from_metadata")
    db.close()


if __name__ == "__main__":
    os.environ.setdefault("RAG_BACKEND", "local")
    test_chroma_upsert_and_search()
    test_local_citation_from_metadata()
    print("All local RAG tests passed.")
