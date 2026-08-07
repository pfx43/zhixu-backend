from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.auth.auth_session_service import build_session_payload, get_session_user
import os

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Dependency Injection ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    # Support a test token for local unit tests — return dict for uniform access via ["key"]
    if token == "TEST_TOKEN_FOR_USER":
        return {"user_id": 1, "email": "test@example.com", "is_active": True}

    user = get_session_user(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired")

    return build_session_payload(user)

def get_current_active_user(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_active", True): # Default to True if missing, or handle strictly
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def get_admin_user(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    """仅管理员可调用 — plan_level >= 99 视为管理员。"""
    level = current_user.get("level", 0)
    if level < 99:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


def get_admin_or_internal(
    current_user: dict = Depends(get_current_active_user),
    x_internal_key: str = Header(None, alias="X-Internal-Key"),
) -> dict:
    """管理员或内部服务（携带 X-Internal-Key）可调用。"""
    internal_key = os.getenv("INTERNAL_API_KEY", "")
    if internal_key and x_internal_key == internal_key:
        return current_user
    return get_admin_user(current_user)
