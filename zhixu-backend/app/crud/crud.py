from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import User, PlanTier
from app.schemas import UserWithPlan
from datetime import datetime, timedelta, timezone

def get_user_by_email(db: Session, email: str):
    """根据邮箱获取用户"""
    return db.query(User).filter(User.email == email).first()

def get_user_by_phone(db: Session, phone: str):
    """根据手机号获取用户"""
    return db.query(User).filter(User.phone == phone).first()

def get_user_by_id(db: Session, user_id: int):
    """根据ID获取用户"""
    return db.query(User).filter(User.id == user_id).first()


def delete_user_by_id(db: Session, user_id: int):
    """删除用户账号"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True

# 🔥 新增：获取用户完整信息（包含套餐详情）
def get_user_with_plan_details_v2(db: Session, user_id: int):
    """获取用户信息及套餐详情"""
    # 使用原生SQL查询，关联users和plan_tiers表
    # MySQL syntax for date difference
    query = text("""
    SELECT 
        u.*, 
        p.name as plan_name, 
        p.price_monthly, 
        p.price_yearly, 
        CAST(julianday(u.expires_at) - julianday('now') AS INTEGER) as days_remaining 
    FROM users u 
    LEFT JOIN plan_tiers p ON u.plan_level = p.level 
    WHERE u.id = :user_id
    """)
    
    result = db.execute(query, {"user_id": user_id}).fetchone()
    return dict(result._mapping) if result else None

# 🔥 新增：检查用户API配额
def check_api_quota(db: Session, user_id: int) -> bool:
    """检查用户是否还有API调用额度"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        return False
    
    # 检查套餐是否过期
    if user.expires_at and user.expires_at < datetime.now(timezone.utc):
        return False
    
    # 这里可以添加更复杂的用量统计逻辑
    # 比如查询当天的API调用次数是否超过限制
    
    return True

# 🔥 新增：获取所有套餐列表
def get_all_plans(db: Session):
    """获取所有套餐信息"""
    return db.query(PlanTier).order_by(PlanTier.level).all()

# 🔥 新增：升级用户套餐
def upgrade_user_plan(db: Session, user_id: int, new_plan_level: int, months: int = 1):
    """升级用户套餐"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    
    plan = db.query(PlanTier).filter(PlanTier.level == new_plan_level).first()
    if not plan:
        return None
    
    # 更新用户套餐信息
    user.plan_level = new_plan_level
    user.api_limit_daily = plan.api_limit_daily
    user.token_limit_monthly = plan.token_limit_monthly
    user.knowledge_base_limit = plan.knowledge_base_limit
    user.model_access = plan.model_access
    user.concurrent_limit = plan.concurrent_limit
    
    # 设置过期时间（当前时间 + months个月）
    if user.expires_at and user.expires_at > datetime.now(timezone.utc):
        # 如果已有套餐，在原有基础上延长
        user.expires_at = user.expires_at + timedelta(days=30 * months)
    else:
        # 如果是新套餐，从当前时间开始
        user.expires_at = datetime.now(timezone.utc) + timedelta(days=30 * months)
    
    db.commit()
    db.refresh(user)
    return user
