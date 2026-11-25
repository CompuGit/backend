import ast
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pymongo
from pymongo.errors import DuplicateKeyError
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.api.models import UserModel
from app.core.logging import logger
from app.database.interface import DatabaseInterface


LEGACY_BOOTSTRAP_ADMIN_HASH = (
    "scrypt:32768:8:1$nnQjROM8w60A12kb$"
    "c5525885afac48cc3ec8ca612f33168383ed9893c5acd10c6e2f60850f8b22198"
    "e67fb74e241fd156d44d4f9c8a8c9f10e094aef4906b30ba6990a22876a3515"
)


class DuplicateIdentityError(ValueError):
    pass


class UserService:
    OPERATIONS = {"get_user", "list_users", "create_user", "update_user", "delete_user"}
    UPDATE_FIELDS = {
        "userName",
        "email",
        "name",
        "contact",
        "roles",
        "canLogin",
        "departments",
        "password_hash",
    }

    def __init__(self, database: DatabaseInterface):
        if database.db_type not in {"mongodb", "sqlite", "mysql", "postgresql"}:
            raise ValueError(f"Unsupported user database type: {database.db_type}")
        self.db_type = database.db_type
        self.database = database
        self.db = database.native
        if self.db_type == "mongodb":
            result = self.db["users"].update_many(
                {"password_hash": LEGACY_BOOTSTRAP_ADMIN_HASH},
                {"$set": {"canLogin": False}},
            )
            modified_count = result.modified_count
        else:
            with self.database.session_scope() as session:
                modified_count = (
                    session.query(UserModel)
                    .filter_by(password_hash=LEGACY_BOOTSTRAP_ADMIN_HASH)
                    .update({"canLogin": False})
                )
                session.commit()
        if modified_count:
            logger.warning(
                "Disabled %s legacy bootstrap account(s) in %s",
                modified_count,
                self.db_type,
            )

    def supports(self, operation: str) -> bool:
        return operation in self.OPERATIONS

    def get_user(self, identifier: Any) -> Optional[Dict[str, Any]]:
        if self.db_type == "mongodb":
            query = self._mongo_identifier_query(identifier)
            return self.db["users"].find_one(query, {"_id": 0})

        with self.database.session_scope() as session:
            user = session.query(UserModel).filter(
                self._relational_identifier_query(identifier)
            ).first()
            return self._relational_user_to_dict(user) if user else None

    def list_users(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        filters = filters or {}
        if self.db_type == "mongodb":
            query = {}
            if "isActive" in filters:
                query["canLogin"] = filters["isActive"]
            return list(
                self.db["users"]
                .find(query, {"_id": 0})
                .sort("userId", 1)
                .skip(offset)
                .limit(limit)
            )

        with self.database.session_scope() as session:
            query = session.query(UserModel)
            if "isActive" in filters:
                query = query.filter(UserModel.canLogin.is_(bool(filters["isActive"])))
            users = (
                query.order_by(UserModel.userId)
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [self._relational_user_to_dict(user) for user in users]

    def count_admins(self) -> int:
        if self.db_type == "mongodb":
            return self.db["users"].count_documents(
                {"roles": "admin", "canLogin": True}
            )
        with self.database.session_scope() as session:
            return session.query(UserModel).filter(
                UserModel.roles.contains('"admin"'), UserModel.canLogin.is_(True)
            ).count()

    def count_users(self, filters: Optional[Dict[str, Any]] = None) -> int:
        filters = filters or {}
        if self.db_type == "mongodb":
            query = {}
            if "isActive" in filters:
                query["canLogin"] = filters["isActive"]
            return self.db["users"].count_documents(query)
        with self.database.session_scope() as session:
            query = session.query(UserModel)
            if "isActive" in filters:
                query = query.filter(UserModel.canLogin.is_(bool(filters["isActive"])))
            return query.count()

    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        data = self._normalize_user_data(user_data)
        if self.db_type == "mongodb":
            data["userId"] = self._next_mongodb_user_id()
            now = datetime.now(timezone.utc)
            data["created_at"] = now
            data["updated_at"] = now
            try:
                self.db["users"].insert_one(data)
            except DuplicateKeyError as error:
                raise DuplicateIdentityError(
                    "A user with that username or email already exists"
                ) from error
            created = self.get_user(data["userId"])
            if created is None:
                raise RuntimeError("Inserted MongoDB user could not be retrieved")
            return created

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        user = UserModel(
            userName=data["userName"],
            email=data["email"],
            name=data.get("name"),
            contact=data.get("contact"),
            roles=json.dumps(data["roles"]),
            canLogin=data["canLogin"],
            password_hash=data["password_hash"],
            departments=json.dumps(data["departments"]),
            created_at=now,
            updated_at=now,
        )
        try:
            with self.database.session_scope() as session:
                session.add(user)
                session.commit()
                session.refresh(user)
                return self._relational_user_to_dict(user)
        except IntegrityError as error:
            logger.info("Duplicate user create rejected for %s", data["userName"])
            raise DuplicateIdentityError(
                "A user with that username or email already exists"
            ) from error

    def update_user(
        self, identifier: Any, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        unexpected = set(update_data) - self.UPDATE_FIELDS
        if unexpected:
            raise ValueError(f"Unsupported user fields: {', '.join(sorted(unexpected))}")
        data = dict(update_data)
        if "userName" in data:
            data["userName"] = self._normalize_identifier(data["userName"])
        if "email" in data:
            data["email"] = self._normalize_identifier(data["email"])
            if not self._valid_email(data["email"]):
                raise ValueError("Email address is invalid")
        if "userName" in data:
            if len(data["userName"]) > 80 or not re.fullmatch(
                r"[a-z0-9][a-z0-9_.-]*", data["userName"]
            ):
                raise ValueError("Username format is invalid")
        for field in ("roles", "departments"):
            if field in data:
                data[field] = self._normalize_string_list(data[field], field)

        now = datetime.now(timezone.utc)
        if self.db_type == "mongodb":
            update = dict(data)
            update["updated_at"] = now
            try:
                result = self.db["users"].update_one(
                    self._mongo_identifier_query(identifier), {"$set": update}
                )
            except DuplicateKeyError as error:
                raise DuplicateIdentityError(
                    "A user with that username or email already exists"
                ) from error
            if not result.matched_count:
                return None
            return self.get_user(identifier)

        try:
            with self.database.session_scope() as session:
                user = session.query(UserModel).filter(
                    self._relational_identifier_query(identifier)
                ).first()
                if user is None:
                    return None
                for key, value in data.items():
                    if key in {"roles", "departments"}:
                        value = json.dumps(value)
                    setattr(user, key, value)
                user.updated_at = now.replace(tzinfo=None)
                session.commit()
                session.refresh(user)
                return self._relational_user_to_dict(user)
        except IntegrityError as error:
            raise DuplicateIdentityError(
                "A user with that username or email already exists"
            ) from error

    def delete_user(self, identifier: Any) -> bool:
        if self.db_type == "mongodb":
            result = self.db["users"].delete_one(self._mongo_identifier_query(identifier))
            return result.deleted_count > 0

        with self.database.session_scope() as session:
            user = session.query(UserModel).filter(
                self._relational_identifier_query(identifier)
            ).first()
            if user is None:
                return False
            session.delete(user)
            session.commit()
            return True

    @staticmethod
    def _normalize_identifier(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Username and email must be non-empty strings")
        return value.strip().lower()

    @classmethod
    def _normalize_user_data(cls, user_data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(user_data, dict):
            raise ValueError("User data must be an object")
        username = cls._normalize_identifier(user_data.get("userName"))
        email = cls._normalize_identifier(user_data.get("email"))
        if len(username) > 80 or len(email) > 254:
            raise ValueError("Username or email is too long")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", username):
            raise ValueError("Username format is invalid")
        if not cls._valid_email(email):
            raise ValueError("Email address is invalid")
        can_login = user_data.get("canLogin", True)
        if not isinstance(can_login, bool):
            raise ValueError("canLogin must be a boolean")
        password_hash = user_data.get("password_hash")
        if not isinstance(password_hash, str) or not password_hash:
            raise ValueError("A password hash is required")
        roles = cls._normalize_string_list(user_data.get("roles", ["user"]), "roles")
        departments = cls._normalize_string_list(
            user_data.get("departments", []), "departments"
        )
        return {
            "userName": username,
            "email": email,
            "name": user_data.get("name"),
            "contact": user_data.get("contact"),
            "roles": roles,
            "canLogin": can_login,
            "password_hash": password_hash,
            "departments": departments,
        }

    @staticmethod
    def _valid_email(email: str) -> bool:
        return bool(
            re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        )

    @staticmethod
    def _normalize_string_list(value: Any, field: str) -> List[str]:
        if not isinstance(value, (list, tuple)) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise ValueError(f"{field} must be a list of non-empty strings")
        normalized = [item.strip().lower() for item in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError(f"{field} must not contain duplicates")
        return normalized

    @staticmethod
    def _mongo_identifier_query(identifier: Any) -> Dict[str, Any]:
        alternatives = [{"userName": identifier}, {"email": identifier}]
        if isinstance(identifier, int):
            alternatives.append({"userId": identifier})
        elif isinstance(identifier, str) and identifier.isdigit():
            alternatives.append({"userId": int(identifier)})
        return {"$or": alternatives}

    @staticmethod
    def _relational_identifier_query(identifier: Any):
        alternatives = [
            UserModel.userName == identifier,
            UserModel.email == identifier,
        ]
        if isinstance(identifier, int) or (
            isinstance(identifier, str) and identifier.isdigit()
        ):
            alternatives.append(UserModel.userId == int(identifier))
        return or_(*alternatives)

    def _next_mongodb_user_id(self) -> int:
        result = self.db["counters"].find_one_and_update(
            {"_id": "userId"},
            {"$inc": {"sequence_value": 1}},
            return_document=pymongo.ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("MongoDB user ID counter is not initialized")
        return result["sequence_value"]

    @staticmethod
    def _decode_string_list(value: Optional[str], field: str) -> List[str]:
        if not value:
            return []
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            # Existing databases may contain Python-list strings from the old model.
            decoded = ast.literal_eval(value)
        if not isinstance(decoded, list) or not all(
            isinstance(item, str) for item in decoded
        ):
            raise ValueError(f"Stored user {field} value is invalid")
        return decoded

    @classmethod
    def _relational_user_to_dict(cls, user: UserModel) -> Dict[str, Any]:
        return {
            "userId": user.userId,
            "userName": user.userName,
            "email": user.email,
            "name": user.name,
            "contact": user.contact,
            "roles": cls._decode_string_list(user.roles, "roles"),
            "canLogin": user.canLogin,
            "password_hash": user.password_hash,
            "departments": cls._decode_string_list(user.departments, "departments"),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
