from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify

from app.core.logging import logger

health_bp = Blueprint("health", __name__)


@health_bp.route("/", methods=["GET"])
def welcome():
    return jsonify(
        {
            "status": "OK",
            "message": (
                f'Welcome to {current_app.config["APP_NAME"]} '
                f'v{current_app.config["APP_VERSION"]}'
            ),
        }
    )


@health_bp.route("/live", methods=["GET"])
def health_check():
    logger.info("/live endpoint called")
    return jsonify(
        {
            "message": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    ), 200


@health_bp.route("/ready", methods=["GET"])
def readiness_check():
    databases = current_app.extensions["databases"]
    try:
        if not all(database.is_connected() for database in databases.values()):
            return jsonify({"status": "not_ready"}), 503
        redis_client = current_app.extensions["redis"]
        if redis_client is not None:
            redis_client.ping()
    except Exception:
        logger.exception("Readiness check failed")
        return jsonify({"status": "not_ready"}), 503
    return jsonify({"status": "ready"}), 200