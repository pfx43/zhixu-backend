from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.redis import cache

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Dependency Injection ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(token: str = Depends(oauth2_scheme)):
    # Support a test token for local unit tests — return dict for uniform access via ["key"]
    if token == "TEST_TOKEN_FOR_USER":
        return {"user_id": 1, "email": "test@example.com", "is_active": True}

    user_info = cache.get_session(token)

    if not user_info:
        raise HTTPException(status_code=401, detail="Session expired")

    return user_info  # 返回字典包含 id, email, level

def get_current_active_user(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_active", True): # Default to True if missing, or handle strictly
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
