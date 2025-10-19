# Only swagger blueprint is available
from app.default_routes.swagger import swagger_bp

def register_default_routes(app):
    # Register Swagger UI blueprint separately
    app.register_blueprint(swagger_bp, url_prefix='/swagger')
        
