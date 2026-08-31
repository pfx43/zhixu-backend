"""TCN 封闭学科名单。书的 tcn_domain 只能是这里的 id 或 NULL。"""
from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class TcnDomain(Base):
    __tablename__ = "tcn_domains"

    id = Column(String(64), primary_key=True)
    label = Column(String(100), nullable=False)

    documents = relationship("Document", back_populates="tcn_domain_row")
