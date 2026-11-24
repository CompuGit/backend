from flask import current_app
from flask_jwt_extended import get_jwt_identity


def register_authentication_callbacks(jwt):
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        return jwt_payload["jti"] in current_app.extensions["blacklisted_tokens"]


def current_identity():
    return get_jwt_identity()
