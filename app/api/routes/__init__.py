from app.api.routes.health import health_bp
from app.api.routes.auth import auth_bp
from app.api.routes.backup import backup_bp
from app.api.routes.users import users_bp

__all__ = ["health_bp", "auth_bp", "backup_bp", "users_bp"]

def register_bp_routes(app):
    blueprints = map(lambda bp: (eval(bp), '/'+bp.split('_')[0]), __all__)

    for blueprint, url_prefix in blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)