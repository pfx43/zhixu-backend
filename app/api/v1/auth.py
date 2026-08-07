from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import timedelta, datetime, timezone

from app.api.deps import get_db, get_current_active_user, get_admin_or_internal, oauth2_scheme
from app.core.security import get_password_hash, verify_password
from app.models import User, PlanTier
from app.schemas import (
    UserCreate, UserRegistrationResponse, Token, UserResponse, UserWithPlan,
    UpgradeRequest, SendVerificationRequest, SendVerificationResponse,
    VerifyEmailRequest, VerifyEmailResponse, RefreshTokenRequest, RefreshTokenResponse,
    ChangePasswordRequest, ChangePasswordResponse, LogoutResponse, DeleteAccountResponse,
    SendPasswordResetRequest, SendPasswordResetResponse,
    ResetPasswordRequest, ResetPasswordResponse,
    UpdateProfileRequest
)
from app.services.auth.auth_service import AuthManager
import app.crud as crud
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=UserRegistrationResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    try:
        return AuthManager.register(
            db=db,
            email=user.email,
            password=user.password,
            nickname=user.nickname,
            username=user.username,
            verification_code=user.verification_code,
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"注册过程中发生异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")

@router.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """登录 — username 字段可传邮箱或手机号，验证码通过 verification_code 字段传入"""
    param = form_data.username
    email = ""
    phone = ""
    if "@" in param:
        email = param
    else:
        phone = param
    return AuthManager.login(
        db=db,
        email=email,
        phone=phone,
        password=form_data.password
    )

@router.post("/refresh-token", response_model=RefreshTokenResponse)
def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    刷新 Token
    
    使用旧的有效 Token 获取新的 Token（延长会话时间）。
    
    **使用场景：**
    - Token 即将过期时调用此接口
    - 获得新 Token 后使用新 Token 替换旧 Token
    - 旧 Token 将被自动删除
    
    **请求：**
    ```json
    {
        "refresh_token": "你的旧token"
    }
    ```
    
    **响应：**
    ```json
    {
        "access_token": "新的token",
        "token_type": "bearer",
        "expires_in": 604800,
        "message": "Token 刷新成功"
    }
    ```
    """
    try:
        return AuthManager.refresh_token(db, request.refresh_token)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Token 刷新失败: {str(e)}")
        raise HTTPException(status_code=500, detail="Token 刷新失败，请重新登录")

@router.get("/users/me", response_model=UserResponse) 
def read_users_me(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取当前用户信息，包含套餐详情"""
    plan_config = db.query(PlanTier).filter(
        PlanTier.level == current_user["level"]
    ).first()
    
    # 套餐和资料可能在会话创建后变化，此接口始终读取最新用户记录。
    db_user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    days_remaining = None
    if db_user.expires_at:
        delta = db_user.expires_at - datetime.now(timezone.utc)
        days_remaining = delta.days if delta.days > 0 else 0
    
    return {
        "id": db_user.id,
        "email": db_user.email,
        "phone": db_user.phone,
        "nickname": db_user.nickname,
        "gender": db_user.gender,
        "signature": db_user.signature,
        "tags": db_user.tags,
        "username": db_user.username,
        "is_active": db_user.is_active,
        "created_at": db_user.created_at,
        "plan_info": {
            "level": db_user.plan_level,
            "name": plan_config.name if plan_config else "未知套餐",
            "daily_api_limit": db_user.api_limit_daily,
            "monthly_token_limit": db_user.token_limit_monthly,
            "kb_limit": db_user.knowledge_base_limit,
            "available_models": db_user.model_access.split(',') if db_user.model_access else [],
            "concurrent_limit": db_user.concurrent_limit,
            "expires_at": db_user.expires_at,
            "days_remaining": days_remaining
        }
    }

