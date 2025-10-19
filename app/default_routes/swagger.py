from flask_swagger_ui import get_swaggerui_blueprint
import os

# Swagger UI configuration
SWAGGER_URL = '/swagger'
API_URL = '/api_doc_json'

swagger_config = {
    'app_name': os.getenv('APP_NAME', 'CompuGit_Backend'),
    'dom_id': '#swagger-ui',
    'deepLinking': True,
    'showMutatedRequest': True,
    'displayRequestDuration': True,
    'supportedSubmitMethods': ['get', 'put', 'post', 'delete', 'options', 'head', 'patch'],
    'validatorUrl': None
}

swagger_bp = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config=swagger_config
)