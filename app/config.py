import json
import math
import os
from dataclasses import asdict, dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlsplit


SUPPORTED_DATABASE_TYPES = {"mongodb", "postgresql", "mysql", "sqlite"}
SUPPORTED_CACHE_TYPES = {"redis"}
DEFAULT_DATABASES = {
    "sqlite_main": {
        "type": "sqlite",
        "path": str(
            Path(__file__).resolve().parents[1] / "instance" / "app.sqlite3"
        ),
    }
}

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


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "on"}
    return bool(value)


def _read_json_object(name: str) -> Dict[str, Any]:
    value = os.getenv(name)
    if not value:
        return {}
    try:
        result = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} must contain valid JSON") from error
    if not isinstance(result, dict):
        raise ValueError(f"{name} must be a JSON object")
    return result


def _read_origins(value: Any) -> List[str]:
    if isinstance(value, str):
        return [origin.strip() for origin in value.split(",") if origin.strip()]
    if isinstance(value, (list, tuple)):
        if not all(isinstance(origin, str) for origin in value):
            raise ValueError("CORS_ORIGINS must contain only strings")
        return [origin.strip() for origin in value if origin.strip()]
    raise ValueError("CORS_ORIGINS must be a comma-separated string or list")


def _positive_duration_seconds(value: Any, setting_name: str) -> float:
    if isinstance(value, timedelta):
        seconds = value.total_seconds()
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
    else:
        raise ValueError(f"{setting_name} must be a positive duration")
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError(f"{setting_name} must be a positive duration")
    return seconds


