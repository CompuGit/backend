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

        if not data or not data.get('userName') or not data.get('password'):
            logger.error("Missing required fields in registration")
            return jsonify({
                'error': 'Missing required fields',
                'message': 'Username and password are required'
            }), 400

        userName = data['userName'].lower().strip()
        password = data['password']

        # Prefer configured database; fallback to in-memory store for development
        db = current_app.db
        if db:
            existing = db.get_user_by_email_or_username_or_userId(userName)
            if existing:
                logger.error("User already exists: %s", userName)
                return jsonify({
                    'error': 'User already exists',
                    'message': 'userName is already registered'
                }), 409
            
            data['password_hash']  = generate_password_hash(password)
            del data['password']
            db.create_user(data)

            logger.info("User registered successfully: %s", userName)
            return jsonify({
                'message': 'User registered successfully',
                'userName': userName
            }), 201
        else:
            logger.warning("/auth/register - No database configured")
            return jsonify({
                'error': 'No database configured',
                'message': 'User registration is not available'
            }), 503

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

        if not data or not data.get('userName') or not data.get('password'):
            logger.error("Missing credentials in login")
            return jsonify({
                'error': 'Missing credentials',
                'message': 'userName and password are required'
            }), 400

        userName = data['userName'].lower().strip()
        password = data['password']

        db = current_app.db
        if db:
            user = db.get_user_by_email_or_username_or_userId(userName)

            if not user or user.get('canLogin') is False:
                logger.error("Login attempt for non-existent or disabled user: %s", userName)
                return jsonify({
                    'error': 'User cannot login',
                    'message': 'userName does not exist or is disabled'
                }), 401

            if not user or not check_password_hash(user['password_hash'], password):
                logger.error("Invalid login attempt for user: %s", userName)
                return jsonify({
                    'error': 'Invalid credentials',
                    'message': 'userName or password is incorrect'
                }), 401

            access_token = create_access_token(identity=userName)
            refresh_token = create_refresh_token(identity=userName)

            logger.info("User logged in successfully: %s", userName)
            return jsonify({
                'message': 'Login successful',
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': {
                    'userName': userName,
                    'created_at': user.get('created_at') if isinstance(user, dict) else None
                }
            }), 200
        else:
            logger.warning("No database configured, using in-memory store")
            return jsonify({
                'error': 'No database configured',
                'message': 'Login is not available'
            }), 503

    except Exception as e:
        logger.error("Login failed: %s", str(e))
        return jsonify({'error': 'Login failed', 'message': str(e)}), 500


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    try:
        # Check if the refresh token is blacklisted
        jti = get_jwt()['jti']
        if jti in current_app.blacklisted_tokens:
            logger.warning("Attempted to use blacklisted refresh token: %s", jti)
            return jsonify({
                'error': 'Token invalid',
                'message': 'Refresh token has been revoked'
            }), 401

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
        # Get the current access token's jti
        access_jti = get_jwt()['jti']
        blacklisted = current_app.blacklisted_tokens
        blacklisted.add(access_jti)
        
        # Check if refresh token is provided in request body to blacklist it too
        data = request.get_json()
        if data and data.get('refresh_token'):
            try:
                from flask_jwt_extended import decode_token
                refresh_token_data = decode_token(data['refresh_token'])
                refresh_jti = refresh_token_data['jti']
                blacklisted.add(refresh_jti)
                logger.info("Both access and refresh tokens revoked for logout")
                message = 'Successfully logged out. Both tokens have been revoked.'
            except Exception as token_error:
                logger.warning("Failed to decode refresh token during logout: %s", str(token_error))
                message = 'Successfully logged out. Access token revoked, but refresh token could not be processed.'
        else:
            message = 'Successfully logged out. Access token revoked. Please discard your refresh token on the client side.'
        
        logger.info("User logged out, access token revoked: %s", access_jti)
        return jsonify({'message': message}), 200

    except Exception as e:
        logger.error("Logout failed: %s", str(e))
        return jsonify({
            'error': 'Logout failed',
            'message': str(e)
        }), 500
