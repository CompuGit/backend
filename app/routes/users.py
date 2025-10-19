from flask import Blueprint, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime

from app.applogger import logger

users_bp = Blueprint('users', __name__)


def _get_users_db():
    return current_app.users_db

@users_bp.route('profile', methods=['GET'])
@jwt_required()
def get_profile():
    logger.info("/users/profile endpoint called")
    try:
        current_user = get_jwt_identity()
        user_data = _get_users_db().get(current_user)

        if not user_data:
            return jsonify({
                'error': 'User not found',
                'message': 'User profile not found'
            }), 404

        return jsonify({
            'profile': {
                'email': current_user,
                'created_at': user_data['created_at']
            }
        }), 200

    except Exception as e:
        logger.error("Get profile failed: %s", str(e))
        return jsonify({
            'error': 'Failed to get profile',
            'message': str(e)
        }), 500


@users_bp.route('', methods=['GET'])
@jwt_required()
def list_users():
    logger.info("/users endpoint called")
    try:
        users_list = []
        for email, user_data in _get_users_db().items():
            users_list.append({
                'email': email,
                'created_at': user_data['created_at']
            })

        return jsonify({'users': users_list, 'total': len(users_list)}), 200

    except Exception as e:
        logger.error("List users failed: %s", str(e))
        return jsonify({
            'error': 'Failed to list users',
            'message': str(e)
        }), 500
