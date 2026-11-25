from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from app.core.logging import logger


HTTP_ERROR_MESSAGES = {
    400: ("Bad request", "The request could not be understood"),
    401: ("Unauthorized", "Authentication is required"),
    403: ("Forbidden", "You do not have permission to perform this action"),
    404: ("Not found", "The requested resource was not found"),
    405: ("Method not allowed", "The method is not allowed for this resource"),
    413: ("Payload too large", "The request payload is too large"),
    429: ("Too many requests", "Please wait before retrying"),
    503: ("Service unavailable", "A required service is temporarily unavailable"),
}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        title, message = HTTP_ERROR_MESSAGES.get(
            error.code or 500,
            ("Request failed", "The request could not be completed"),
        )
        return jsonify({"error": title, "message": message}), error.code or 500

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        logger.exception("Unhandled request error", exc_info=error)
        return (
            jsonify(
                {
                    "error": "Internal server error",
                    "message": "The request could not be completed",
                }
            ),
            500,
        )
