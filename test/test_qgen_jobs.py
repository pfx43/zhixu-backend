"""出题作业：入队快照、complete 入库、一页失败不影响其它页、TCN 词表。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import (
    Document,
    GlobalQuestion,
    KbCollection,
    QuestionProvenance,
    User,
    UserQuestionRef,
)
from app.models.qgen import QgenJob
from app.qgen.tcn_tags import build_tag_hint, tag_names_for_domain
from app.services.quiz import qgen_job_service
from app.services.quiz.question_normalize import normalize_question
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


def _make_user(db, email: str) -> User:
    user = User(email=email, password_hash="hash", nickname="用户", is_active=True)
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
        question_gen_status="not_started",
    )
    db.add(doc)
    db.flush()
    return doc


def _page(num: int) -> dict:
    return {
        "page_number": num,
        "title": f"第 {num} 页",
        "content": f"第 {num} 页正文。",
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
        "explanation": "见原文",
        "tags": ["极限"],
        "reference_text": "第 1 页正文。",
    }


def _patch_pages(monkeypatch, pages):
    monkeypatch.setattr(
        "app.services.quiz.qgen_job_service.get_pages_by_numbers",
        lambda db, doc, nums: [p for p in pages if p["page_number"] in nums],
    )
    by_num = {p["page_number"]: p for p in pages}

    def _near(db, doc, page_numbers, max_near_lookups=3):
        lo, hi = min(page_numbers), max(page_numbers)
        near = {}
        allowed = set()
        for num in range(lo - 1, hi + 2):
            if num in by_num:
                near[num] = by_num[num]
                allowed.add(num)
        return near, allowed

    monkeypatch.setattr(
        "app.services.quiz.qgen_job_service.build_near_page_context", _near
    )


def test_normalize_lives_outside_gen_service():
    q = normalize_question(_qdata())
    assert q["answer"] == "A"
    assert q["question_type"] == "single_choice"


def test_enqueue_claim_complete_persists(db_session, monkeypatch):
    user = _make_user(db_session, "qgen1@example.com")
    doc = _make_doc(db_session, user)
    _patch_pages(monkeypatch, [_page(1), _page(2)])

    resp = qgen_job_service.enqueue_generate_from_pages(
        db_session, user.id, doc.id, [1, 2], questions_per_page=1
    )
    db_session.commit()
    assert resp.job_id
    assert resp.question_gen_status == "processing"

    claimed = qgen_job_service.claim_next_job(db_session)
    db_session.commit()
    assert claimed["job_id"] == resp.job_id
    assert claimed["user_id"] == user.id
    assert len(claimed["pages"]) == 2

    result = qgen_job_service.complete_page(
        db_session, claimed["job_id"], 1, [_qdata("第一页的题？")]
    )
    db_session.commit()
    assert result["status"] == "completed"
    assert result["total_questions"] == 1

    qgen_job_service.fail_page(db_session, claimed["job_id"], 2, "llm_timeout")
    db_session.commit()

    job = db_session.query(QgenJob).filter(QgenJob.id == claimed["job_id"]).one()
    assert job.status == "completed"
    pages = {p.page_number: p.status for p in job.pages}
    assert pages[1] == "completed"
    assert pages[2] == "failed"

    assert db_session.query(GlobalQuestion).count() == 1
    assert db_session.query(UserQuestionRef).filter(UserQuestionRef.user_id == user.id).count() == 1
    prov = db_session.query(QuestionProvenance).one()
    assert prov.page_number == 1


def test_claim_skips_user_already_running(db_session, monkeypatch):
    user = _make_user(db_session, "qgen2@example.com")
    other = _make_user(db_session, "qgen3@example.com")
    doc_a = _make_doc(db_session, user, "A")
    doc_b = _make_doc(db_session, user, "B")
    doc_c = _make_doc(db_session, other, "C")
    _patch_pages(monkeypatch, [_page(1)])

    first = qgen_job_service.enqueue_generate_from_pages(db_session, user.id, doc_a.id, [1])
    second = qgen_job_service.enqueue_generate_from_pages(db_session, user.id, doc_b.id, [1])
    third = qgen_job_service.enqueue_generate_from_pages(db_session, other.id, doc_c.id, [1])
    db_session.commit()

    claimed_first = qgen_job_service.claim_next_job(db_session)
    db_session.commit()
    assert claimed_first["job_id"] == first.job_id

    claimed_other = qgen_job_service.claim_next_job(db_session)
    db_session.commit()
    assert claimed_other["job_id"] == third.job_id

    claimed_none = qgen_job_service.claim_next_job(db_session)
    assert claimed_none is None
    leftover = db_session.query(QgenJob).filter(QgenJob.id == second.job_id).one()
    assert leftover.status == "queued"


def test_get_job_is_user_scoped(db_session, monkeypatch):
    owner = _make_user(db_session, "qgen4@example.com")
    other = _make_user(db_session, "qgen5@example.com")
    doc = _make_doc(db_session, owner)
    _patch_pages(monkeypatch, [_page(1)])
    resp = qgen_job_service.enqueue_generate_from_pages(db_session, owner.id, doc.id, [1])
    db_session.commit()

    public = qgen_job_service.get_job_for_user(db_session, owner.id, resp.job_id)
    assert public["job_id"] == resp.job_id

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        qgen_job_service.get_job_for_user(db_session, other.id, resp.job_id)
    assert exc.value.status_code == 404


def test_tcn_domain_copied_onto_job(db_session, monkeypatch):
    user = _make_user(db_session, "qgen6@example.com")
    doc = _make_doc(db_session, user)
    doc.tcn_domain = "higher_math"
    _patch_pages(monkeypatch, [_page(1)])
    resp = qgen_job_service.enqueue_generate_from_pages(db_session, user.id, doc.id, [1])
    db_session.commit()
    job = db_session.query(QgenJob).filter(QgenJob.id == resp.job_id).one()
    assert job.tcn_domain == "higher_math"


def test_max_agents_not_tied_to_page_checkbox_limit():
    from app.core.config import QUESTION_GEN_MAX_AGENTS
    from app.qgen.settings import max_agents

    n = max_agents()
    assert n == QUESTION_GEN_MAX_AGENTS
    assert n >= 1


def test_enqueue_keeps_all_selected_pages(db_session, monkeypatch):
    user = _make_user(db_session, "qgen-many@example.com")
    doc = _make_doc(db_session, user)
    pages = [_page(i) for i in range(1, 13)]
    _patch_pages(monkeypatch, pages)
    nums = list(range(1, 13))
    resp = qgen_job_service.enqueue_generate_from_pages(
        db_session, user.id, doc.id, nums
    )
    db_session.commit()
    job = db_session.query(QgenJob).filter(QgenJob.id == resp.job_id).one()
    assert [p.page_number for p in job.pages] == nums
    assert resp.page_numbers == nums


def test_tcn_tag_names_lock_hint_when_domain_set():
    names = tag_names_for_domain("higher_math")
    assert "夹逼准则" in "、".join(names) or any("夹逼" in n for n in names)
    hint = build_tag_hint("已有 tag：随便编", "higher_math")
    assert "必须从下列名单中选择" in hint
    assert "随便编" not in hint
    assert build_tag_hint("已有 tag：极限", None) == "已有 tag：极限"
    assert tag_names_for_domain("not_a_domain") == []
