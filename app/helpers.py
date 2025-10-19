from flask import jsonify

def json_response(data, status_code=200):
    """
    Helper to create consistent JSON responses and set the status code.
    Rely on Flask's `jsonify` to set the correct Content-Type header.
    """
    response = jsonify(data)
    response.status_code = status_code
    return response