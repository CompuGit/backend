import os
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any, Dict


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
    DB_TYPE: str = "mongodb"
    DB_URI: str = ""
    DB_NAME: str = "compugit"
    DB_USERNAME: str = ""
    DB_PASSWORD: str = ""
    DB_HOST: str = "localhost"
    DB_PORT: int = 27017

    @classmethod
    def from_environment(cls) -> "AppSettings":
        settings = cls(
            APP_NAME=os.getenv("APP_NAME", "CompuGit_Backend"),
            APP_VERSION=os.getenv("VERSION", "1.0.0"),
            ENV=os.getenv("ENV", "development").lower(),
            SECRET_KEY=os.getenv("SECRET_KEY", ""),
            ACCESS_TOKEN_EXPIRES=int(os.getenv("ACCESS_TOKEN_EXPIRES", "1")),
            REFRESH_TOKEN_EXPIRES=int(os.getenv("REFRESH_TOKEN_EXPIRES", "1")),
            ENABLE_CORS=_read_bool("ENABLE_CORS"),
            CORS_ORIGINS=os.getenv("CORS_ORIGINS", "*"),
            DB_TYPE=os.getenv("DB_TYPE", "mongodb").lower(),
            DB_URI=os.getenv("DB_URI", ""),
            DB_NAME=os.getenv("DB_NAME", "compugit"),
            DB_USERNAME=os.getenv("DB_USERNAME", ""),
            DB_PASSWORD=os.getenv("DB_PASSWORD", ""),
            DB_HOST=os.getenv("DB_HOST", "localhost"),
            DB_PORT=int(os.getenv("DB_PORT", "27017")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.ACCESS_TOKEN_EXPIRES <= 0 or self.REFRESH_TOKEN_EXPIRES <= 0:
            raise ValueError("JWT token expiration values must be positive")
        if self.DB_TYPE not in {"mongodb", "postgresql"}:
            raise ValueError(f"Unsupported database type: {self.DB_TYPE}")
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