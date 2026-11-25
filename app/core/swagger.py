from pathlib import Path
from typing import Any

import yaml
from flask import Blueprint, current_app, jsonify
from flask_swagger_ui import get_swaggerui_blueprint

api_doc_bp = Blueprint("api_documentation", __name__)


def _load_openapi_spec(spec_path: Path) -> dict[str, Any]:
    spec: Any = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or not isinstance(spec.get("info"), dict):
        raise ValueError(f"Invalid OpenAPI document: {spec_path}")

    route_doc_files = spec.pop("x-route-doc-files", [])
    if not isinstance(route_doc_files, list) or not all(
        isinstance(file_name, str) for file_name in route_doc_files
    ):
        raise ValueError(f"Invalid route document list: {spec_path}")

    paths = spec.setdefault("paths", {})
    components = spec.setdefault("components", {})
    if not isinstance(paths, dict) or not isinstance(components, dict):
        raise ValueError(f"Invalid OpenAPI paths or components: {spec_path}")

    for file_name in route_doc_files:
        route_doc_path = spec_path.parent / file_name
        route_doc: Any = yaml.safe_load(route_doc_path.read_text(encoding="utf-8"))
        if not isinstance(route_doc, dict) or not isinstance(
            route_doc.get("paths"), dict
        ):
            raise ValueError(f"Invalid route document: {route_doc_path}")

        duplicate_paths = paths.keys() & route_doc["paths"].keys()
        if duplicate_paths:
            raise ValueError(
                f"Duplicate paths in {route_doc_path}: {sorted(duplicate_paths)}"
            )
        paths.update(route_doc["paths"])

        route_components = route_doc.get("components", {})
        if not isinstance(route_components, dict):
            raise ValueError(f"Invalid route components: {route_doc_path}")
        for component_type, definitions in route_components.items():
            if not isinstance(definitions, dict):
                raise ValueError(f"Invalid {component_type} components: {route_doc_path}")
            target_definitions = components.setdefault(component_type, {})
            if not isinstance(target_definitions, dict):
                raise ValueError(f"Invalid {component_type} components: {spec_path}")
            duplicate_components = target_definitions.keys() & definitions.keys()
            if duplicate_components:
                raise ValueError(
                    f"Duplicate {component_type} components in {route_doc_path}: "
                    f"{sorted(duplicate_components)}"
                )
            target_definitions.update(definitions)

    return spec


@api_doc_bp.route("/api_doc_json")
def get_api_doc_json():
    return jsonify(current_app.extensions["swagger_spec"])


def register_swagger(app) -> None:
    spec_path = Path(__file__).resolve().parents[1] / "api" / "docs" / "openapi.yaml"
    spec = _load_openapi_spec(spec_path)
    spec["info"]["version"] = app.config["APP_VERSION"]
    spec["info"]["title"] = app.config["APP_NAME"]
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