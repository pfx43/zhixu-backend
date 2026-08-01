import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import app.crud as crud
import app.crud.auth_session as auth_session_crud
from app.models import AuthSession, User


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_auth_session(
    db: Session,
    *,
    token: str,
    user_id: int,
    ttl_seconds: int,
) -> None:
    now = _utc_now()
    auth_session_crud.delete_expired_auth_sessions(db, now)
    auth_session_crud.add_auth_session(
        db,
        token_hash=hash_token(token),
        user_id=user_id,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )


def get_session_user(db: Session, token: str) -> User | None:
    session = get_auth_session(db, token)
    if session is None:
        return None
    return crud.get_user_by_id(db, session.user_id)


def get_auth_session(
    db: Session,
    token: str,
) -> AuthSession | None:
    return auth_session_crud.get_active_auth_session(
        db,
        token_hash=hash_token(token),
        active_after=_utc_now(),
    )


def rotate_auth_session(
    db: Session,
    *,
    old_token: str,
    new_token: str,
    ttl_seconds: int,
) -> User | None:
    session = get_auth_session(db, old_token)
    if session is None:
        return None
    user = crud.get_user_by_id(db, session.user_id)
    if user is None or not user.is_active:
        auth_session_crud.delete_auth_session_record(db, session)
        return None

    now = _utc_now()
    rotated = auth_session_crud.rotate_auth_session_hash(
        db,
        old_token_hash=hash_token(old_token),
        new_token_hash=hash_token(new_token),
        active_after=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    return user if rotated == 1 else None


def delete_auth_session(db: Session, token: str) -> int:
    return auth_session_crud.delete_auth_session_by_hash(db, hash_token(token))


def delete_user_auth_sessions(
    db: Session,
    user_id: int,
    *,
    preserve_token: str | None = None,
) -> int:
    return auth_session_crud.delete_auth_sessions_for_user(
        db,
        user_id=user_id,
        preserve_token_hash=hash_token(preserve_token) if preserve_token else None,
    )


def build_session_payload(user: User) -> dict:
    return {
        "user_id": user.id,
        "email": user.email,
        "nickname": user.nickname,
        "level": user.plan_level,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "dataset_id": user.dataset_id,
        "user_hash": user.user_hash,
        "api_limit_daily": user.api_limit_daily,
        "token_limit_monthly": user.token_limit_monthly,
        "knowledge_base_limit": user.knowledge_base_limit,
        "model_access": user.model_access,
        "concurrent_limit": user.concurrent_limit,
    }
