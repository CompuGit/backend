from flask import Flask, jsonify


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({"error": "Bad request", "message": str(error)}), 400

    @app.errorhandler(401)
    def unauthorized(_error):
        return jsonify(
            {"error": "Unauthorized", "message": "Authentication required"}
        ), 401

    @app.errorhandler(403)
    def forbidden(_error):
        return jsonify(
            {"error": "Forbidden", "message": "Insufficient permissions"}
        ), 403

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(
            {"error": "Not found", "message": "Resource not found"}
        ), 404

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify(
            {
                "error": "Internal server error",
                "message": "Something went wrong",
            }
        ), 500