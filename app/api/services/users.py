from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pymongo
from sqlalchemy.orm import Session

from app.api.models import UserModel
from app.core.logging import logger
from app.database.interface import DatabaseInterface


class UserService:
    OPERATIONS = {"get_user", "list_users", "create_user", "update_user", "delete_user"}

    def __init__(self, database: DatabaseInterface):
        if database.db_type not in {"mongodb", "sqlite", "mysql", "postgresql"}:
            raise ValueError(f"Unsupported user database type: {database.db_type}")
        self.db_type = database.db_type
        self.db = database.native
        self._ensure_admin_user()

    def supports(self, operation: str) -> bool:
        return operation in self.OPERATIONS

    def get_user(self, identifier: Any) -> Optional[Dict[str, Any]]:
        if self.db_type == "mongodb":
            return self.db["users"].find_one(
                {
                    "$or": [
                        {"email": identifier},
                        {"userName": identifier},
                        {"userId": identifier},
                    ]
                },
                {"_id": 0},
            )

        user = self.db.query(UserModel).filter_by(email=identifier).first()
        return self._relational_user_to_dict(user) if user else None

    def list_users(
        self, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        if self.db_type == "mongodb":
            query = {}
            if filters and "isActive" in filters:
                query["isActive"] = filters["isActive"]
            return list(self.db["users"].find(query, {"_id": 0}))

        users = self.db.query(UserModel).all()
        return [self._relational_user_to_dict(user) for user in users]

    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        if self.db_type == "mongodb":
            data = dict(user_data)
            data["userId"] = self._next_mongodb_user_id()
            data["created_at"] = datetime.now()
            if self.db.users.find_one({"userName": "admin"}):
                return
            self.db.users.insert_one(data)
            created = self.get_user(data["userId"])
            if created is None:
                raise RuntimeError("Inserted MongoDB user could not be retrieved")
            return created

        session = self.db
        if session.query(UserModel).filter_by(email=user_data["email"]).first():
            return
        try:
            user = UserModel(
                userName=user_data["userName"],
                email=user_data["email"],
                name=user_data.get("name"),
                contact=user_data.get("contact"),
                roles=str(user_data.get("roles", [])),
                canLogin=user_data.get("canLogin", True),
                password_hash=user_data["password_hash"],
                departments=str(user_data.get("departments", [])),
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            session.add(user)
            session.commit()
            return self._relational_user_to_dict(user)
        except Exception as error:
            session.rollback()
            logger.error("Failed to create user in %s: %s", self.db_type, error)
            raise

    def update_user(
        self, identifier: Any, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        if self.db_type == "mongodb":
            data = dict(update_data)
            data["updated_at"] = datetime.now()
            result = self.db["users"].update_one(
                {"userId": identifier}, {"$set": data}
            )
            return self.get_user(identifier) if result.modified_count else None

        session = self.db
        try:
            user = session.query(UserModel).filter_by(email=identifier).first()
            if user:
                for key, value in update_data.items():
                    if hasattr(user, key):
                        setattr(user, key, value)
                user.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                session.commit()
                return self._relational_user_to_dict(user)
            return None
        except Exception as error:
            session.rollback()
            logger.error("Failed to update user in %s: %s", self.db_type, error)
            raise

    def delete_user(self, identifier: Any) -> bool:
        if self.db_type == "mongodb":
            result = self.db["users"].delete_one({"userId": identifier})
            return result.deleted_count > 0

        session = self.db
        try:
            user = session.query(UserModel).filter_by(email=identifier).first()
            if not user:
                return False
            session.delete(user)
            session.commit()
            return True
        except Exception as error:
            session.rollback()
            logger.error("Failed to delete user from %s: %s", self.db_type, error)
            raise

    def _next_mongodb_user_id(self) -> int:
        result = self.db["counters"].find_one_and_update(
            {"_id": "userId"},
            {"$inc": {"sequence_value": 1}},
            return_document=pymongo.ReturnDocument.AFTER,
        )
        return result["sequence_value"]

    @staticmethod
    def _relational_user_to_dict(user: UserModel) -> Dict[str, Any]:
        return {
            "email": user.email,
            "password_hash": user.password_hash,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }

    def _ensure_admin_user(self) -> None:
        admin_user = {
            "userId": 10000,
            "userName": "admin",
            "email": "ad.compugit@gmail.com",
            "name": "Admin Compugit",
            "contact": "6305813208",
            "roles": ["admin"],
            "canLogin": True,
            "password_hash": (
                "scrypt:32768:8:1$nnQjROM8w60A12kb$"
                "c5525885afac48cc3ec8ca612f33168383ed9893c5acd10c6e2f60850f8b22198"
                "e67fb74e241fd156d44d4f9c8a8c9f10e094aef4906b30ba6990a22876a3515"
            ),
            "departments": [],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }

        self.create_user(admin_user)
