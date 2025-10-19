import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

from app.database.interface import DatabaseInterface
from app.applogger import logger

Base = declarative_base()

class UserModel(Base):
    __tablename__ = 'users'

    email = Column(String, primary_key=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)

class SQLAlchemyConnection(DatabaseInterface):
    def __init__(self):
        self.engine = None
        self.Session = None
        self._session = None
        self.db_url = os.getenv('DB_URI', 'postgresql://postgres:postgres@localhost:5432') + \
                        '/' + os.getenv('DB_NAME', 'compugit')

    def connect(self) -> None:
        try:
            self.engine = create_engine(self.db_url)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self._session = self.Session()
            logger.info("Successfully connected to PostgreSQL")
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {str(e)}")
            raise

    def disconnect(self) -> None:
        if self._session:
            self._session.close()
        if self.engine:
            self.engine.dispose()
        self._session = None
        self.engine = None
        logger.info("PostgreSQL connection closed")

    def is_connected(self) -> bool:
        if self.engine:
            try:
                with self.engine.connect() as connection:
                    connection.execute("SELECT 1")
                return True
            except:
                return False
        return False

    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user = UserModel(
                email=user_data['email'],
                password_hash=user_data['password_hash'],
                created_at=datetime.utcnow()
            )
            self._session.add(user)
            self._session.commit()
            return self._user_to_dict(user)
        except Exception as e:
            self._session.rollback()
            logger.error(f"Failed to create user in PostgreSQL: {str(e)}")
            raise

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        try:
            user = self._session.query(UserModel).filter_by(email=email).first()
            return self._user_to_dict(user) if user else None
        except Exception as e:
            logger.error(f"Failed to get user from PostgreSQL: {str(e)}")
            raise

    def get_all_users(self) -> List[Dict[str, Any]]:
        try:
            users = self._session.query(UserModel).all()
            return [self._user_to_dict(user) for user in users]
        except Exception as e:
            logger.error(f"Failed to get users from PostgreSQL: {str(e)}")
            raise

    def update_user(self, email: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            user = self._session.query(UserModel).filter_by(email=email).first()
            if user:
                update_data['updated_at'] = datetime.utcnow()
                for key, value in update_data.items():
                    if hasattr(user, key):
                        setattr(user, key, value)
                self._session.commit()
                return self._user_to_dict(user)
            return None
        except Exception as e:
            self._session.rollback()
            logger.error(f"Failed to update user in PostgreSQL: {str(e)}")
            raise

    def delete_user(self, email: str) -> bool:
        try:
            user = self._session.query(UserModel).filter_by(email=email).first()
            if user:
                self._session.delete(user)
                self._session.commit()
                return True
            return False
        except Exception as e:
            self._session.rollback()
            logger.error(f"Failed to delete user from PostgreSQL: {str(e)}")
            raise

    def _user_to_dict(self, user: UserModel) -> Dict[str, Any]:
        if not user:
            return None
        return {
            'email': user.email,
            'password_hash': user.password_hash,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'updated_at': user.updated_at.isoformat() if user.updated_at else None
        }