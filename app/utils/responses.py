from flask import jsonify


def json_response(data, status_code=200):
    response = jsonify(data)
    response.status_code = status_code
    return response
