from flask import Flask, jsonify
import os
from app.default_routes import register_default_routes
from app.routes import register_routes
from flask_swagger import swagger

app = Flask(__name__)

# Configuration
app.config['APP_NAME'] = os.getenv('APP_NAME','CompuGit_Backend')
app.config['APP_VERSION'] = os.getenv('VERSION','1.0.0')

# Initialize swagger
swag = swagger(app)

# Basic error handlers
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
    raise RuntimeError("Failed to register routes. Check route definitions.")