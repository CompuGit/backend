from flask import Blueprint, current_app, jsonify
from flask_swagger import swagger
from flask_swagger_ui import get_swaggerui_blueprint

api_doc_bp = Blueprint("api_documentation", __name__)


@api_doc_bp.route("/api_doc_json")
def get_api_doc_json():
    return jsonify(current_app.extensions["swagger_spec"])


def register_swagger(app) -> None:
    spec = swagger(app)
    spec["info"] = {
        "version": app.config["APP_VERSION"],
        "title": app.config["APP_NAME"],
        "description": "CompuGit Backend API Documentation",
        "contact": {"email": "admin@example.com"},
        "license": {"name": "MIT"},
    }
    spec["basePath"] = "/api"
    spec["schemes"] = ["http", "https"]
    spec["securityDefinitions"] = {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": (
                "JWT Authorization header using the Bearer scheme. "
                'Example: "Authorization: Bearer {token}"'
            ),
        }
    }
    app.extensions["swagger_spec"] = spec
    app.register_blueprint(api_doc_bp)
    app.register_blueprint(
        get_swaggerui_blueprint(
            "/swagger",
            "/api_doc_json",
            config={
                "app_name": app.config["APP_NAME"],
                "dom_id": "#swagger-ui",
                "deepLinking": True,
                "showMutatedRequest": True,
                "displayRequestDuration": True,
                "supportedSubmitMethods": [
                    "get",
                    "put",
                    "post",
                    "delete",
                    "options",
                    "head",
                    "patch",
                ],
                "validatorUrl": None,
            },
        )
    )