@dataclass(frozen=True)
class AppSettings:
    APP_NAME: str = "CompuGit_Backend"
    APP_VERSION: str = "1.0.0"
    ENV: str = "development"
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRES: int = 1
    REFRESH_TOKEN_EXPIRES: int = 1
    ENABLE_CORS: bool = False
    CORS_ORIGINS: Any = field(default_factory=list)
    CORS_SUPPORTS_CREDENTIALS: bool = False
    DATABASES: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: {
            name: dict(connection) for name, connection in DEFAULT_DATABASES.items()
        }
    )
    PRIMARY_DATABASE: str = "sqlite_main"
    BACKUP_DATABASE: Optional[str] = None
    ENABLE_CACHE: bool = False
    CACHE_DB: Dict[str, Any] = field(default_factory=dict)
    ALLOW_PUBLIC_REGISTRATION: bool = False
    MIN_PASSWORD_LENGTH: int = 8
    DEBUG: bool = False
    ENABLE_SWAGGER: bool = True
    AUTO_CREATE_SCHEMA: bool = True
    LOGIN_RATE_LIMIT: int = 5
    LOGIN_RATE_WINDOW_SECONDS: int = 60
    TRUST_PROXY: bool = False
    PROXY_FIX_X_FOR: int = 0
    PROXY_FIX_X_PROTO: int = 0
    PROXY_FIX_X_HOST: int = 0
    API_MAX_CONTENT_LENGTH: int = 2 * 1024 * 1024

    @classmethod
    def from_environment(cls, validate: bool = True) -> "AppSettings":
        databases = _read_json_object("DATABASES")
        if not os.getenv("DATABASES"):
            databases = {
                name: dict(connection)
                for name, connection in DEFAULT_DATABASES.items()
            }

        primary_database = os.getenv("PRIMARY_DATABASE")
        if not primary_database:
            primary_database = next(iter(databases))

        environment = os.getenv("ENV", "development").strip().lower()
        if environment == "prod":
            environment = "production"
        elif environment in {"dev", "local"}:
            environment = "development"
        elif environment in {"test", "testing"}:
            environment = "testing"

        settings = cls(
            APP_NAME=os.getenv("APP_NAME", "CompuGit_Backend"),
            APP_VERSION=os.getenv("VERSION", "1.0.0"),
            ENV=environment,
            SECRET_KEY=os.getenv("SECRET_KEY", ""),
            ACCESS_TOKEN_EXPIRES=int(os.getenv("ACCESS_TOKEN_EXPIRES", "1")),
            REFRESH_TOKEN_EXPIRES=int(os.getenv("REFRESH_TOKEN_EXPIRES", "1")),
            ENABLE_CORS=_read_bool("ENABLE_CORS"),
            CORS_ORIGINS=os.getenv("CORS_ORIGINS", ""),
            CORS_SUPPORTS_CREDENTIALS=_read_bool("CORS_SUPPORTS_CREDENTIALS"),
            DATABASES=databases,
            PRIMARY_DATABASE=primary_database.strip().lower(),
            BACKUP_DATABASE=os.getenv("BACKUP_DATABASE", "").strip().lower() or None,
            ENABLE_CACHE=_read_bool("ENABLE_CACHE"),
            CACHE_DB=_read_json_object("CACHE_DB"),
            ALLOW_PUBLIC_REGISTRATION=_read_bool("ALLOW_PUBLIC_REGISTRATION"),
            MIN_PASSWORD_LENGTH=int(os.getenv("MIN_PASSWORD_LENGTH", "8")),
            DEBUG=_read_bool("DEBUG"),
            ENABLE_SWAGGER=_read_bool("ENABLE_SWAGGER", default=True),
            AUTO_CREATE_SCHEMA=_read_bool("AUTO_CREATE_SCHEMA", default=True),
            LOGIN_RATE_LIMIT=int(os.getenv("LOGIN_RATE_LIMIT", "5")),
            LOGIN_RATE_WINDOW_SECONDS=int(
                os.getenv("LOGIN_RATE_WINDOW_SECONDS", "60")
            ),
            TRUST_PROXY=_read_bool("TRUST_PROXY"),
            PROXY_FIX_X_FOR=int(os.getenv("PROXY_FIX_X_FOR", "0")),
            PROXY_FIX_X_PROTO=int(os.getenv("PROXY_FIX_X_PROTO", "0")),
            PROXY_FIX_X_HOST=int(os.getenv("PROXY_FIX_X_HOST", "0")),
            API_MAX_CONTENT_LENGTH=int(
                os.getenv("API_MAX_CONTENT_LENGTH", str(2 * 1024 * 1024))
            ),
        )
        if validate:
            settings.validate()
        return settings

    def validate(self) -> None:
        if self.ENV not in {"development", "testing", "production"}:
            raise ValueError("ENV must be development, testing, or production")
        if self.ACCESS_TOKEN_EXPIRES <= 0 or self.REFRESH_TOKEN_EXPIRES <= 0:
            raise ValueError("JWT token expiration values must be positive")
        if self.MIN_PASSWORD_LENGTH < 8:
            raise ValueError("MIN_PASSWORD_LENGTH must be at least 8")
        if self.LOGIN_RATE_LIMIT <= 0 or self.LOGIN_RATE_WINDOW_SECONDS <= 0:
            raise ValueError("Login rate-limit values must be positive")
        if min(
            self.PROXY_FIX_X_FOR,
            self.PROXY_FIX_X_PROTO,
            self.PROXY_FIX_X_HOST,
        ) < 0:
            raise ValueError("Proxy trust counts must not be negative")
        if self.API_MAX_CONTENT_LENGTH <= 0:
            raise ValueError("API_MAX_CONTENT_LENGTH must be positive")
        if not self.TRUST_PROXY and any(
            (self.PROXY_FIX_X_FOR, self.PROXY_FIX_X_PROTO, self.PROXY_FIX_X_HOST)
        ):
            raise ValueError("Set TRUST_PROXY=True to enable forwarded header trust")

        if not isinstance(self.DATABASES, Mapping) or not self.DATABASES:
            raise ValueError("Configure at least one database in DATABASES")
        normalized_names = set()
        for name, database in self.DATABASES.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Database connection names must be non-empty strings")
            normalized_name = name.strip().lower()
            if normalized_name in normalized_names:
                raise ValueError("Database connection names must be unique")
            normalized_names.add(normalized_name)
            if not isinstance(database, Mapping):
                raise ValueError(f"Database connection '{name}' must be an object")
            db_type = str(database.get("type", "")).strip().lower()
            if db_type not in SUPPORTED_DATABASE_TYPES:
                raise ValueError(
                    f"Unsupported database type for connection '{name}': {db_type}"
                )

        primary = next(
            (
                database
                for name, database in self.DATABASES.items()
                if name.strip().lower() == self.PRIMARY_DATABASE
            ),
            None,
        )
        if not isinstance(primary, Mapping):
            raise ValueError("PRIMARY_DATABASE must name an enabled database")

        if self.BACKUP_DATABASE is not None:
            backup = next(
                (
                    database
                    for name, database in self.DATABASES.items()
                    if name.strip().lower() == self.BACKUP_DATABASE
                ),
                None,
            )
            if not isinstance(backup, Mapping) or str(
                backup.get("type", "")
            ).lower() not in SUPPORTED_DATABASE_TYPES:
                raise ValueError("BACKUP_DATABASE must name a supported database")

        if self.ENABLE_CACHE:
            if not self.CACHE_DB:
                raise ValueError("ENABLE_CACHE requires CACHE_DB Redis configuration")
            if (
                str(self.CACHE_DB.get("type", "")).strip().lower()
                not in SUPPORTED_CACHE_TYPES
            ):
                raise ValueError("CACHE_DB must use a supported cache type")

        origins = _read_origins(self.CORS_ORIGINS)
        if self.ENABLE_CORS and not origins:
            raise ValueError("CORS_ORIGINS must be configured when CORS is enabled")
        for origin in origins:
            if origin == "*":
                if self.ENV == "production":
                    raise ValueError("Wildcard CORS origins are not allowed in production")
                continue
            parsed_origin = urlsplit(origin)
            if (
                parsed_origin.scheme not in {"http", "https"}
                or not parsed_origin.hostname
                or parsed_origin.path
                or parsed_origin.query
                or parsed_origin.fragment
            ):
                raise ValueError(f"Invalid CORS origin: {origin}")
            if self.ENV == "production" and parsed_origin.scheme != "https":
                raise ValueError("Production CORS origins must use HTTPS")
        if (
            self.ENABLE_CORS
            and self.CORS_SUPPORTS_CREDENTIALS
            and "*" in origins
        ):
            raise ValueError(
                "Wildcard CORS origins cannot be used with credentials"
            )

        if self.ENV == "production":
            if len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "SECRET_KEY must be configured with at least 32 characters in production"
                )
            if self.DEBUG:
                raise ValueError("DEBUG must be disabled in production")
            if self.ENABLE_SWAGGER:
                raise ValueError("ENABLE_SWAGGER must be disabled in production")
            if not self.ENABLE_CACHE:
                raise ValueError(
                    "ENABLE_CACHE with Redis is required in production for shared token revocation"
                )
            if self.ALLOW_PUBLIC_REGISTRATION:
                raise ValueError(
                    "Public registration requires an email-verification flow before production use"
                )
            primary_type = str(primary.get("type", "")).strip().lower()
            if primary_type == "sqlite":
                raise ValueError(
                    "SQLite is intended for development; configure a production database"
                )

    def validate_flask_config(self, config: Mapping[str, Any]) -> "AppSettings":
        _positive_duration_seconds(
            config.get("JWT_ACCESS_TOKEN_EXPIRES", timedelta(hours=1)),
            "JWT_ACCESS_TOKEN_EXPIRES",
        )
        _positive_duration_seconds(
            config.get("JWT_REFRESH_TOKEN_EXPIRES", timedelta(days=1)),
            "JWT_REFRESH_TOKEN_EXPIRES",
        )
        environment = str(config.get("ENV", self.ENV)).strip().lower()
        if environment == "prod":
            environment = "production"
        elif environment in {"dev", "local"}:
            environment = "development"
        elif environment in {"test", "testing"}:
            environment = "testing"

        updated = replace(
            self,
            ENV=environment,
            SECRET_KEY=str(
                config.get("JWT_SECRET_KEY", config.get("SECRET_KEY", self.SECRET_KEY))
                or ""
            ),
            DATABASES=config.get("DATABASES", self.DATABASES),
            PRIMARY_DATABASE=str(
                config.get("PRIMARY_DATABASE", self.PRIMARY_DATABASE)
            ).strip().lower(),
            ENABLE_CACHE=_as_bool(config.get("ENABLE_CACHE", self.ENABLE_CACHE)),
            CACHE_DB=config.get("CACHE_DB", self.CACHE_DB),
            ENABLE_CORS=_as_bool(config.get("ENABLE_CORS", self.ENABLE_CORS)),
            CORS_ORIGINS=config.get("CORS_ORIGINS", self.CORS_ORIGINS),
            CORS_SUPPORTS_CREDENTIALS=_as_bool(
                config.get(
                    "CORS_SUPPORTS_CREDENTIALS",
                    self.CORS_SUPPORTS_CREDENTIALS,
                )
            ),
            ALLOW_PUBLIC_REGISTRATION=_as_bool(
                config.get(
                    "ALLOW_PUBLIC_REGISTRATION", self.ALLOW_PUBLIC_REGISTRATION
                )
            ),
            MIN_PASSWORD_LENGTH=int(
                config.get("MIN_PASSWORD_LENGTH", self.MIN_PASSWORD_LENGTH)
            ),
            DEBUG=_as_bool(config.get("DEBUG", self.DEBUG)),
            ENABLE_SWAGGER=_as_bool(
                config.get("ENABLE_SWAGGER", self.ENABLE_SWAGGER)
            ),
            AUTO_CREATE_SCHEMA=_as_bool(
                config.get("AUTO_CREATE_SCHEMA", self.AUTO_CREATE_SCHEMA)
            ),
            LOGIN_RATE_LIMIT=int(
                config.get("LOGIN_RATE_LIMIT", self.LOGIN_RATE_LIMIT)
            ),
            LOGIN_RATE_WINDOW_SECONDS=int(
                config.get(
                    "LOGIN_RATE_WINDOW_SECONDS", self.LOGIN_RATE_WINDOW_SECONDS
                )
            ),
            TRUST_PROXY=_as_bool(config.get("TRUST_PROXY", self.TRUST_PROXY)),
            PROXY_FIX_X_FOR=int(
                config.get("PROXY_FIX_X_FOR", self.PROXY_FIX_X_FOR)
            ),
            PROXY_FIX_X_PROTO=int(
                config.get("PROXY_FIX_X_PROTO", self.PROXY_FIX_X_PROTO)
            ),
            PROXY_FIX_X_HOST=int(
                config.get("PROXY_FIX_X_HOST", self.PROXY_FIX_X_HOST)
            ),
            API_MAX_CONTENT_LENGTH=int(
                config.get("API_MAX_CONTENT_LENGTH", self.API_MAX_CONTENT_LENGTH)
            ),
        )
        updated.validate()
        return updated

    def to_flask_config(self) -> Dict[str, Any]:
        values = asdict(self)
        secret_key = values["SECRET_KEY"] or "development-only-not-for-production"
        values["SECRET_KEY"] = secret_key
        values["JWT_SECRET_KEY"] = secret_key
        values["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
            hours=values.pop("ACCESS_TOKEN_EXPIRES")
        )
        values["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(
            days=values.pop("REFRESH_TOKEN_EXPIRES")
        )
        values["CORS_CONFIG"] = {
            "origins": _read_origins(values["CORS_ORIGINS"]),
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": values["CORS_SUPPORTS_CREDENTIALS"],
        }
        return values
