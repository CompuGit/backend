from flask import Blueprint, jsonify, current_app, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash

from app.applogger import logger

users_bp = Blueprint('users', __name__)

@users_bp.route('profile', methods=['GET'])
@jwt_required()
def get_profile():
    logger.info("/users/profile endpoint called")
    try:
        current_user = get_jwt_identity()
        db = current_app.db

        if hasattr(db, 'get_user_by_email_or_username_or_userId'):
            user_data = db.get_user_by_email_or_username_or_userId(current_user)
            if not user_data:
                return jsonify({
                    'error': 'User not found',
                    'message': 'User profile not found'
                }), 404
            del user_data['password_hash']
            return jsonify(user_data), 200
        else:
            logger.warning("/users/profile - get_user_by_email_or_username_or_userId not implemented in the database")
            return jsonify({
                'error': 'Not implemented',
                'message': 'User profile retrieval is not supported by the current database'
            }), 501

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

    filters = {}
    is_active = request.args.get('isActive')
    if is_active is not None:
        filters['isActive'] = is_active.lower() == 'true'

    try:
        users_list = []
        db = current_app.db
        if hasattr(db, 'get_all_users'):
            for u in db.get_all_users(filters=filters):
                if u['userId'] == 10000 or u.get('userName','').lower() == 'admin':
                    continue  # Skip admin user
                del u['password_hash']
                users_list.append(u)
            logger.info("/users - get_all_users returned %d users", len(users_list))
            return jsonify({'users': users_list, 'total': len(users_list)}), 200
        else:
            logger.warning("/users - get_all_users not implemented in the database")
            return jsonify({
                'error': 'Not implemented',
                'message': 'Listing users is not supported by the current database'
            }), 501
        
    except Exception as e:
        logger.error("List users failed: %s", str(e))
        return jsonify({
            'error': 'Failed to list users',
            'message': str(e)
        }), 500


@users_bp.route('<userId>', methods=['GET'])
@jwt_required()
def get_user(userId:int):
    """Get a specific user by userId"""
    userId = int(userId)
    logger.info("/users/%s GET endpoint called", userId)
    try:
        db = current_app.db
        
        if hasattr(db, 'get_user_by_email_or_username_or_userId'):
            user_data = db.get_user_by_email_or_username_or_userId(userId)
            if not user_data:
                return jsonify({
                    'error': 'User not found',
                    'message': f'User with userId {userId} not found'
                }), 404
            
            # Remove sensitive data
            if 'password_hash' in user_data:
                del user_data['password_hash']
            
            logger.info("/users/%s - User found successfully", userId)
            return jsonify(user_data), 200
        else:
            logger.warning("/users/%s - get_user_by_email_or_username_or_userId not implemented in the database", userId)
            return jsonify({
                'error': 'Not implemented',
                'message': 'User retrieval is not supported by the current database'
            }), 501

    except Exception as e:
        logger.error("Get user failed for userId %s: %s", userId, str(e))
        return jsonify({
            'error': 'Failed to get user',
            'message': str(e)
        }), 500


@users_bp.route('<userId>', methods=['PUT', 'PATCH'])
@jwt_required()
def update_user(userId:int):
    """Update a specific user by userId"""
    userId = int(userId)
    logger.info("/users/%s %s endpoint called", userId, request.method)
    try:
        update_data = request.get_json()
        
        if not update_data:
            return jsonify({
                'error': 'Invalid request',
                'message': 'No JSON data provided'
            }), 400
        
        # Remove sensitive fields that shouldn't be updated directly
        sensitive_fields = ['password_hash']
        for field in sensitive_fields:
            if field in update_data:
                del update_data[field]

        db = current_app.db
        
        if hasattr(db, 'get_user_by_email_or_username_or_userId') and hasattr(db, 'update_user'):
            # First check if user exists
            existing_user = db.get_user_by_email_or_username_or_userId(userId)
            if not existing_user:
                return jsonify({
                    'error': 'User not found',
                    'message': f'User with userId {userId} not found'
                }), 404

            # Update user (using userId as identifier for the database method)
            updated_user = db.update_user(userId, update_data)

            if updated_user:
                logger.info("/users/%s - User updated successfully", userId)
                return jsonify({
                    'message': f'User {userId} updated successfully'
                }), 200
            else:
                return jsonify({
                    'error': 'Update failed',
                    'message': 'Failed to update user'
                }), 500
        else:
            logger.warning("/users/%s - update_user not implemented in the database", userId)
            return jsonify({
                'error': 'Not implemented',
                'message': 'User update is not supported by the current database'
            }), 501

    except Exception as e:
        logger.error("Update user failed for userId %s: %s", userId, str(e))
        return jsonify({
            'error': 'Failed to update user',
            'message': str(e)
        }), 500


