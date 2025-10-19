from app.applogger import logger

# Import all blueprints here
from app.routes.health import health_bp
from app.routes.users import users_bp

__all__ = ["health_bp", "users_bp"]

def register_routes(app):
    blueprints = map(lambda bp: (eval(bp), '/'+bp.split('_')[0]), __all__)

    for blueprint, url_prefix in blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)
        logger.info("Registered %s route: %s", blueprint.name, url_prefix)

        