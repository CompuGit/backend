from datetime import datetime

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
            "timestamp": datetime.now().isoformat(),
        }
    ), 200