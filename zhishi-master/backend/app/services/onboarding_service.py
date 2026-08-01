from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.models.onboarding import OnboardingState


class OnboardingAlreadyInProgress(Exception):
    def __init__(self, latest: Dict[str, Any]):
        self.latest = latest


class OnboardingRevisionConflict(Exception):
    def __init__(self, latest: Dict[str, Any]):
        self.latest = latest


def _default_steps():
    return {"channel": "pending", "upload": "pending", "profile": "pending", "tags": "pending", "help": "pending"}


def serialize_state(state: OnboardingState) -> Dict[str, Any]:
    return {
        "guide_version": int(state.guide_version),
        "revision": int(state.revision),
        "status": state.status,
        "current_step": state.current_step,
        "steps": state.steps or _default_steps(),
        "channel": state.channel_answer,
        "profile": state.profile_answer,
        "tags": state.tags,
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