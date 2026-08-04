from pydantic import BaseModel, ConfigDict, EmailStr
from datetime import datetime
from typing import Optional, List

# Token 响应模型
class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int

# 用户基础信息
class UserBase(BaseModel):
    email: str
    username: Optional[str] = None
    nickname: str = "新用户"

# 用户创建（注册）
class UserCreate(UserBase):
    password: str
    verification_code: Optional[str] = None

# 用户信息返回（不包含密码）
class User(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# 🔥 新增：套餐信息
class PlanTier(BaseModel):
    level: int
    name: str
    price_monthly: float
    api_limit_daily: int
    token_limit_monthly: int
    knowledge_base_limit: int
    model_access: str
    concurrent_limit: int
    
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

# 🔥 新增：完整的用户信息（包含套餐详情）
class UserWithPlan(User):
    plan_level: int
    api_limit_daily: int
    token_limit_monthly: int
    knowledge_base_limit: int
    model_access: str
    concurrent_limit: int
    expires_at: Optional[datetime] = None
    days_remaining: Optional[int] = None  # 剩余天数
    plan_details: Optional[PlanTier] = None  # 套餐详细信息
    
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


# 🔥 新增：UserResponse 和 PlanInfo (匹配用户要求的结构)
class PlanInfo(BaseModel):
    level: int
    name: str
    daily_api_limit: int
    monthly_token_limit: int
    kb_limit: int
    available_models: List[str]
    concurrent_limit: int
    expires_at: Optional[datetime] = None
    days_remaining: Optional[int] = None

class UserResponse(BaseModel):
    id: int
    email: str
    phone: Optional[str] = None
    nickname: Optional[str] = None
    gender: Optional[str] = None
    signature: Optional[str] = None
    tags: Optional[str] = None
    username: Optional[str] = None
    is_active: bool
    created_at: datetime
    plan_info: PlanInfo

# Alias for PlanTier to match user request
class PlanTierResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

class UpgradeRequest(BaseModel):
    plan_level: int
    months: int = 1

class UserRegistrationResponse(User):
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    message: Optional[str] = None


# ============ 邮箱验证相关模型 ============

class SendVerificationRequest(BaseModel):
    """发送验证码请求 — 邮箱或手机号"""
    email: str  # 名称历史原因，实际可传邮箱或手机号

class SendVerificationResponse(BaseModel):
    """发送验证码响应"""
    message: str
    expires_in: int

class VerifyEmailRequest(BaseModel):
    """邮箱验证请求"""
    email: str
    code: str

class VerifyEmailResponse(BaseModel):
    """邮箱验证响应"""
    message: str
    email: str
    is_email_verified: bool


# ============ 密码重置相关模型 ============

class SendPasswordResetRequest(BaseModel):
    """发送密码重置邮件请求"""
    email: str

class SendPasswordResetResponse(BaseModel):
    """发送密码重置邮件响应"""
    message: str
    expires_in: int

class ResetPasswordRequest(BaseModel):
    """重置密码请求"""
    reset_token: str
    new_password: str

class ResetPasswordResponse(BaseModel):
    """重置密码响应"""
    message: str
    email: str


# ============ Token 刷新相关模型 ============

class RefreshTokenRequest(BaseModel):
    """Token 刷新请求"""
    refresh_token: str

class RefreshTokenResponse(BaseModel):
    """Token 刷新响应"""
    access_token: str
    token_type: str
    expires_in: int
    message: str


# ============ 修改密码相关模型 ============

class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str

class ChangePasswordResponse(BaseModel):
    """修改密码响应"""
    message: str
    email: str

class LogoutResponse(BaseModel):
    """退出登录响应"""
    message: str

class DeleteAccountResponse(BaseModel):
    """注销账号响应"""
    message: str


# ============ 个人资料更新模型 ============

class UpdateProfileRequest(BaseModel):
    """更新个人资料 — 只允许白名单字段"""
    phone: Optional[str] = None
    nickname: Optional[str] = None
    gender: Optional[str] = None
    signature: Optional[str] = None
    tags: Optional[str] = None  # JSON 字符串数组


# ============ 聊天相关模型 ============

from app.schemas.quiz import CitationOut


class ChatRequest(BaseModel):
    content: str
    session_id: Optional[str] = None
    stream: bool = False
    collection_id: Optional[str] = None
    # 对话模式: qa / learning / classroom_note / verify
    mode: Optional[str] = "qa"
    # TCN 集成字段（可选，不传则跳过知识状态更新）
    tc_node_id: Optional[str] = None
    tc_user_action: Optional[str] = None  # "correct" | "incorrect"
    tc_domain_id: Optional[str] = None

class ChatResponse(BaseModel):
    session_id: str
    session_title: Optional[str] = None
    role: str
    content: str
    created_at: datetime
    citations: Optional[List[CitationOut]] = None

class ChatHistoryItem(BaseModel):
    role: str
    content: str
    created_at: datetime

class ChatSession(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int

class ChatSessionList(BaseModel):
    sessions: List[ChatSession]