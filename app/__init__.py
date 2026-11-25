import atexit
import re
from typing import Any, Mapping, Optional

import click
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from app.api.routes import register_bp_routes
from app.api.services.users import UserService
from app.config import AppSettings, _positive_duration_seconds
from app.core.auth.n import register_authentication_callbacks
from app.core.auth.passwords import password_validation_error
from app.core.cache import JsonCache
from app.core.errors import register_error_handlers
from app.core.extensions import cors, jwt
from app.core.logging import logger
from app.core.middleware import register_middleware
from app.core.security_state import SecurityState
from app.core.swagger import register_swagger
from app.database import get_cache, get_databases


def _register_admin_command(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option(
        "--password", confirmation_prompt=True, hide_input=True
    )
    def create_admin(username: str, email: str, password: str) -> None:
        """Create the first administrator using an interactive password prompt."""
        error = password_validation_error(
            password, app.config["MIN_PASSWORD_LENGTH"]
        )
        if error:
            raise click.ClickException(error)
        try:
            user = app.extensions["user_service"].create_user(
                {
                    "userName": username,
                    "email": email,
                    "password_hash": generate_password_hash(password),
                    "roles": ["admin"],
                    "canLogin": True,
                }
            )
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Administrator '{user['userName']}' created.")


def create_app(
    config: Optional[Mapping[str, Any]] = None,
    database: Optional[Any] = None,
) -> Flask:
    app = Flask(__name__)
    settings = AppSettings.from_environment(validate=config is None)
    app.config.from_mapping(settings.to_flask_config())
    if config:
        app.config.update(config)
        if "DATABASES" in config:
            configured_databases = config["DATABASES"]
            if "PRIMARY_DATABASE" not in config and configured_databases:
                app.config["PRIMARY_DATABASE"] = str(next(iter(configured_databases))).lower()

    if config and "SECRET_KEY" in config and "JWT_SECRET_KEY" not in config:
        app.config["JWT_SECRET_KEY"] = config["SECRET_KEY"]
    settings = settings.validate_flask_config(app.config)
    app.config["ENV"] = settings.ENV
    app.config["SECRET_KEY"] = settings.SECRET_KEY or "development-only-not-for-production"
    app.config["JWT_SECRET_KEY"] = app.config["SECRET_KEY"]
    app.config["ENABLE_CORS"] = settings.ENABLE_CORS
    app.config["ENABLE_CACHE"] = settings.ENABLE_CACHE
    app.config["CORS_ORIGINS"] = settings.CORS_ORIGINS
    app.config["CORS_SUPPORTS_CREDENTIALS"] = (
        settings.CORS_SUPPORTS_CREDENTIALS
    )
    app.config["ALLOW_PUBLIC_REGISTRATION"] = settings.ALLOW_PUBLIC_REGISTRATION
    app.config["MIN_PASSWORD_LENGTH"] = settings.MIN_PASSWORD_LENGTH
    app.config["AUTO_CREATE_SCHEMA"] = settings.AUTO_CREATE_SCHEMA
    app.config["ENABLE_SWAGGER"] = settings.ENABLE_SWAGGER
    app.config["LOGIN_RATE_LIMIT"] = settings.LOGIN_RATE_LIMIT
    app.config["LOGIN_RATE_WINDOW_SECONDS"] = settings.LOGIN_RATE_WINDOW_SECONDS
    app.config["TRUST_PROXY"] = settings.TRUST_PROXY
    app.config["PROXY_FIX_X_FOR"] = settings.PROXY_FIX_X_FOR
    app.config["PROXY_FIX_X_PROTO"] = settings.PROXY_FIX_X_PROTO
    app.config["PROXY_FIX_X_HOST"] = settings.PROXY_FIX_X_HOST
    app.config["API_MAX_CONTENT_LENGTH"] = settings.API_MAX_CONTENT_LENGTH
    app.config["CORS_CONFIG"] = settings.to_flask_config()["CORS_CONFIG"]

    if settings.TRUST_PROXY:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=settings.PROXY_FIX_X_FOR,
            x_proto=settings.PROXY_FIX_X_PROTO,
            x_host=settings.PROXY_FIX_X_HOST,
        )

    jwt.init_app(app)
    if app.config["ENABLE_CORS"]:
        cors.init_app(app, **app.config["CORS_CONFIG"])

    if database is None:
        databases = get_databases(app.config)
        pm_db = databases[app.config["PRIMARY_DATABASE"]]
    else:
        databases = {app.config["PRIMARY_DATABASE"]: database}
        pm_db = database
    try:
        redis_client = get_cache(app.config)
    except Exception:
        for connection in databases.values():
            disconnect = getattr(connection, "disconnect", None)
            if callable(disconnect):
                try:
                    disconnect()
                except Exception:
                    logger.exception("Database cleanup after startup failure failed")
        raise
    namespace = re.sub(r"[^a-zA-Z0-9_-]", "_", app.config["APP_NAME"]).lower()
    app.extensions["redis"] = redis_client
    app.extensions["cache"] = JsonCache(redis_client, namespace)
    access_ttl = _positive_duration_seconds(
        app.config["JWT_ACCESS_TOKEN_EXPIRES"],
        "JWT_ACCESS_TOKEN_EXPIRES",
    )
    refresh_ttl = _positive_duration_seconds(
        app.config["JWT_REFRESH_TOKEN_EXPIRES"],
        "JWT_REFRESH_TOKEN_EXPIRES",
    )
    app.extensions["security_state"] = SecurityState(
        redis_client,
        namespace,
        int(access_ttl + refresh_ttl + 60),
    )
    app.extensions["databases"] = databases
    app.extensions["pm_db"] = pm_db
    app.extensions["user_service"] = UserService(pm_db)
    register_authentication_callbacks(jwt)

    app.db = pm_db

    @app.route("/", methods=["GET"])
    def index():
        return {
            "status": "OK",
            "message": f"Welcome to {app.config['APP_NAME']} v{app.config['APP_VERSION']}",
        }

    register_error_handlers(app)
    register_middleware(app)
    register_bp_routes(app)
    if settings.ENABLE_SWAGGER:
        register_swagger(app)
    _register_admin_command(app)

    connections_closed = False

    def close_connections() -> None:
        nonlocal connections_closed
        if connections_closed:
            return
        connections_closed = True
        for connection in databases.values():
            disconnect = getattr(connection, "disconnect", None)
            if callable(disconnect):
                try:
                    disconnect()
                except Exception:
                    logger.exception("Database connection shutdown failed")
        if redis_client is not None:
            try:
                redis_client.close()
            except Exception:
                logger.exception("Redis shutdown failed")

    app.extensions["close_connections"] = close_connections
    atexit.register(close_connections)

    return app