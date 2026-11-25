from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.api.models.base import Base


class UserModel(Base):
    __tablename__ = "users"
    
    userId = Column(Integer, primary_key=True, autoincrement=True)
    userName = Column(String(80), nullable=False, unique=True, index=True)
    email = Column(String(254), nullable=False, unique=True, index=True)
    name = Column(String, nullable=True)
    contact = Column(String, nullable=True)
    roles = Column(String, nullable=False, default="[]")
    canLogin = Column(Boolean, nullable=False, default=True)
    password_hash = Column(String(512), nullable=False)
    departments = Column(String, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
            DateTime,
            nullable=True,
            default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
