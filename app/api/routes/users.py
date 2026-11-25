from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.exceptions import ServiceUnavailable
from werkzeug.security import generate_password_hash

from app.api.services.users import DuplicateIdentityError
from app.core.auth.passwords import password_validation_error
from app.core.auth.authZ import requires_roles
from app.core.logging import logger

users_bp = Blueprint("users", __name__)

USER_UPDATE_FIELDS = {
    "userName",
    "email",
    "name",
    "contact",
    "roles",
    "canLogin",
    "departments",
}


def _public_user(user_data):
    return {key: value for key, value in user_data.items() if key != "password_hash"}


def _preserve_last_admin(service, existing_user, update_data):
    if "admin" not in existing_user.get("roles", []):
        return False
    removes_admin = (
        "roles" in update_data and "admin" not in update_data["roles"]
    )
    disables_admin = update_data.get("canLogin") is False
    return (removes_admin or disables_admin) and service.count_admins() <= 1


@users_bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    try:
        user_data = current_app.extensions["user_service"].get_user(
            get_jwt_identity()
        )
        if not user_data or not user_data.get("canLogin", True):
            return jsonify({"error": "User profile not found"}), 404
        return jsonify(_public_user(user_data)), 200
    except Exception:
        logger.exception("Profile retrieval failed")
        return jsonify({"error": "Profile could not be retrieved"}), 500


