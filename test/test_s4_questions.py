"""#17 出题页 / 邻页：页码写入、页数上限截断、邻页范围、用户隔离、SSE 进度事件。"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import (
    User,
    KbCollection,
    Document,
    GlobalQuestion,
    QuestionProvenance,
    UserQuestionRef,
)
from app.crud import question as question_crud
from app.services.quiz import question_gen_service
from app.services.tools.question_gen_tools import QuestionGenTools
from app.core.config import MAX_PAGES_PER_GEN
from pgutil import make_sessionmaker


@pytest.fixture()
def db_session():
    engine, SessionLocal = make_sessionmaker()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_user(db, email: str, nickname: str = "用户") -> User:
    user = User(email=email, password_hash="hash", nickname=nickname, is_active=True)
    db.add(user)
    db.flush()
    return user


def _make_doc(db, user: User, name: str = "测试文档") -> Document:
    collection = KbCollection(user_id=user.id, name=f"collection-{name}", zone="study")
    db.add(collection)
    db.flush()
    doc = Document(
        user_id=user.id,
        collection_id=collection.id,
        display_name=name,
        zone="study",
        content_hash=f"hash-{name}-{user.id}",
    )
    db.add(doc)
    db.flush()
    return doc


def _page(page_number: int) -> dict:
    return {
        "page_number": page_number,
        "title": f"第 {page_number} 页",
        "content": f"第 {page_number} 页的正文内容。",
        "char_start": 0,
        "char_end": 100,
        "segment_id": None,
    }


def _qdata(stem: str = "这道题选什么？") -> dict:
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
        "explanation": "解析",
        "tags": ["测试"],
    }


# ─── 纯逻辑：页数上限 ───────────────────────────────

def test_cap_page_numbers_keeps_within_limit():
    pages = list(range(1, MAX_PAGES_PER_GEN + 1))
    assert question_gen_service.cap_page_numbers(pages) == pages


def test_cap_page_numbers_truncates_over_limit():
    pages = list(range(1, MAX_PAGES_PER_GEN + 5))
    capped = question_gen_service.cap_page_numbers(pages)
    assert len(capped) == MAX_PAGES_PER_GEN
    assert capped == pages[:MAX_PAGES_PER_GEN]


# ─── 纯逻辑：邻页工具 get_near_page ─────────────────

def test_get_near_page_only_adjacent_offset():
    tools = QuestionGenTools(
        pages={
            4: {"title": "第 4 页", "content": "p4"},
            5: {"title": "第 5 页", "content": "p5"},
            6: {"title": "第 6 页", "content": "p6"},
        },
        allowed_page_numbers={4, 5, 6},
        max_near_lookups=5,
    )
    # 只能 +1 / -1，翻一步
    assert json.loads(tools.get_near_page(5, 1))["page_number"] == 6
    assert json.loads(tools.get_near_page(6, -1))["page_number"] == 5
    # offset 不是 ±1 → 拒绝
    assert "error" in json.loads(tools.get_near_page(5, 2))
    assert "error" in json.loads(tools.get_near_page(5, 0))


def test_get_near_page_cannot_escape_selected_range():
    tools = QuestionGenTools(
        pages={
            5: {"title": "第 5 页", "content": "p5"},
            6: {"title": "第 6 页", "content": "p6"},
            7: {"title": "第 7 页", "content": "p7"},
            8: {"title": "第 8 页", "content": "p8"},
        },
        allowed_page_numbers={5, 6, 7, 8},  # 选中范围 {5,6,7} 的 ±1 → 允许 4..8
        max_near_lookups=10,
    )
    # 8 在允许范围内（选中 {5,6,7} 的 +1）
    assert json.loads(tools.get_near_page(7, 1))["page_number"] == 8
    # 9 超出范围 → 拒绝
    assert "error" in json.loads(tools.get_near_page(8, 1))


def test_get_near_page_lookup_limit():
    tools = QuestionGenTools(
        pages={
            4: {"title": "第 4 页", "content": "p4"},
            5: {"title": "第 5 页", "content": "p5"},
            6: {"title": "第 6 页", "content": "p6"},
        },
        allowed_page_numbers={4, 5, 6},
        max_near_lookups=2,
    )
    assert "error" not in json.loads(tools.get_near_page(5, -1))
    assert "error" not in json.loads(tools.get_near_page(5, 1))
    # 超过次数上限 → 拒绝
    assert "error" in json.loads(tools.get_near_page(6, -1))


# ─── DB 集成：页码写入 ───────────────────────────────

def test_persist_question_from_page_writes_page_number(db_session):
    user = _make_user(db_session, "cyb-page@example.com")
    doc = _make_doc(db_session, user)
    page = _page(5)

    created, reused = question_gen_service._persist_question_from_page(
        db_session,
        user_id=user.id,
        document=doc,
        page=page,
        qdata=_qdata(stem="第 5 页的题目？"),
        source_type="generated",
    )
    db_session.commit()

    assert created is True
    prov = (
        db_session.query(QuestionProvenance)
        .filter(QuestionProvenance.document_id == doc.id)
        .first()
    )
    assert prov is not None
    assert prov.page_number == 5

    # 页计数能看到该页已有题
    counts = question_crud.count_questions_per_page(
        db_session, user.id, doc.id, [5, 6]
    )
    assert counts.get(5) == 1
    assert counts.get(6) is None


# ─── DB 集成：用户隔离 ───────────────────────────────

def test_count_questions_per_page_user_isolation(db_session):
    user_a = _make_user(db_session, "cyb-a@example.com", "A")
    user_b = _make_user(db_session, "cyb-b@example.com", "B")
    doc_a = _make_doc(db_session, user_a, "docA")
    _make_doc(db_session, user_b, "docB")

    question_gen_service._persist_question_from_page(
        db_session,
        user_id=user_a.id,
        document=doc_a,
        page=_page(5),
        qdata=_qdata(stem="A 的题目"),
    )
    db_session.commit()

    # A 自己看得到
    counts_a = question_crud.count_questions_per_page(
        db_session, user_a.id, doc_a.id, [5]
    )
    assert counts_a.get(5) == 1
    # B 看不到 A 的题（用户隔离）
    counts_b = question_crud.count_questions_per_page(
        db_session, user_b.id, doc_a.id, [5]
    )
    assert counts_b == {}


# ─── SSE：逐页进度事件 ───────────────────────────────

def test_stream_generate_from_pages_emits_page_events(monkeypatch, db_session):
    user = _make_user(db_session, "cyb-stream@example.com")
    doc = _make_doc(db_session, user)

    class FakeDoc:
        id = doc.id
        display_name = doc.display_name
        zone = "study"
        segment_status = "completed"
        question_gen_status = "not_started"
        global_document_id = None
        collection_id = doc.collection_id

    monkeypatch.setattr(
        question_gen_service.kb_crud,
        "get_document_by_id_or_dify",
        lambda db, uid, did: FakeDoc(),
    )
    monkeypatch.setattr(
        question_gen_service,
        "get_pages_by_numbers",
        lambda db, docobj, nums: [
            _page(n) for n in nums
        ],
    )

    async def fake_generate_one_page(**kwargs):
        pn = kwargs["page_number"]
        if pn == 5:
            return {
                "page_number": 5,
                "status": "completed",
                "questions_created": 1,
                "questions_reused": 0,
                "total_questions": 1,
            }
        return {
            "page_number": pn,
            "status": "failed",
            "questions_created": 0,
            "questions_reused": 0,
            "total_questions": 0,
        }

    monkeypatch.setattr(
        question_gen_service, "_generate_one_page", fake_generate_one_page
    )

    async def _collect():
        events = []
        async for event_name, data in question_gen_service.stream_generate_from_pages(
            user_id=user.id,
            document_id=doc.id,
            page_numbers=[5, 6],
            questions_per_page=1,
            provider=lambda p: [_qdata()],
            token="",
        ):
            events.append((event_name, data["type"], data))
        return events

    events = asyncio.run(_collect())

    types = [t for _, t, _ in events]
    assert types[0] == "page_start"
    assert types[1] == "page_start"
    assert "page_complete" in types
    assert "page_failed" in types
    assert types[-1] == "done"

    done = events[-1][2]
    assert done["document_id"] == doc.id
    assert done["page_numbers"] == [5, 6]
    assert done["total_pages"] == 2
    assert done["questions_created"] == 1
