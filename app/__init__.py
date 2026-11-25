from typing import Any, Mapping, Optional

from flask import Flask

from app.api.routes import register_bp_routes
from app.api.services.users import UserService
from app.core.auth.n import register_authentication_callbacks
from app.config import AppSettings
from app.core.errors import register_error_handlers
from app.core.extensions import cors, jwt
from app.core.middleware import register_middleware
from app.core.swagger import register_swagger
from app.database import get_cache, get_databases


def create_app(
    config: Optional[Mapping[str, Any]] = None,
    database: Optional[Any] = None,
) -> Flask:
    app = Flask(__name__)
    settings = AppSettings.from_environment()
    app.config.from_mapping(settings.to_flask_config())
    if config:
        app.config.update(config)
        if "DATABASES" in config:
            configured_databases = config["DATABASES"]
            if "PRIMARY_DATABASE" not in config and configured_databases:
                app.config["PRIMARY_DATABASE"] = next(
                    (
                        str(name).lower()
                        for name, database_config in configured_databases.items()
                        if isinstance(database_config, Mapping)

                    ),
                    "",
                )

    if app.config["ENV"] == "prod" and not app.config["JWT_SECRET_KEY"]:
        raise ValueError("SECRET_KEY must be configured in production")

    jwt.init_app(app)
    register_authentication_callbacks(jwt)
    if app.config["ENABLE_CORS"]:
        cors.init_app(app, **app.config["CORS_CONFIG"])

    app.extensions["blacklisted_tokens"] = set()
    if database is None:
        databases = get_databases(app.config)
        pm_db = databases[app.config["PRIMARY_DATABASE"]]
    else:
        databases = {app.config["PRIMARY_DATABASE"]: database}
        pm_db = database
    app.extensions["cache"] = get_cache(app.config)
    app.extensions["databases"] = databases
    app.extensions["pm_db"] = pm_db
    app.extensions["user_service"] = UserService(pm_db)

    # Keep these aliases for code that imports the Flask application directly.
    app.db = pm_db
    app.blacklisted_tokens = app.extensions["blacklisted_tokens"]


    @app.route("/", methods=["GET"])
    def index():
        return {
            "status": "OK",
            "message": f"Welcome to {app.config['APP_NAME']} v{app.config['APP_VERSION']}"
        }

    register_error_handlers(app)
    register_middleware(app)
    register_bp_routes(app)
    register_swagger(app)
    
    return app