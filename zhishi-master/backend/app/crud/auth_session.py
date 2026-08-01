from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AuthSession


def add_auth_session(
    db: Session,
    *,
    token_hash: str,
    user_id: int,
    expires_at: datetime,
) -> None:
    db.add(
        AuthSession(
            token_hash=token_hash,
            user_id=user_id,
            expires_at=expires_at,
        )
    )


def get_active_auth_session(
    db: Session,
    *,
    token_hash: str,
    active_after: datetime,
) -> AuthSession | None:
    return db.query(AuthSession).filter(
        AuthSession.token_hash == token_hash,
        AuthSession.expires_at > active_after,
    ).first()


def rotate_auth_session_hash(
    db: Session,
    *,
    old_token_hash: str,
    new_token_hash: str,
    active_after: datetime,
    expires_at: datetime,
) -> int:
    return (
        db.query(AuthSession)
        .filter(
            AuthSession.token_hash == old_token_hash,
            AuthSession.expires_at > active_after,
        )
        .update(
            {
                AuthSession.token_hash: new_token_hash,
                AuthSession.expires_at: expires_at,
                AuthSession.created_at: active_after,
            },
            synchronize_session=False,
        )
    )


def delete_auth_session_record(db: Session, session: AuthSession) -> None:
    db.delete(session)


def delete_auth_session_by_hash(db: Session, token_hash: str) -> int:
    return (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == token_hash)
        .delete(synchronize_session=False)
    )


def delete_auth_sessions_for_user(
    db: Session,
    *,
    user_id: int,
    preserve_token_hash: str | None = None,
) -> int:
    query = db.query(AuthSession).filter(AuthSession.user_id == user_id)
    if preserve_token_hash:
        query = query.filter(AuthSession.token_hash != preserve_token_hash)
    return query.delete(synchronize_session=False)


def delete_expired_auth_sessions(db: Session, expired_at: datetime) -> int:
    return (
        db.query(AuthSession)
        .filter(AuthSession.expires_at <= expired_at)
        .delete(synchronize_session=False)
    )