@users_bp.route('<userId>', methods=['DELETE'])
@jwt_required()
def delete_user(userId:int):
    """Delete a specific user by userId"""
    userId = int(userId)
    logger.info("/users/%s DELETE endpoint called", userId)
    try:
        db = current_app.db
        
        if hasattr(db, 'get_user_by_email_or_username_or_userId') and hasattr(db, 'delete_user'):
            # First check if user exists
            existing_user = db.get_user_by_email_or_username_or_userId(userId)
            if not existing_user:
                return jsonify({
                    'error': 'User not found',
                    'message': f'User with userId {userId} not found'
                }), 404
            
            # Delete user (using userId as identifier for the database method)
            deleted = db.delete_user(userId)
            
            if deleted:
                logger.info("/users/%s - User deleted successfully", userId)
                return jsonify({
                    'message': f'User {userId} deleted successfully'
                }), 200
            else:
                return jsonify({
                    'error': 'Delete failed',
                    'message': 'Failed to delete user'
                }), 500
        else:
            logger.warning("/users/%s - delete_user not implemented in the database", userId)
            return jsonify({
                'error': 'Not implemented',
                'message': 'User deletion is not supported by the current database'
            }), 501

    except Exception as e:
        logger.error("Delete user failed for userId %s: %s", userId, str(e))
        return jsonify({
            'error': 'Failed to delete user',
            'message': str(e)
        }), 500


@users_bp.route('', methods=['POST'])
@jwt_required()
def create_user():
    """Create a new user"""
    logger.info("/users POST endpoint called")
    try:
        data = request.get_json()
        
        
        if not data:
            return jsonify({
                'error': 'Invalid request',
                'message': 'No JSON data provided'
            }), 400
        
        # Validate required fields
        required_fields = ['userName', 'canLogin']
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return jsonify({
                'error': 'Missing required fields',
                'message': f'The following fields are required: {", ".join(missing_fields)}'
            }), 400
        
        userName = data['userName'].lower().strip()

        db = current_app.db
        
        if hasattr(db, 'get_user_by_email_or_username_or_userId') and hasattr(db, 'create_user'):
            # Check if user already exists
            existing_user = db.get_user_by_email_or_username_or_userId(userName)
            if existing_user:
                return jsonify({
                    'error': 'User already exists',
                    'message': f'User with userName "{userName}" already exists'
                }), 409
            

            data['password_hash'] = generate_password_hash(userName)
            if data.get('password'):
                del data['password'] 
            
            # Create the user
            created_user = db.create_user(data)
            
            if created_user:
                # Remove sensitive data before returning
                if 'password_hash' in created_user:
                    del created_user['password_hash']
                
                logger.info("/users - User created successfully: %s", userName)
                return jsonify({
                    'message': 'User created successfully',
                    'userId': created_user['userId'],
                    'userName': created_user['userName']
                }), 201
            else:
                return jsonify({
                    'error': 'Creation failed',
                    'message': 'Failed to create user'
                }), 500
        else:
            logger.warning("/users - create_user not implemented in the database")
            return jsonify({
                'error': 'Not implemented',
                'message': 'User creation is not supported by the current database'
            }), 501
    
    except Exception as e:
        logger.error("Create user failed: %s", str(e))
        return jsonify({
            'error': 'Failed to create user',
            'message': str(e)
        }), 500
