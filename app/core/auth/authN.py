from flask import current_app
from flask_jwt_extended import get_jwt_identity
from werkzeug.exceptions import ServiceUnavailable

from app.core.logging import logger


def register_authentication_callbacks(jwt):
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(_jwt_header, jwt_payload):
        try:
            return current_app.extensions["security_state"].is_token_revoked(
                jwt_payload
            )
        except Exception as error:
            logger.exception("Token revocation service is unavailable")
            raise ServiceUnavailable(
                "Authentication state is temporarily unavailable"
            ) from error


def current_identity():
    return get_jwt_identity()
