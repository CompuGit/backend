import json
import os
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import unquote, urlsplit

from flask import current_app, has_app_context
from redis import Redis

from app.core.logging import logger
from app.database.ddb import (
    MongoDBBackup,
    MongoDBConnection,
    MongoDBRestore,
    check_mongodb_tools,
)
from app.database.interface import DatabaseInterface
from app.database.rdb import RDBConnection


def _read_object(value: Any, setting_name: str) -> Mapping[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(f"{setting_name} must contain valid JSON") from error
    if not isinstance(value, Mapping):
        raise ValueError(f"{setting_name} must be a JSON object")
    return value


def _cache_enabled(settings: Mapping[str, Any]) -> bool:
    value = settings.get("ENABLE_CACHE", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "on"}
    return bool(value)


def _effective_databases(settings: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    configured = _read_object(settings.get("DATABASES", {}), "DATABASES")
    databases: Dict[str, Mapping[str, Any]] = {}
    for raw_name, raw_settings in configured.items():
        name = str(raw_name).strip().lower()
        if not re.fullmatch(r"[a-z0-9_-]+", name):
            raise ValueError(f"Invalid database connection name: {raw_name}")
        if not isinstance(raw_settings, Mapping):
            raise ValueError(f"Database connection '{name}' must be an object")
        db_type = str(raw_settings.get("type", "")).strip().lower()
        if db_type == "redis":
            raise ValueError("Redis cache connections must be configured in CACHE_DB")
        if db_type not in {"sqlite", "mysql", "postgresql", "mongodb"}:
            raise ValueError(
                f"Unsupported database type for connection '{name}': {db_type}"
            )
        databases[name] = raw_settings
    return databases


def _connection_settings(
    db_type: str, raw_settings: Mapping[str, Any]
) -> Dict[str, Any]:
    return {
        "DB_TYPE": db_type,
        "DB_URI": raw_settings.get("uri", raw_settings.get("url", "")),
        "DB_NAME": raw_settings.get(
            "name", raw_settings.get("database", "compugit")
        ),
        "DB_USERNAME": raw_settings.get("username", ""),
        "DB_PASSWORD": raw_settings.get("password", ""),
        "DB_HOST": raw_settings.get("host", "localhost"),
        "DB_PORT": raw_settings.get("port"),
        "DB_SQLITE_PATH": raw_settings.get(
            "sqlite_path", raw_settings.get("path", "compugit.sqlite3")
        ),
        "REDIS_DB": raw_settings.get("db", raw_settings.get("database", 0)),
    }


def _connection_definitions(
    settings: Mapping[str, Any],
) -> Tuple[List[Tuple[str, str, Dict[str, Any]]], str]:
    databases = _effective_databases(settings)
    definitions = []
    for name, raw_settings in databases.items():
        db_type = str(raw_settings.get("type", "")).strip().lower()
        connection_settings = _connection_settings(db_type, raw_settings)
        definitions.append((name, db_type, connection_settings))

    persistent_names = {name for name, _, _ in definitions}
    if not persistent_names:
        raise ValueError("DATABASES must configure at least one persistent database")

    primary = str(settings.get("PRIMARY_DATABASE", "")).strip().lower()
    if primary not in persistent_names:
        raise ValueError(f"PRIMARY_DATABASE '{primary}' is not enabled")
    return definitions, primary


class DatabaseFactory:
    """Create and manage named connections for the supported database backends."""

    CONNECTION_TYPES = {
        "postgresql": RDBConnection,
        "mysql": RDBConnection,
        "sqlite": RDBConnection,
        "mongodb": MongoDBConnection,
    }

    @classmethod
    def create_connection(
        cls, settings: Mapping[str, Any]
    ) -> Any:
        db_type = str(settings.get("DB_TYPE", "")).strip().lower()
        if db_type == "redis":
            return cls._create_redis_connection(settings)
        connection_type = cls.CONNECTION_TYPES.get(db_type)
        if connection_type is None:
            raise ValueError(f"Unsupported database type: {db_type}")
        connection = connection_type(settings)
        return cls._connect(connection, settings)

    @staticmethod
    def _create_redis_connection(settings: Mapping[str, Any]) -> Redis:
        connection: Optional[Redis] = None
        try:
            uri = settings.get("DB_URI")
            if uri:
                connection = Redis.from_url(uri, decode_responses=True)
            else:
                connection = Redis(
                    host=settings.get("DB_HOST", "localhost"),
                    port=int(settings.get("DB_PORT") or 6379),
                    db=int(settings.get("REDIS_DB", 0)),
                    username=settings.get("DB_USERNAME") or None,
                    password=settings.get("DB_PASSWORD") or None,
                    decode_responses=True,
                )
            connection.ping()
            logger.info("Successfully connected to Redis")
            return connection
        except Exception as error:
            if connection is not None:
                try:
                    connection.close()
                except Exception as cleanup_error:
                    logger.warning("Redis cleanup after failed connect also failed: %s", cleanup_error)
            logger.error("Failed to initialize Redis connection: %s", error)
            raise

    @staticmethod
    def _disconnect(connection: Any) -> None:
        disconnect = getattr(connection, "disconnect", None)
        if callable(disconnect):
            disconnect()
            return
        close = getattr(connection, "close", None)
        if callable(close):
            close()

    @staticmethod
    def _connect(
        connection: DatabaseInterface, settings: Mapping[str, Any]
    ) -> DatabaseInterface:
        try:
            connection.connect()
            return connection
        except Exception as error:
            try:
                connection.disconnect()
            except Exception as cleanup_error:
                logger.warning(
                    "Database cleanup after failed connect also failed: %s",
                    cleanup_error,
                )
            logger.error(
                "Failed to initialize %s database connection: %s",
                settings.get("DB_TYPE"),
                error,
            )
            raise

    @classmethod
    def get_databases(
        cls, config: Optional[Mapping[str, Any]] = None
    ) -> Dict[str, Any]:
        settings = config or {}
        definitions, primary = _connection_definitions(settings)
        connections: Dict[str, DatabaseInterface] = {}
        try:
            for name, _, connection_settings in definitions:
                connection_settings["AUTO_CREATE_SCHEMA"] = (
                    name == primary
                    and bool(settings.get("AUTO_CREATE_SCHEMA", True))
                )
                connections[name] = cls.create_connection(connection_settings)
            return connections
        except Exception:
            for connection in connections.values():
                try:
                    cls._disconnect(connection)
                except Exception as cleanup_error:
                    logger.warning("Database cleanup failed: %s", cleanup_error)
            raise


class BackupFactory:
    @staticmethod
    def check_tools_availability() -> Dict[str, bool]:
        return check_mongodb_tools()

    @staticmethod
    def get_mongodb_backup_instance(
        connection_settings: Optional[Dict[str, Any]] = None,
        validate_tools: bool = True,
    ) -> MongoDBBackup:
        settings = connection_settings or BackupFactory._get_env_connection_settings()
        return MongoDBBackup(
            host=settings.get("host"),
            port=settings.get("port"),
            database=settings.get("database"),
            username=settings.get("username"),
            password=settings.get("password"),
            validate_tools=validate_tools,
        )

    @staticmethod
    def get_mongodb_restore_instance(
        connection_settings: Optional[Dict[str, Any]] = None,
        validate_tools: bool = True,
    ) -> MongoDBRestore:
        settings = connection_settings or BackupFactory._get_env_connection_settings()
        return MongoDBRestore(
            host=settings.get("host"),
            port=settings.get("port"),
            database=settings.get("database"),
            username=settings.get("username"),
            password=settings.get("password"),
            validate_tools=validate_tools,
        )

    @staticmethod
    def _get_env_connection_settings() -> Dict[str, Any]:
        if has_app_context():
            config = current_app.config
            databases = config.get("DATABASES", {})
            backup_database = config.get("BACKUP_DATABASE")
            primary_database = config.get("PRIMARY_DATABASE")
        else:
            databases = os.getenv("DATABASES", "{}")
            try:
                databases = json.loads(databases)
            except json.JSONDecodeError as error:
                raise ValueError("DATABASES must contain valid JSON") from error
            backup_database = os.getenv("BACKUP_DATABASE")
            primary_database = os.getenv("PRIMARY_DATABASE")

        settings = BackupFactory._mongodb_settings_from_registry(
            databases, backup_database, primary_database
        )
        if settings is None:
            raise ValueError("No MongoDB connection is configured for backup")
        logger.info(
            "MongoDB backup connection settings: host=%s, port=%s, database=%s",
            settings.get("host", "localhost"),
            settings.get("port", 27017),
            settings.get("database"),
        )
        return settings

    @staticmethod
    def _mongodb_settings_from_registry(
        databases: Any,
        backup_database: Optional[str],
        primary_database: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        if databases is None:
            return None
        if not isinstance(databases, Mapping):
            raise ValueError("DATABASES_CONFIG must be a JSON object")

        mongo_databases = {
            str(name).lower(): settings
            for name, settings in databases.items()
            if isinstance(settings, Mapping)
            and str(settings.get("type", "")).lower() == "mongodb"
        }
        selected_name = backup_database or primary_database
        if selected_name:
            selected = mongo_databases.get(selected_name.lower())
            if selected is not None:
                candidates = [(selected_name.lower(), selected)]
            elif backup_database:
                raise ValueError(
                    f"BACKUP_DATABASE '{backup_database}' is not a MongoDB connection"
                )
            else:
                candidates = []
        else:
            candidates = []

        if not candidates:
            if len(mongo_databases) == 1:
                candidates = list(mongo_databases.items())
            elif len(mongo_databases) > 1:
                raise ValueError(
                    "Set BACKUP_DATABASE when multiple MongoDB connections are configured"
                )
            else:
                return None

        _, connection = candidates[0]
        uri = connection.get("uri", connection.get("url", ""))
        settings = BackupFactory._parse_mongodb_uri(uri) if uri else {}
        settings["host"] = connection.get("host") or settings.get("host", "localhost")
        settings["port"] = int(connection.get("port") or settings.get("port", 27017))
        settings["database"] = connection.get(
            "name", connection.get("database", settings.get("database", "compugit"))
        )
        settings["username"] = connection.get("username") or settings.get("username")
        settings["password"] = connection.get("password") or settings.get("password")
        return settings

    @staticmethod
    def _parse_mongodb_uri(uri: str) -> Dict[str, Any]:
        if not uri:
            return {}
        parsed = urlsplit(uri)
        if parsed.scheme not in {"mongodb", "mongodb+srv"}:
            raise ValueError("MongoDB URI must use mongodb:// or mongodb+srv://")
        settings: Dict[str, Any] = {}
        if parsed.hostname:
            settings["host"] = parsed.hostname
        if parsed.port:
            settings["port"] = parsed.port
        else:
            settings["port"] = 27017
        if parsed.username:
            settings["username"] = unquote(parsed.username)
        if parsed.password:
            settings["password"] = unquote(parsed.password)
        database = parsed.path.lstrip("/").split("?", 1)[0]
        if database:
            settings["database"] = database
        return settings

    @staticmethod
    def create_backup_restore_pair(
        connection_settings: Optional[Dict[str, Any]] = None,
        validate_tools: bool = True,
    ) -> Tuple[MongoDBBackup, MongoDBRestore]:
        return (
            BackupFactory.get_mongodb_backup_instance(
                connection_settings, validate_tools
            ),
            BackupFactory.get_mongodb_restore_instance(
                connection_settings, validate_tools
            ),
        )

    @staticmethod
    def validate_connection_settings(connection_settings: Mapping[str, Any]) -> bool:
        required_fields = ("host", "port", "database")
        missing_fields = [
            field
            for field in required_fields
            if connection_settings.get(field) is None
        ]
        if missing_fields:
            logger.error("Missing MongoDB connection settings: %s", missing_fields)
            return False
        port = connection_settings.get("port")
        if not isinstance(port, int) or isinstance(port, bool) or not 0 < port <= 65535:
            logger.error("Invalid MongoDB port: %s", port)
            return False
        return True


def get_databases(
    config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return DatabaseFactory.get_databases(config)


def get_cache(
    config: Optional[Mapping[str, Any]] = None,
) -> Optional[Redis]:
    settings = config or {}
    if not _cache_enabled(settings):
        return None
    cache_config = _read_object(settings.get("CACHE_DB", {}), "CACHE_DB")
    if str(cache_config.get("type", "")).strip().lower() != "redis":
        raise ValueError("CACHE_DB must use type redis")
    return DatabaseFactory.create_connection(_connection_settings("redis", cache_config))