@users_bp.route("", methods=["GET"])
@requires_roles("admin")
def list_users():
    is_active = request.args.get("isActive")
    filters = {}
    if is_active is not None:
        if is_active.lower() not in {"true", "false"}:
            return jsonify({"error": "isActive must be true or false"}), 400
        filters["isActive"] = is_active.lower() == "true"

    try:
        limit = request.args.get("limit", default=50, type=int)
        offset = request.args.get("offset", default=0, type=int)
        if limit is None or offset is None:
            return jsonify({"error": "limit and offset must be integers"}), 400
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)
        service = current_app.extensions["user_service"]
        users = service.list_users(filters=filters, limit=limit, offset=offset)
        total = service.count_users(filters=filters)
        return jsonify(
            {
                "users": [_public_user(user) for user in users],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        ), 200
    except Exception:
        logger.exception("User listing failed")
        return jsonify({"error": "Users could not be listed"}), 500


@users_bp.route("/<int:user_id>", methods=["GET"])
@requires_roles("admin")
def get_user(user_id: int):
    try:
        user_data = current_app.extensions["user_service"].get_user(user_id)
        if not user_data:
            return jsonify({"error": "User not found"}), 404
        return jsonify(_public_user(user_data)), 200
    except Exception:
        logger.exception("User retrieval failed for id %s", user_id)
        return jsonify({"error": "User could not be retrieved"}), 500


@users_bp.route("/<int:user_id>", methods=["PUT", "PATCH"])
@requires_roles("admin")
def update_user(user_id: int):
    update_data = request.get_json(silent=True)
    if not isinstance(update_data, dict) or not update_data:
        return jsonify({"error": "A non-empty JSON object is required"}), 400
    if set(update_data) - USER_UPDATE_FIELDS:
        return jsonify({"error": "Unsupported user fields"}), 400
    if "roles" in update_data and (
        not isinstance(update_data["roles"], list)
        or not all(isinstance(role, str) for role in update_data["roles"])
    ):
        return jsonify({"error": "roles must be a list of strings"}), 400
    if "canLogin" in update_data and not isinstance(update_data["canLogin"], bool):
        return jsonify({"error": "canLogin must be a boolean"}), 400
    for field in ("name", "contact"):
        if field in update_data and (
            update_data[field] is not None
            and (
                not isinstance(update_data[field], str)
                or len(update_data[field]) > 200
            )
        ):
            return jsonify({"error": f"{field} must be a string of at most 200 characters"}), 400
    if "departments" in update_data and (
        not isinstance(update_data["departments"], list)
        or not all(isinstance(item, str) for item in update_data["departments"])
    ):
        return jsonify({"error": "departments must be a list of strings"}), 400

    try:
        service = current_app.extensions["user_service"]
        existing_user = service.get_user(user_id)
        if not existing_user:
            return jsonify({"error": "User not found"}), 404
        if _preserve_last_admin(service, existing_user, update_data):
            return jsonify({"error": "The last active administrator cannot be removed"}), 409
        updated_user = service.update_user(user_id, update_data)
        if not updated_user:
            return jsonify({"error": "User update failed"}), 409
        if "canLogin" in update_data and not update_data["canLogin"]:
            current_app.extensions["security_state"].revoke_identity(
                existing_user["userName"]
            )
        logger.info(
            "audit action=user_updated actor=%s target_user_id=%s",
            get_jwt_identity(),
            user_id,
        )
        return jsonify({"message": "User updated successfully"}), 200
    except DuplicateIdentityError:
        return jsonify({"error": "Username or email is already in use"}), 409
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except ServiceUnavailable:
        raise
    except Exception:
        logger.exception("User update failed for id %s", user_id)
        return jsonify({"error": "User could not be updated"}), 500


@users_bp.route("/<int:user_id>", methods=["DELETE"])
@requires_roles("admin")
def delete_user(user_id: int):
    try:
        service = current_app.extensions["user_service"]
        existing_user = service.get_user(user_id)
        if not existing_user:
            return jsonify({"error": "User not found"}), 404
        if (
            "admin" in existing_user.get("roles", [])
            and service.count_admins() <= 1
        ):
            return jsonify({"error": "The last administrator cannot be deleted"}), 409
        deleted = service.delete_user(user_id)
        if not deleted:
            return jsonify({"error": "User deletion failed"}), 409
        current_app.extensions["security_state"].revoke_identity(
            existing_user["userName"]
        )
        logger.info(
            "audit action=user_deleted actor=%s target_user_id=%s",
            get_jwt_identity(),
            user_id,
        )
        return jsonify({"message": "User deleted successfully"}), 200
    except ServiceUnavailable:
        raise
    except Exception:
        logger.exception("User deletion failed for id %s", user_id)
        return jsonify({"error": "User could not be deleted"}), 500


@users_bp.route("", methods=["POST"])
@requires_roles("admin")
def create_user():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400
    if set(data) - {"userName", "email", "password", "roles", "canLogin"}:
        return jsonify({"error": "Unsupported user fields"}), 400
    if not all(data.get(field) for field in ("userName", "email", "password")):
        return jsonify({"error": "Username, email, and password are required"}), 400
    if "roles" in data and (
        not isinstance(data["roles"], list)
        or not all(isinstance(role, str) for role in data["roles"])
    ):
        return jsonify({"error": "roles must be a list of strings"}), 400
    if "canLogin" in data and not isinstance(data["canLogin"], bool):
        return jsonify({"error": "canLogin must be a boolean"}), 400
    password_error = password_validation_error(
        data["password"], current_app.config["MIN_PASSWORD_LENGTH"]
    )
    if password_error:
        return jsonify({"error": password_error}), 400

    try:
        user = current_app.extensions["user_service"].create_user(
            {
                "userName": data["userName"],
                "email": data["email"],
                "password_hash": generate_password_hash(data["password"]),
                "roles": data.get("roles", ["user"]),
                "canLogin": data.get("canLogin", True),
            }
        )
        logger.info(
            "audit action=user_created actor=%s target_user_id=%s",
            get_jwt_identity(),
            user["userId"],
        )
        return jsonify(
            {
                "message": "User created successfully",
                "user": _public_user(user),
            }
        ), 201
    except DuplicateIdentityError:
        return jsonify({"error": "Username or email is already in use"}), 409
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        logger.exception("User creation failed")
        return jsonify({"error": "User could not be created"}), 500
