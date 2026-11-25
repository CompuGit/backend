from functools import wraps

from flask import abort, current_app
from flask_jwt_extended import get_jwt_identity, jwt_required


def requires_roles(*roles):
    def decorator(view):
        @wraps(view)
        @jwt_required()
        def wrapped(*args, **kwargs):
            user = current_app.extensions["user_service"].get_user(
                get_jwt_identity()
            )
            if (
                not user
                or not user.get("canLogin", True)
                or not any(role in user.get("roles", []) for role in roles)
            ):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
