from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (create_access_token, create_refresh_token,
                                jwt_required, get_jwt_identity, get_jwt)
from datetime import datetime
from app.applogger import logger

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()

        if not data or not data.get('email') or not data.get('password'):
            logger.error("Missing required fields in registration")
            return jsonify({
                'error': 'Missing required fields',
                'message': 'Email and password are required'
            }), 400

        email = data['email'].lower().strip()
        password = data['password']

        users_db = current_app.users_db

        if email in users_db:
            logger.error("User already exists: %s", email)
            return jsonify({
                'error': 'User already exists',
                'message': 'Email is already registered'
            }), 409

        users_db[email] = {
            'email': email,
            'password_hash': generate_password_hash(password),
            'created_at': datetime.utcnow().isoformat()
        }

        logger.info("User registered successfully: %s", email)
        return jsonify({
            'message': 'User registered successfully',
            'email': email
        }), 201

    except Exception as e:
        logger.error("Registration failed: %s", str(e))
        return jsonify({
            'error': 'Registration failed',
            'message': str(e)
        }), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()

        if not data or not data.get('email') or not data.get('password'):
            logger.error("Missing credentials in login")
            return jsonify({
                'error': 'Missing credentials',
                'message': 'Email and password are required'
            }), 400

        email = data['email'].lower().strip()
        password = data['password']

        users_db = current_app.users_db
        user = users_db.get(email)

        if not user or not check_password_hash(user['password_hash'], password):
            logger.error("Invalid login attempt for user: %s", email)
            return jsonify({
                'error': 'Invalid credentials',
                'message': 'Email or password is incorrect'
            }), 401

        access_token = create_access_token(identity=email)
        refresh_token = create_refresh_token(identity=email)

        logger.info("User logged in successfully: %s", email)
        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': {
                'email': email,
                'created_at': user['created_at']
            }
        }), 200

    except Exception as e:
        logger.error("Login failed: %s", str(e))
        return jsonify({'error': 'Login failed', 'message': str(e)}), 500


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    try:
        current_user = get_jwt_identity()
        new_token = create_access_token(identity=current_user)

        logger.info("Token refreshed for user: %s", current_user)
        return jsonify({
            'access_token': new_token,
            'message': 'Token refreshed successfully'
        }), 200

    except Exception as e:
        logger.error("Token refresh failed: %s", str(e))
        return jsonify({
            'error': 'Token refresh failed',
            'message': str(e)
        }), 500


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    try:
        jti = get_jwt()['jti']
        # Attach blacklisted tokens to the app instance
        blacklisted = current_app.blacklisted_tokens
        blacklisted.add(jti)

        logger.info("User logged out, token revoked: %s", jti)
        return jsonify({'message': 'Successfully logged out'}), 200

    except Exception as e:
        logger.error("Logout failed: %s", str(e))
        return jsonify({
            'error': 'Logout failed',
            'message': str(e)
        }), 500
