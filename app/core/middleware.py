import uuid

from flask import Flask, current_app, g, request


def register_middleware(app: Flask) -> None:
    @app.before_request
    def assign_request_id():
        g.request_id = uuid.uuid4().hex
        if not request.path.startswith("/backup"):
            request.max_content_length = current_app.config[
                "API_MAX_CONTENT_LENGTH"
            ]

    @app.after_request
    def add_response_headers(response):
        if response.is_json or not response.content_type:
            response.headers["Content-Type"] = "application/json"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-Request-ID"] = g.get("request_id", uuid.uuid4().hex)
        if request.path.startswith(("/auth", "/users")):
            response.headers["Cache-Control"] = "no-store"
        if current_app.config.get("ENV") == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
