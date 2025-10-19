from flask import Flask, jsonify
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from datetime import timedelta
import os
from app.applogger import logger
from app.default_routes import register_default_routes
from app.routes import register_routes
from flask_swagger import swagger
from app.settings import enable_cors, cors_config

app = Flask(__name__)

# Configuration
app.config['APP_NAME'] = os.getenv('APP_NAME','CompuGit_Backend')
app.config['APP_VERSION'] = os.getenv('VERSION','1.0.0')
app.config['JWT_SECRET_KEY'] = os.getenv('SECRET_KEY','')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=int(os.getenv('ACCESS_TOKEN_EXPIRES', 1)))
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=int(os.getenv('REFRESH_TOKEN_EXPIRES', 1)))

# Initialize extensions
jwt = JWTManager(app)
CORS(app, **cors_config) if enable_cors else None
swag = swagger(app)

# In-memory storage for demo can access them via `current_app` at runtime and avoid circular imports.
app.users_db = {}
app.blacklisted_tokens = set()

# JWT token blacklist checker
@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    jti = jwt_payload['jti']
    # Use the store attached to the Flask app instance to avoid
    # referencing module-level names which can cause circular import issues.
    return jti in getattr(app, 'blacklisted_tokens', set())

# Error handlers
@app.errorhandler(400)
def bad_request(error):
    return jsonify({'error': 'Bad request', 'message': str(error)}), 400

@app.errorhandler(401)
def unauthorized(error):
    return jsonify({
        'error': 'Unauthorized',
        'message': 'Authentication required'
    }), 401

@app.errorhandler(403)
def forbidden(error):
    return jsonify({
        'error': 'Forbidden',
        'message': 'Insufficient permissions'
    }), 403

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Not found',
        'message': 'Resource not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'error': 'Internal server error',
        'message': 'Something went wrong'
    }), 500

@app.after_request
def set_content_type(response):
    """
    Ensure we don't accidentally override non-JSON responses.
    Only set Content-Type to application/json when Flask already
    recognizes the response as JSON (response.is_json) or when
    the Content-Type is empty.
    """
    try:
        # response.is_json is True for responses created with jsonify
        if getattr(response, 'is_json', False) or not response.content_type:
            response.headers['Content-Type'] = 'application/json'
    except Exception:
        # If anything goes wrong, don't modify the response
        pass

    return response

@app.route('/api_doc_json')
def get_api_doc_json():
    """
    Generate Swagger API documentation
    """
    swag['info'] = {
        'version': app.config['APP_VERSION'],
        'title': app.config['APP_NAME'],
        'description': 'CompuGit Backend API Documentation',
        'contact': {
            'email': 'admin@example.com'
        },
        'license': {
            'name': 'MIT',
        }
    }
    swag['basePath'] = '/api'
    swag['schemes'] = ['http', 'https']
    swag['securityDefinitions'] = {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'JWT Authorization header using the Bearer scheme. Example: "Authorization: Bearer {token}"'
        }
    }
    return jsonify(swag)

@app.route('/', methods=['GET'])
def welcome():
    return jsonify({
        'status': 'OK',
        'message': f'Welcome to {app.config["APP_NAME"]} API v{app.config["APP_VERSION"]}'
    })

# Register route blueprints from the routes package
try:
    register_default_routes(app)
    register_routes(app)
except Exception:
    logger.warning("Failed to register route blueprints; check app.routes package")