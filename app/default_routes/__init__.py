from app.applogger import logger

# Import all blueprints here
from app.default_routes.swagger import swagger_bp
from app.default_routes.auth import auth_bp
from app.default_routes.backup import backup_bp

def register_default_routes(app):
    # Register Swagger UI blueprint separately
    app.register_blueprint(auth_bp, url_prefix='/auth')
    logger.info("Registered auth route: /auth")
    
    # Register Swagger UI blueprint separately
    app.register_blueprint(swagger_bp, url_prefix='/swagger')
    logger.info("Registered SwaggerUI route: /swagger")
    
    # Register Backup blueprint separately
    app.register_blueprint(backup_bp, url_prefix='/backup')
    logger.info("Registered backup route: /backup")