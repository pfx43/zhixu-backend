from sqlalchemy import Column, Integer, String, DateTime, Boolean, DECIMAL
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    
    # 字段顺序必须严格与数据库表一致
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    username = Column(String(100), nullable=True)
    nickname = Column(String(50), nullable=False, default='用户')
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # 邮箱验证字段
    is_email_verified = Column(Boolean, default=False)
    email_verified_at = Column(DateTime, nullable=True)
    
    plan_level = Column(Integer, nullable=False, default=0)
    api_limit_daily = Column(Integer, nullable=False, default=10)
    token_limit_monthly = Column(Integer, nullable=False, default=10000)
    knowledge_base_limit = Column(Integer, nullable=False, default=1)
    model_access = Column(String(100), nullable=False, default='gpt-3.5-turbo')
    concurrent_limit = Column(Integer, nullable=False, default=1)
    expires_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    phone = Column(String(20), nullable=True, unique=True)

    # 个人资料扩展字段
    gender = Column(String(10), nullable=True)
    signature = Column(String(200), nullable=True)
    tags = Column(String(500), nullable=True)  # JSON 数组，如 '["程序员","学生"]'

    # Dify 知识库 ID（注册时自动分配）
    dataset_id = Column(String(255), nullable=True)

    # TCN 知识追踪用户哈希（注册时自动生成）
    user_hash = Column(String(64), nullable=True, unique=True)

    kb_collections = relationship("KbCollection", back_populates="user")
    documents = relationship("Document", back_populates="user")
    question_refs = relationship("UserQuestionRef", back_populates="user")
    quiz_sessions = relationship("QuizSession", back_populates="user")
    quiz_answers = relationship("QuizAnswer", back_populates="user")
    tutor_sessions = relationship("TutorSession", back_populates="user")

class PlanTier(Base):
    __tablename__ = "plan_tiers"
    
    level = Column(Integer, primary_key=True, index=True, autoincrement=False)
    name = Column(String(50), nullable=False)
    price_monthly = Column(DECIMAL(10, 2))
    price_yearly = Column(DECIMAL(10, 2))
    api_limit_daily = Column(Integer, nullable=False)
    token_limit_monthly = Column(Integer, nullable=False)
    knowledge_base_limit = Column(Integer, nullable=False)
    model_access = Column(String(255), nullable=False)
    concurrent_limit = Column(Integer, nullable=False)
    support_level = Column(String(20), default='basic')
    created_at = Column(DateTime, default=datetime.utcnow)
