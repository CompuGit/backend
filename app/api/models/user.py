from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Integer, Boolean

from app.api.models.base import Base


class UserModel(Base):
    __tablename__ = "users"
    
    userId = Column(Integer, primary_key=True, autoincrement=True)
    userName = Column(String, nullable=False)
    email = Column(String, unique=True)
    name = Column(String, nullable=True)
    contact = Column(String, nullable=True)
    roles = Column(String, nullable=True)
    canLogin = Column(Boolean, default=True)
    password_hash = Column(String, nullable=False)
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
