from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    jwt_required,
)
from werkzeug.exceptions import ServiceUnavailable
from werkzeug.security import check_password_hash, generate_password_hash

from app.core.auth.authN import current_identity
from app.core.auth.passwords import password_validation_error
from app.api.services.users import DuplicateIdentityError
from app.core.logging import logger

auth_bp = Blueprint("auth", __name__)


def _rate_limited(bucket: str, identity: str) -> bool:
    state = current_app.extensions["security_state"]
    remote_addr = request.remote_addr or "unknown"
    limit = current_app.config["LOGIN_RATE_LIMIT"]
    window = current_app.config["LOGIN_RATE_WINDOW_SECONDS"]
    try:
        return not (
            state.allow_request(f"{bucket}:ip", remote_addr, limit, window)
            and state.allow_request(f"{bucket}:identity", identity, limit, window)
        )
    except Exception as error:
        logger.exception("Authentication rate limiter is unavailable")
        raise ServiceUnavailable(
            "Authentication service is temporarily unavailable"
        ) from error


def _new_token_pair(identity: str):
    claims = current_app.extensions["security_state"].token_claims(identity)
    return (
        create_access_token(identity=identity, additional_claims=claims),
        create_refresh_token(identity=identity, additional_claims=claims),
    )


@auth_bp.route("/register", methods=["POST"])
def register():
    if not current_app.config["ALLOW_PUBLIC_REGISTRATION"]:
        return jsonify({"error": "Registration is disabled"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400
    if set(data) - {"userName", "email", "password"}:
        return jsonify({"error": "Unsupported registration fields"}), 400
    if not all(data.get(field) for field in ("userName", "email", "password")):
        return jsonify(
            {"error": "Username, email, and password are required"}
        ), 400

    username = data["userName"]
    email = data["email"]
    if not isinstance(username, str) or not isinstance(email, str):
        return jsonify({"error": "Username and email must be strings"}), 400
    username = username.strip().lower()
    email = email.strip().lower()
    if not username or not email or len(username) > 80 or len(email) > 254:
        return jsonify({"error": "Username or email is invalid"}), 400
    password_error = password_validation_error(
        data["password"], current_app.config["MIN_PASSWORD_LENGTH"]
    )
    if password_error:
        return jsonify({"error": password_error}), 400
    if _rate_limited("register", f"{username}:{email}"):
        return jsonify({"error": "Too many registration attempts"}), 429

    try:
        user = current_app.extensions["user_service"].create_user(
            {
                "userName": username,
                "email": email,
                "password_hash": generate_password_hash(data["password"]),
                "roles": ["user"],
                "canLogin": True,
            }
        )
    except DuplicateIdentityError:
        return jsonify({"error": "Username or email is already registered"}), 409
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        logger.exception("User registration failed")
        return jsonify({"error": "Registration could not be completed"}), 500

    logger.info("audit action=user_registered user_id=%s", user["userId"])
    return jsonify({"message": "User registered successfully"}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400
    username = data.get("username", data.get("userName", data.get("email")))
    password = data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({"error": "Username and password are required"}), 400

    username = username.strip().lower()
    if not username or not password or len(password) > 1024:
        return jsonify({"error": "Invalid username or password"}), 401
    if _rate_limited("login", username):
        response = jsonify({"error": "Too many login attempts"})
        response.status_code = 429
        response.headers["Retry-After"] = str(
            current_app.config["LOGIN_RATE_WINDOW_SECONDS"]
        )
        return response

    try:
        user = current_app.extensions["user_service"].get_user(username)
        if (
            not user
            or not user.get("canLogin", True)
            or not check_password_hash(user["password_hash"], password)
        ):
            return jsonify({"error": "Invalid username or password"}), 401
        access_token, refresh_token = _new_token_pair(user["userName"])
    except Exception:
        logger.exception("Login could not be completed")
        return jsonify({"error": "Authentication service is unavailable"}), 503

    logger.info("audit action=login_succeeded user_id=%s", user["userId"])
    return jsonify(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "userName": user["userName"],
                "email": user["email"],
                "roles": user["roles"],
            },
        }
    ), 200


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    payload = get_jwt()
    identity = current_identity()
    user = current_app.extensions["user_service"].get_user(identity)
    if not user or not user.get("canLogin", True):
        return jsonify({"error": "Authentication required"}), 401

    state = current_app.extensions["security_state"]
    state.revoke_token(payload["jti"], payload["exp"])
    access_token, refresh_token = _new_token_pair(identity)
    return jsonify(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "message": "Tokens refreshed successfully",
        }
    ), 200


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    payload = get_jwt()
    state = current_app.extensions["security_state"]
    state.revoke_token(payload["jti"], payload["exp"])
    state.revoke_identity(current_identity())

    logger.info("audit action=logout identity=%s", current_identity())
    return jsonify({"message": "Successfully logged out on all devices"}), 200


@auth_bp.route("/pwupdate", methods=["POST"])
@jwt_required()
def change_password():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400
    old_password = data.get("oldPassword")
    new_password = data.get("newPassword")
    if not isinstance(old_password, str) or not isinstance(new_password, str):
        return jsonify({"error": "Current and new passwords are required"}), 400
    password_error = password_validation_error(
        new_password, current_app.config["MIN_PASSWORD_LENGTH"]
    )
    if password_error:
        return jsonify({"error": password_error}), 400

    identity = current_identity()
    try:
        service = current_app.extensions["user_service"]
        user = service.get_user(identity)
        if not user or not check_password_hash(user["password_hash"], old_password):
            return jsonify({"error": "Current password is incorrect"}), 401
        current_app.extensions["security_state"].revoke_identity(identity)
        service.update_user(
            identity,
            {"password_hash": generate_password_hash(new_password)},
        )
    except ServiceUnavailable:
        raise
    except Exception:
        logger.exception("Password update failed")
        return jsonify({"error": "Password update could not be completed"}), 500

    logger.info("audit action=password_changed identity=%s", identity)
    return jsonify({"message": "Password changed; sign in again"}), 200