@router.get("/users/me/plan", response_model=UserWithPlan)
def get_my_plan_details(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取当前用户的完整套餐信息"""
    user_data = crud.get_user_with_plan_details_v2(db, current_user["user_id"])
    if not user_data:
        raise HTTPException(status_code=404, detail="用户未找到")
    
    return user_data

@router.get("/users/me/quota")
def check_my_quota(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """检查当前用户的API配额状态"""
    has_quota = crud.check_api_quota(db, current_user["user_id"])
    
    user_data = crud.get_user_with_plan_details_v2(db, current_user["user_id"])
    
    if not user_data:
        raise HTTPException(status_code=404, detail="用户数据异常")

    return {
        "has_quota": has_quota,
        "plan_level": user_data.get("plan_level"),
        "plan_name": user_data.get("plan_name"),
        "api_limit_daily": user_data.get("api_limit_daily"),
        "expires_at": user_data.get("expires_at"),
        "days_remaining": user_data.get("days_remaining")
    }

@router.post("/users/me/upgrade-plan")
def upgrade_my_plan(
    request: UpgradeRequest,
    current_user: dict = Depends(get_admin_or_internal),
    db: Session = Depends(get_db)
):
    """管理员升级用户套餐（需管理员权限或 X-Internal-Key）"""
    upgraded_user = crud.upgrade_user_plan(db, current_user["user_id"], request.plan_level, request.months)
    if not upgraded_user:
        raise HTTPException(status_code=400, detail="套餐升级失败")
    
    return {"message": "套餐升级成功", "new_plan_level": request.plan_level}

@router.get("/test-token-info")
def get_test_info(current_user: dict = Depends(get_current_active_user)):
    return {
        "status": "验证成功",
        "message": f"欢迎回来，{current_user['email']}！",
        "server_time": datetime.now(timezone.utc),
        "your_user_id": current_user["user_id"],
        "hint": "如果你能看到这条消息，说明持久化 Token 会话可用。",
    }


# ============ 邮箱验证相关路由 ============

@router.post("/send-verification", response_model=SendVerificationResponse)
def send_verification(
    request: SendVerificationRequest,
    db: Session = Depends(get_db)
):
    """
    发送验证码（邮箱或手机号）
    """
    try:
        return AuthManager.send_verification_code(request.email)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"发送验证码失败: {str(e)}")
        raise HTTPException(status_code=500, detail="发送验证码失败，请稍后重试")


@router.post("/verify-email", response_model=VerifyEmailResponse)
def verify_email(
    request: VerifyEmailRequest,
    db: Session = Depends(get_db)
):
    """
    验证邮箱
    
    - 用户输入验证码进行验证
    - 验证成功后更新用户的邮箱验证状态
    """
    try:
        return AuthManager.verify_email(db, request.email, request.code)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"邮箱验证失败: {str(e)}")
        raise HTTPException(status_code=500, detail="验证失败，请稍后重试")


@router.post("/forgot-password", response_model=SendPasswordResetResponse)
def forgot_password(
    request: SendPasswordResetRequest,
    db: Session = Depends(get_db)
):
    """
    发送密码重置邮件
    """
    try:
        return AuthManager.send_password_reset(db, request.email)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"发送重置邮件失败: {str(e)}")
        raise HTTPException(status_code=500, detail="发送重置邮件失败，请稍后重试")


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    使用邮箱重置密码
    """
    try:
        return AuthManager.reset_password(db, request.reset_token, request.new_password)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"重置密码失败: {str(e)}")
        raise HTTPException(status_code=500, detail="重置密码失败，请稍后重试")


@router.post("/logout", response_model=LogoutResponse)
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    退出登录

    - 删除数据库中的当前 Session Token
    """
    try:
        return AuthManager.logout(db=db, token=token)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"退出登录失败: {str(e)}")
        raise HTTPException(status_code=500, detail="退出登录失败，请稍后重试")


@router.get("/check-email-verification/{email}")
def check_email_verification(
    email: str,
    db: Session = Depends(get_db)
):
    """
    检查邮箱验证状态（无需登录）
    不暴露用户是否存在，始终返回相同结构。
    """
    user = crud.get_user_by_email(db, email=email)
    if not user:
        # 不暴露用户不存在，返回统一格式
        return {
            "email": email,
            "is_email_verified": False,
            "email_verified_at": None,
            "message": "如果该邮箱已注册，可查看其验证状态",
        }
    
    return {
        "email": user.email,
        "is_email_verified": user.is_email_verified,
        "email_verified_at": user.email_verified_at,
    }


# ============ 修改密码相关路由 ============

@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    request: ChangePasswordRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    修改用户密码
    
    **需要登录**（需要在请求头中提供有效的 Token）
    
    **流程：**
    1. 验证旧密码是否正确
    2. 验证新密码不与旧密码相同
    3. 更新数据库中的密码哈希
    4. 返回成功消息
    
    **安全提示：**
    - 修改密码后，所有旧 Token 立即失效
    - 用户需要使用新密码重新登录
    
    **示例请求：**
    ```json
    {
        "old_password": "旧密码",
        "new_password": "新密码"
    }
    ```
    
    **示例响应：**
    ```json
    {
        "message": "密码修改成功，请使用新密码重新登录其他设备",
        "email": "user@example.com"
    }
    ```
    """
    try:
        return AuthManager.change_password(
            db=db,
            user_id=current_user["user_id"],
            old_password=request.old_password,
            new_password=request.new_password,
            current_token=None  # 可选：传递当前 Token 以保留会话
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"修改密码失败: {str(e)}")
        raise HTTPException(status_code=500, detail="修改密码失败，请稍后重试")


@router.delete("/account", response_model=DeleteAccountResponse)
def delete_account(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    注销账号

    删除当前登录用户账号，并在同一事务内清理所有持久化会话 Token。
    """
    try:
        return AuthManager.delete_account(db=db, user_id=current_user["user_id"])
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"注销账号失败: {str(e)}")
        raise HTTPException(status_code=500, detail="注销账号失败，请稍后重试")


# ─── 个人资料白名单字段 ───
_PROFILE_WHITELIST = {"phone", "nickname", "gender", "signature", "tags"}


@router.patch("/users/me")
def update_profile(
    req: UpdateProfileRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    更新个人资料（仅允许 phone / nickname / gender / signature / tags）
    """
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    updates = req.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field not in _PROFILE_WHITELIST:
            continue
        setattr(user, field, value)

    try:
        db.commit()
        db.refresh(user)
        return {"message": "资料更新成功", "updated_fields": list(updates.keys())}
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该手机号已被其他账号绑定",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"更新资料失败: {e}")
        raise HTTPException(status_code=500, detail="更新失败，请稍后重试")
