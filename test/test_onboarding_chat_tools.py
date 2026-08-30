"""引导对话工具：按登录 user_id 隔离，并弹出目标确认卡 / 上传卡。"""
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pgutil import make_sessionmaker
from app.models import Goal, User
from app.models.onboarding import OnboardingState
from app.services.onboarding.chat_cards import (
    cards_shown_from_history,
    persistable_cards,
    user_confirmed_goal_from_history,
)
from app.services.tools.onboarding_tools import OnboardingTools


def _seed_user(session, user_id: int, email: str, nickname: str = "用户"):
    session.add(User(
        id=user_id,
        email=email,
        password_hash="hashed",
        nickname=nickname,
        is_active=True,
    ))
    session.commit()


@pytest.fixture()
def onboard_env(monkeypatch):
    engine, SessionLocal = make_sessionmaker()

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

    monkeypatch.setattr("app.services.tools.onboarding_tools.short_session", _short)
    monkeypatch.setattr("app.services.onboarding.chat_cards.short_session", _short)

    with SessionLocal() as s:
        _seed_user(s, 8801, "a@example.com", "Alice")
        _seed_user(s, 8802, "b@example.com", "Bob")

    yield SessionLocal
    engine.dispose()


def test_requires_user_id():
    with pytest.raises(ValueError):
        OnboardingTools(user_id=0)


def test_name_and_goal_isolated(onboard_env):
    SessionLocal = onboard_env
    a = OnboardingTools(user_id=8801)
    b = OnboardingTools(user_id=8802)

    assert "已记住名字" in a.save_name("啊噗")
    assert "目标已写入" in a.confirm_learning_goal("两周内把高数第一章刷完")

    with SessionLocal() as db:
        alice = db.query(User).filter(User.id == 8801).one()
        bob = db.query(User).filter(User.id == 8802).one()
        assert alice.nickname == "啊噗"
        assert bob.nickname == "Bob"
        goals_a = db.query(Goal).filter(Goal.user_id == 8801, Goal.status == "active").all()
        goals_b = db.query(Goal).filter(Goal.user_id == 8802, Goal.status == "active").all()
        assert len(goals_a) == 1
        assert goals_a[0].text == "两周内把高数第一章刷完"
        assert goals_b == []

    items = a.drain_ui()
    types = [i["type"] for i in items]
    assert "goal_card" in types
    assert next(i["goal"] for i in items if i["type"] == "goal_card") == "两周内把高数第一章刷完"
    assert b.drain_ui() == []


def test_docs_card_waits_for_confirm(onboard_env):
    first = OnboardingTools(user_id=8801)
    first.confirm_learning_goal("考研上岸")
    first.drain_ui()
    waiting = OnboardingTools(
        user_id=8801,
        shown_cards={"goal_card"},
        goal_confirmed=False,
    )
    assert "还没点确认" in waiting.offer_add_document()
    assert waiting.drain_ui() == []

    confirmed = OnboardingTools(
        user_id=8801,
        shown_cards={"goal_card"},
        goal_confirmed=True,
    )
    assert "已弹出添加资料卡片" in confirmed.offer_add_document()
    types = [i["type"] for i in confirmed.drain_ui()]
    assert "docs_card" in types


def test_complete_only_current_user(onboard_env):
    SessionLocal = onboard_env
    a = OnboardingTools(user_id=8801)
    b = OnboardingTools(user_id=8802)
    a.complete_onboarding()
    types = [i["type"] for i in a.drain_ui()]
    assert "done" in types

    with SessionLocal() as db:
        state_a = db.query(OnboardingState).filter_by(user_id=8801).one()
        state_b = db.query(OnboardingState).filter_by(user_id=8802).one_or_none()
        assert state_a.status == "completed"
        assert state_b is None


def test_same_goal_does_not_repeat_card(onboard_env):
    a = OnboardingTools(user_id=8801)
    a.confirm_learning_goal("考研上岸")
    a.drain_ui()
    again = a.confirm_learning_goal("考研上岸")
    assert "已经弹过" in again
    assert a.drain_ui() == []


def test_history_helpers_do_not_cross_user_payload():
    history_a = [
        {"role": "assistant", "content": "", "payload": {"onboarding": [{"type": "goal_card", "goal": "A"}]}},
        {"role": "user", "content": "我确认这个目标，就是这个。"},
    ]
    history_b = [
        {"role": "assistant", "content": "", "payload": {"onboarding": [{"type": "docs_card"}]}},
    ]
    assert cards_shown_from_history(history_a) == {"goal_card"}
    assert cards_shown_from_history(history_b) == {"docs_card"}
    assert user_confirmed_goal_from_history(history_a) is True
    assert user_confirmed_goal_from_history(history_b) is False
    assert persistable_cards([{"type": "rail", "id": "meet"}, {"type": "goal_card", "goal": "A"}]) == [
        {"type": "goal_card", "goal": "A"}
    ]
