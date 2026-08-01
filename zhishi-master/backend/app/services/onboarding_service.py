from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.models.onboarding import OnboardingState


_CHANNEL_CODES = {
    "friend",
    "social_media",
    "search_engine",
    "school_teacher",
    "competition_project",
    "other",
}
_IDENTITY_CODES = {
    "student",
    "professional",
    "researcher",
    "teacher",
    "other",
    "prefer_not_to_say",
}
_USE_PURPOSES = {
    "learning",
    "research",
    "work",
    "competition",
    "knowledge_management",
    "other",
}
_FUNCTION_PREFERENCES = {
    "tina",
    "knowledge_base",
    "graph",
    "practice",
    "analytics",
    "other",
}
_DAILY_USAGE = {
    "less_than_15_minutes",
    "15_30_minutes",
    "30_60_minutes",
    "more_than_60_minutes",
    "unsure",
    "prefer_not_to_say",
}
_TAG_PREFIXES = {"identity", "field", "purpose", "preference"}


class OnboardingAlreadyInProgress(Exception):
    def __init__(self, latest: Dict[str, Any]):
        self.latest = latest


class OnboardingRevisionConflict(Exception):
    def __init__(self, latest: Dict[str, Any]):
        self.latest = latest


def _default_steps():
    return {"channel": "pending", "upload": "pending", "profile": "pending", "tags": "pending", "help": "pending"}


def _channel_for_response(value: Any):
    if not isinstance(value, dict):
        return None
    code = value.get("channel")
    remark = value.get("channel_remark")
    if not isinstance(code, str) or code not in _CHANNEL_CODES:
        return None
    if not isinstance(remark, (str, type(None))):
        return None
    return {"channel": code, "channel_remark": remark}


def _profile_for_response(value: Any):
    if not isinstance(value, dict) or not value:
        return None
    consent = value.get("personalization_consent")
    identity_code = value.get("identity_code")
    identity_other = value.get("identity_other")
    major_field = value.get("major_field")
    use_purposes = value.get("use_purposes") or []
    function_preferences = value.get("function_preferences") or []
    daily_usage = value.get("daily_usage")
    if not isinstance(consent, bool):
        return None
    if identity_code is not None and (
        not isinstance(identity_code, str) or identity_code not in _IDENTITY_CODES
    ):
        return None
    if not isinstance(identity_other, (str, type(None))):
        return None
    if not isinstance(major_field, (str, type(None))):
        return None
    if not isinstance(use_purposes, list) or any(
        not isinstance(item, str) or item not in _USE_PURPOSES
        for item in use_purposes
    ):
        return None
    if not isinstance(function_preferences, list) or any(
        not isinstance(item, str) or item not in _FUNCTION_PREFERENCES
        for item in function_preferences
    ):
        return None
    if daily_usage is not None and (
        not isinstance(daily_usage, str) or daily_usage not in _DAILY_USAGE
    ):
        return None
    return {
        "identity_code": identity_code,
        "identity_other": identity_other,
        "major_field": major_field,
        "use_purposes": use_purposes,
        "function_preferences": function_preferences,
        "daily_usage": daily_usage,
        "personalization_consent": consent,
    }


def _tags_for_response(value: Any):
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            return []
        tag_id = item.get("id")
        name = item.get("name")
        if not isinstance(tag_id, str) or not isinstance(name, str):
            return []
        if tag_id.split("-", 1)[0] not in _TAG_PREFIXES:
            return []
        result.append({"id": tag_id, "name": name})
    return result


def serialize_state(state: OnboardingState) -> Dict[str, Any]:
    return {
        "guide_version": int(state.guide_version),
        "revision": int(state.revision),
        "status": state.status,
        "current_step": state.current_step,
        "steps": state.steps or _default_steps(),
        "channel": _channel_for_response(state.channel_answer),
        "profile": _profile_for_response(state.profile_answer),
        "tags": _tags_for_response(state.tags),
    }


def _flag_state_dirty(state: OnboardingState):
    """Mark JSON columns as modified so SQLAlchemy includes them in UPDATE."""
    flag_modified(state, "steps")
    flag_modified(state, "channel_answer")
    flag_modified(state, "profile_answer")
    flag_modified(state, "tags")


