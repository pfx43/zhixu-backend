"""从当前用户自己的会话历史里读引导卡片，不跨用户。"""
from typing import Any, Dict, Iterable, List, Optional, Set

from app.core.database import short_session
from app.models import Goal, User
from app.models.onboarding import OnboardingState


CARD_TYPES = {"goal_card", "docs_card", "done"}
CONFIRM_PHRASES = ("确认这个目标", "确认，就是这个")
CHANGE_PHRASES = ("还想改一下",)
SKIP_OR_UPLOAD_PHRASES = ("先跳过资料", "已经上传了资料")


def _onboarding_items(message: Dict[str, Any]) -> List[dict]:
    payload = message.get("payload") or {}
    if not isinstance(payload, dict):
        return []
    items = payload.get("onboarding") or []
    return [item for item in items if isinstance(item, dict)]


def cards_shown_from_history(history: Optional[Iterable[dict]]) -> Set[str]:
    types: Set[str] = set()
    for message in history or []:
        for item in _onboarding_items(message):
            kind = item.get("type")
            if kind:
                types.add(str(kind))
    return types


def persistable_cards(items: Iterable[dict]) -> List[dict]:
    cards = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") in CARD_TYPES:
            cards.append(item)
    return cards


def user_confirmed_goal_from_history(
    history: Optional[Iterable[dict]],
    current: str = "",
) -> bool:
    """用户点过「确认，就是这个」之后为 True；刚说「还想改一下」则 False。"""
    texts: List[str] = []
    for message in history or []:
        if message.get("role") == "user":
            texts.append(message.get("content") or "")
    if current:
        texts.append(current)
    for text in reversed(texts[-20:]):
        if any(p in text for p in CHANGE_PHRASES):
            return False
        if any(p in text for p in CONFIRM_PHRASES):
            return True
    return False


def is_skip_or_uploaded(text: str) -> bool:
    return any(p in (text or "") for p in SKIP_OR_UPLOAD_PHRASES)


def build_onboarding_context(
    user_id: int,
    shown_cards: Optional[Set[str]] = None,
    goal_confirmed: bool = False,
) -> str:
    """只读当前登录用户的称呼/目标/引导状态，给引导 prompt 用。"""
    shown = shown_cards or set()
    with short_session() as db:
        user = db.query(User).filter(User.id == user_id).one_or_none()
        goal = (
            db.query(Goal)
            .filter(Goal.user_id == user_id, Goal.status == "active")
            .order_by(Goal.created_at.desc())
            .first()
        )
        state = db.query(OnboardingState).filter_by(user_id=user_id).one_or_none()
    nickname = (user.nickname if user else "") or "还不知道"
    role = (user.signature if user else "") or "还不知道"
    goal_text = (goal.text if goal else "") or "还没有"
    status = (state.status if state else "pending") or "pending"
    goal_note = "（确认卡已经弹过，不要再调 confirm_learning_goal，除非用户改了目标）" if "goal_card" in shown else ""
    docs_note = "已经弹过，不要再调 offer_add_document" if "docs_card" in shown else "还没弹"
    confirmed = "是" if goal_confirmed else "否"
    return (
        f"- 称呼：{nickname}\n"
        f"- 身份：{role}\n"
        f"- 学习目标：{goal_text}{goal_note}\n"
        f"- 引导状态：{status}\n"
        f"- 资料卡：{docs_note}\n"
        f"- 用户是否已确认目标：{confirmed}"
    )
