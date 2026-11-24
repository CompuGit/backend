from flask import Flask


def register_middleware(app: Flask) -> None:
    @app.after_request
    def set_content_type(response):
        if response.is_json or not response.content_type:
            response.headers["Content-Type"] = "application/json"
        return response