def restart_onboarding(db: Session, user_id: int, expected_revision: int, mode: str, preserve_answers: bool) -> Dict[str, Any]:
    # lock row for update to ensure atomicity (Postgres)
    state = db.query(OnboardingState).filter_by(user_id=user_id).with_for_update(nowait=False).one_or_none()
    created_new = False
    if state is None:
        # create initial record if not exists
        state = OnboardingState(
            user_id=user_id,
            guide_version=1,
            revision=0,
            status="pending",
            current_step=None,
            steps=_default_steps(),
            channel_answer=None,
            profile_answer=None,
            tags=None,
        )
        db.add(state)
        db.flush()  # get id
        created_new = True

    if state.status == "in_progress":
        raise OnboardingAlreadyInProgress(latest=serialize_state(state))

    # If we just created the state record for this user, skip revision conflict
    # check so old accounts without prior onboarding can reset without matching a
    # nonexistent revision.
    if not created_new and expected_revision != int(state.revision):
        raise OnboardingRevisionConflict(latest=serialize_state(state))

    # perform reset in same transaction
    state.status = "in_progress"
    state.current_step = "channel"
    state.steps = _default_steps()
    _flag_state_dirty(state)
    state.revision = int(state.revision) + 1
    db.add(state)
    db.flush()
    return serialize_state(state)


def get_onboarding_state(db: Session, user_id: int) -> Dict[str, Any]:
    state = db.query(OnboardingState).filter_by(user_id=user_id).one_or_none()
    if state is None:
        # Do NOT auto-create for legacy users; return marker for legacy_without_state
        return {"should_show": False, "reason": "legacy_without_state", "state": None}

    # decide should_show: only when in_progress or pending (new) should show
    should_show = state.status in ("in_progress", "pending")
    reason = state.status if state.status else "unknown"
    return {"should_show": should_show, "reason": reason, "state": serialize_state(state)}


def submit_onboarding_step(db: Session, user_id: int, expected_revision: int, step: str, action: str, answer: Dict[str, Any]) -> Dict[str, Any]:
    state = db.query(OnboardingState).filter_by(user_id=user_id).with_for_update(nowait=False).one_or_none()
    if state is None:
        raise OnboardingRevisionConflict(latest={})

    if expected_revision != int(state.revision):
        raise OnboardingRevisionConflict(latest=serialize_state(state))

    # Accept actions: completed, skipped
    if action not in ("completed", "skipped"):
        raise ValueError("unsupported action")

    # update step status
    steps = state.steps or _default_steps()
    if step not in steps:
        raise ValueError("unknown step")

    steps[step] = "completed" if action == "completed" else "skipped"

    # persist answers for known steps
    if step == "channel":
        state.channel_answer = answer
    elif step == "profile":
        state.profile_answer = answer
    elif step == "tags":
        state.tags = answer.get("tags") if isinstance(answer, dict) and "tags" in answer else state.tags

    # advance current_step to next pending
    next_step = None
    order = ["channel", "upload", "profile", "tags", "help"]
    for s in order:
        if steps.get(s) in ("pending", None):
            next_step = s
            break

    state.steps = steps
    _flag_state_dirty(state)
    state.current_step = next_step
    # if no pending remain, mark completed
    if all(v in ("completed", "skipped") for v in steps.values()):
        state.status = "completed"

    state.revision = int(state.revision) + 1
    db.add(state)
    db.flush()
    return serialize_state(state)


def complete_onboarding(db: Session, user_id: int, expected_revision: int, action: str) -> Dict[str, Any]:
    state = db.query(OnboardingState).filter_by(user_id=user_id).with_for_update(nowait=False).one_or_none()
    if state is None:
        raise OnboardingRevisionConflict(latest={})

    if expected_revision != int(state.revision):
        raise OnboardingRevisionConflict(latest=serialize_state(state))

    if action == "completed":
        # only mark completed if all steps handled
        steps = state.steps or _default_steps()
        if not all(v in ("completed", "skipped") for v in steps.values()):
            raise ValueError("cannot complete: not all steps processed")
        state.status = "completed"
        _flag_state_dirty(state)
    elif action == "skip_remaining":
        steps = state.steps or _default_steps()
        for k, v in steps.items():
            if v == "pending":
                steps[k] = "skipped"
        state.steps = steps
        _flag_state_dirty(state)
        state.status = "skipped"
    else:
        raise ValueError("unknown action")

    state.revision = int(state.revision) + 1
    db.add(state)
    db.flush()
    return serialize_state(state)
