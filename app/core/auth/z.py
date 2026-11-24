from functools import wraps

from flask import abort
from flask_jwt_extended import get_jwt, jwt_required


def requires_roles(*roles):
    def decorator(view):
        @wraps(view)
        @jwt_required()
        def wrapped(*args, **kwargs):
            user_roles = get_jwt().get("roles", [])
            if not any(role in user_roles for role in roles):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
