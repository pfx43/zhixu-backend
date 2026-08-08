"""
用量表模型 — usage_daily / usage_token
用于按日 API 调用次数和按月 token 消耗的配额控制。
"""

from sqlalchemy import Column, Integer, String, BigInteger, Date, Index
from app.core.database import Base


class UsageDaily(Base):
    __tablename__ = "usage_daily"

    user_id = Column(Integer, primary_key=True, nullable=False)
    date = Column(Date, primary_key=True, nullable=False)
    api_calls = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_usage_daily_user_date", "user_id", "date"),
    )


class UsageToken(Base):
    __tablename__ = "usage_token"

    user_id = Column(Integer, primary_key=True, nullable=False)
    yyyymm = Column(String(6), primary_key=True, nullable=False)  # 如 '202608'
    prompt_tokens = Column(BigInteger, nullable=False, default=0)
    completion_tokens = Column(BigInteger, nullable=False, default=0)
    total_tokens = Column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        Index("idx_usage_token_user_yyyymm", "user_id", "yyyymm"),
    )
