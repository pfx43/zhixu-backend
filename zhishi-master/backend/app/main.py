from fastapi import FastAPI, Depends
from app.core.database import init_db
from app.api.v1.router import api_router
from app.api.deps import get_db
from app.crud import get_user_with_plan_details_v2
from sqlalchemy.orm import Session
import logging

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- App ---
app = FastAPI(title="Zhishi Backend")

# 延迟初始化数据库到启动事件
@app.on_event("startup")
async def startup_event():
    try:
        init_db()
        logger.info("✅ 数据库初始化成功")
    except Exception as e:
        logger.error(f"⚠️  数据库初始化失败: {str(e)}")
        logger.error("请确保 MySQL 已启动，并且数据库凭证正确")

# Include Routers
app.include_router(api_router, prefix="/api/v1") # Include v1 routers

# --- Extra Routes (Test) ---
# These were in login1.py, keeping for compatibility if needed or move to tests
@app.get("/test-plan-query/{user_id}") 
async def test_plan_query(user_id: int, db: Session = Depends(get_db)): 
    return get_user_with_plan_details_v2(db, user_id)
