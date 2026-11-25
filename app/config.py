import json
import os
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any, Dict, Optional


SUPPORTED_DATABASE_TYPES = {"mongodb", "postgresql", "mysql", "sqlite"}
SUPPORTED_CACHE_TYPES = {"redis"}

DEFAULT_DB_PORT_BY_TYPE = {
    "mongodb": 27017,
    "postgresql": 5432,
    "mysql": 3306,
}


def _read_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "on"}


@dataclass(frozen=True)
class AppSettings:
    APP_NAME: str = "CompuGit_Backend"
    APP_VERSION: str = "1.0.0"
    ENV: str = "development"
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRES: int = 1
    REFRESH_TOKEN_EXPIRES: int = 1
    ENABLE_CORS: bool = False
    CORS_ORIGINS: str = "*"
    DATABASES: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    PRIMARY_DATABASE: str = "sqlite_main"
    BACKUP_DATABASE: Optional[str] = None
    ENABLE_CACHE: bool = False
    CACHE_DB: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_environment(cls) -> "AppSettings":
        databases = os.getenv("DATABASES")
        configured_databases: Dict[str, Dict[str, Any]] = {}
        if databases:
            try:
                configured_databases = json.loads(databases)
            except json.JSONDecodeError as error:
                raise ValueError("DATABASES must contain valid JSON") from error
            if not isinstance(configured_databases, dict):
                raise ValueError("DATABASES must be a JSON object")

        cache_db = os.getenv("CACHE_DB")
        configured_cache: Dict[str, Any] = {}
        if cache_db:
            try:
                configured_cache = json.loads(cache_db)
            except json.JSONDecodeError as error:
                raise ValueError("CACHE_DB must contain valid JSON") from error
            if not isinstance(configured_cache, dict):
                raise ValueError("CACHE_DB must be a JSON object")

        primary_database = os.getenv("PRIMARY_DATABASE")
        if not primary_database and configured_databases:
            primary_database = next(iter(configured_databases))

        settings = cls(
            APP_NAME=os.getenv("APP_NAME", "CompuGit_Backend"),
            APP_VERSION=os.getenv("VERSION", "1.0.0"),
            ENV=os.getenv("ENV", "development").lower(),
            SECRET_KEY=os.getenv("SECRET_KEY", ""),
            ACCESS_TOKEN_EXPIRES=int(os.getenv("ACCESS_TOKEN_EXPIRES", "1")),
            REFRESH_TOKEN_EXPIRES=int(os.getenv("REFRESH_TOKEN_EXPIRES", "1")),
            ENABLE_CORS=_read_bool("ENABLE_CORS"),
            CORS_ORIGINS=os.getenv("CORS_ORIGINS", "*"),
            DATABASES=configured_databases,
            PRIMARY_DATABASE=(primary_database or "").strip().lower(),
            BACKUP_DATABASE=os.getenv("BACKUP_DATABASE", "").strip().lower() or None,
            ENABLE_CACHE=_read_bool("ENABLE_CACHE"),
            CACHE_DB=configured_cache,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.ACCESS_TOKEN_EXPIRES <= 0 or self.REFRESH_TOKEN_EXPIRES <= 0:
            raise ValueError("JWT token expiration values must be positive")

        if not self.DATABASES:
            raise ValueError("Configure at least one database in DATABASES")
        for name, database in self.DATABASES.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Database connection names must be non-empty strings")
            if not isinstance(database, dict):
                raise ValueError(f"Database connection '{name}' must be an object")
            db_type = str(database.get("type", "")).strip().lower()
            if db_type not in SUPPORTED_DATABASE_TYPES:
                raise ValueError(
                    f"Unsupported database type for connection '{name}': {db_type}"
                )

        primary = self.DATABASES.get(self.PRIMARY_DATABASE)
        if not isinstance(primary, dict) or str(primary.get("type", "")).lower() not in SUPPORTED_DATABASE_TYPES:
            raise ValueError("PRIMARY_DATABASE must name an enabled persistent database")

        if self.BACKUP_DATABASE is not None:
            backup = self.DATABASES.get(self.BACKUP_DATABASE)
            if not isinstance(backup, dict) or str(
                backup.get("type", "")
            ).lower() not in SUPPORTED_DATABASE_TYPES:
                raise ValueError("BACKUP_DATABASE must name a supported database connection")

        if self.ENABLE_CACHE:
            if not self.CACHE_DB:
                raise ValueError("ENABLE_CACHE requires CACHE_DB Redis configuration")
            if str(self.CACHE_DB.get("type", "")).strip().lower() not in SUPPORTED_CACHE_TYPES:
                raise ValueError("CACHE_DB must use a supported cache type")

        if self.ENV == "prod" and not self.SECRET_KEY:
            raise ValueError("SECRET_KEY must be configured in production")

    def to_flask_config(self) -> Dict[str, Any]:
        values = asdict(self)
        values["JWT_SECRET_KEY"] = values.pop("SECRET_KEY")
        values["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
            hours=values.pop("ACCESS_TOKEN_EXPIRES")
        )
        values["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(
            days=values.pop("REFRESH_TOKEN_EXPIRES")
        )
        values["CORS_CONFIG"] = {
            "origins": [origin.strip() for origin in values["CORS_ORIGINS"].split(",")],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True,
        }
        return values