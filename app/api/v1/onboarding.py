from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Literal, Optional, Dict, Any, List
from app.api.deps import get_db, get_current_active_user
from app.schemas.onboarding import (
    OnboardingChannelCode,
    OnboardingDailyUsage,
    OnboardingFunctionPreference,
    OnboardingIdentityCode,
    OnboardingUsePurpose,
)
from app.services.onboarding.onboarding_service import restart_onboarding, OnboardingAlreadyInProgress, OnboardingRevisionConflict
from app.services.onboarding.onboarding_service import get_onboarding_state, submit_onboarding_step, complete_onboarding

router = APIRouter(tags=["引导"])

class OnboardingRestartIn(BaseModel):
    expected_revision: int
    mode: Literal["all"]
    preserve_answers: bool

class ChannelOut(BaseModel):
    channel: OnboardingChannelCode
    channel_remark: Optional[str] = None

class ProfileOut(BaseModel):
    identity_code: Optional[OnboardingIdentityCode] = None
    identity_other: Optional[str] = None
    major_field: Optional[str] = None
    use_purposes: List[OnboardingUsePurpose]
    function_preferences: List[OnboardingFunctionPreference]
    daily_usage: Optional[OnboardingDailyUsage] = None
    personalization_consent: bool

class TagOut(BaseModel):
    id: str
    name: str

class OnboardingStateOut(BaseModel):
    guide_version: int
    revision: int
    status: str
    current_step: Optional[str] = None
    steps: Dict[str, str]
    channel: Optional[ChannelOut] = None
    profile: Optional[ProfileOut] = None
    tags: List[TagOut]


class OnboardingStateWrapper(BaseModel):
    should_show: bool
    reason: str
    state: Optional[OnboardingStateOut] = None


class OnboardingStepIn(BaseModel):
    expected_revision: int
    step: str
    action: Literal["completed", "skipped"]
    answer: Optional[Dict[str, Any]] = None


class OnboardingCompleteIn(BaseModel):
    expected_revision: int
    action: Literal["completed", "skip_remaining"]


@router.post("/restart", response_model=OnboardingStateOut)
def onboarding_restart(payload: OnboardingRestartIn, db: Session = Depends(get_db), current_user: dict = Depends(get_current_active_user)):
    try:
        state = restart_onboarding(db, current_user["user_id"], payload.expected_revision, payload.mode, payload.preserve_answers)
        db.commit()
        return state
    except OnboardingAlreadyInProgress as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "onboarding_already_in_progress", "message": "账号已经重新进入引导。", "latest": e.latest},
        )
    except OnboardingRevisionConflict as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "onboarding_revision_conflict", "message": "引导进度已在其他设备更新。", "latest": e.latest},
        )
    except Exception:
        db.rollback()
        raise


@router.get("/state", response_model=OnboardingStateWrapper)
def onboarding_state(db: Session = Depends(get_db), current_user: dict = Depends(get_current_active_user)):
    return get_onboarding_state(db, current_user["user_id"])


@router.post("/step", response_model=OnboardingStateOut)
def onboarding_step(payload: OnboardingStepIn, db: Session = Depends(get_db), current_user: dict = Depends(get_current_active_user)):
    try:
        state = submit_onboarding_step(db, current_user["user_id"], payload.expected_revision, payload.step, payload.action, payload.answer or {})
        db.commit()
        return state
    except OnboardingRevisionConflict as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "onboarding_revision_conflict", "latest": e.latest})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception:
        db.rollback()
        raise


@router.post("/complete", response_model=OnboardingStateOut)
def onboarding_complete(payload: OnboardingCompleteIn, db: Session = Depends(get_db), current_user: dict = Depends(get_current_active_user)):
    try:
        state = complete_onboarding(db, current_user["user_id"], payload.expected_revision, payload.action)
        db.commit()
        return state
    except OnboardingRevisionConflict as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "onboarding_revision_conflict", "latest": e.latest})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception:
        db.rollback()
        raise
