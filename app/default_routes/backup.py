import os
import tempfile
from flask import Blueprint, jsonify, request, send_file, current_app
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage

from app.database.backup_factory import BackupFactory
from app.applogger import logger

backup_bp = Blueprint('backup', __name__)


def check_tools_and_log():
    """Check MongoDB tools availability and log status"""
    try:
        tools_status = BackupFactory.check_tools_availability()
        if not all(tools_status.values()):
            missing = [tool for tool, available in tools_status.items() if not available]
            logger.warning(f"MongoDB tools not available: {missing}")
            return False, f"Required MongoDB tools not installed: {', '.join(missing)}. Please install mongodb-database-tools package."
        return True, "MongoDB tools are available"
    except Exception as e:
        logger.error(f"Error checking MongoDB tools: {e}")
        return False, f"Error checking MongoDB tools: {e}"


# Helper function to parse query filters
def parse_query_filters():
    """Parse query parameters into MongoDB filters"""
    filters = {}
    
    # Common filter parameters (Flask returns None if conversion fails)
    limit = request.args.get('limit', type=int)
    skip = request.args.get('skip', type=int)
    
    # Add limit and skip to filters if provided
    if limit is not None and limit > 0:
        filters['limit'] = limit
    if skip is not None and skip >= 0:
        filters['skip'] = skip
    
    # Date range filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Custom query filter (JSON string)
    query = request.args.get('query')
    if query:
        try:
            import json
            query_filters = json.loads(query)
            if isinstance(query_filters, dict):
                filters.update(query_filters)
            else:
                raise ValueError("Query parameter must be a JSON object")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in query parameter: {str(e)}")
    
    # Date range filter for documents with 'createdAt' field
    if start_date or end_date:
        date_filter = {}
        if start_date:
            try:
                from datetime import datetime
                # Handle both formats: with and without 'Z'
                if start_date.endswith('Z'):
                    start_date = start_date[:-1] + '+00:00'
                elif not ('+' in start_date or start_date.endswith('Z')):
                    start_date = start_date + '+00:00'
                date_filter['$gte'] = datetime.fromisoformat(start_date)
            except ValueError as e:
                raise ValueError(f"Invalid start_date format: {str(e)}. Use ISO 8601 format")
        
        if end_date:
            try:
                from datetime import datetime
                # Handle both formats: with and without 'Z'
                if end_date.endswith('Z'):
                    end_date = end_date[:-1] + '+00:00'
                elif not ('+' in end_date or end_date.endswith('Z')):
                    end_date = end_date + '+00:00'
                date_filter['$lte'] = datetime.fromisoformat(end_date)
            except ValueError as e:
                raise ValueError(f"Invalid end_date format: {str(e)}. Use ISO 8601 format")
        
        if date_filter:
            filters['createdAt'] = date_filter
    
    return filters

def validate_mongodb_file(file: FileStorage) -> bool:
    """Validate uploaded file is a MongoDB backup file"""
    if not file:
        return False
    
    filename = secure_filename(file.filename)
    if not filename:
        return False
    
    # Check file extension
    allowed_extensions = {'.tar.gz', '.tgz', '.bson'}
    if not any(filename.endswith(ext) for ext in allowed_extensions):
        return False
    
    return True


# Database Info Routes
@backup_bp.route('dbinfo', methods=['GET'])
@jwt_required()
def get_database_info():
    """Get database information including host, port, database name, and collections"""
    logger.info("/backup/dbinfo endpoint called")
    
    try:
        backup_instance = BackupFactory.get_mongodb_backup_instance()
        db_info = backup_instance.get_database_info()
        
        return jsonify({
            'success': True,
            'data': db_info
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get database info: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get database info',
            'message': str(e)
        }), 500


# Backup Routes
@backup_bp.route('', methods=['GET'])
@jwt_required()
def backup_full_database():
    """Create full database backup with optional filters"""
    logger.info("/backup endpoint called for full database backup")
    
    # Check if MongoDB tools are available
    tools_available, tools_message = check_tools_and_log()
    if not tools_available:
        return jsonify({
            'success': False,
            'error': 'MongoDB tools not available',
            'message': tools_message,
            'installation_guide': {
                'ubuntu_debian': 'sudo apt-get install mongodb-database-tools',
                'centos_rhel': 'sudo yum install mongodb-database-tools',
                'macos': 'brew install mongodb/brew/mongodb-database-tools'
            }
        }), 503  # Service Unavailable
    
    try:
        # Parse query filters
        filters = parse_query_filters()
        
        # Create backup instance (skip validation since we already checked)
        backup_instance = BackupFactory.get_mongodb_backup_instance(validate_tools=False)
        
        # Create backup
        backup_path = backup_instance.backup_database(filters=filters if filters else None)
        
        # Send file as download
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=f"mongodb_full_backup_{backup_instance.database}_{int(__import__('time').time())}.tar.gz",
            mimetype='application/gzip'
        )
        
    except ValueError as e:
        logger.error(f"Invalid parameters for backup: {e}")
        return jsonify({
            'success': False,
            'error': 'Invalid parameters',
            'message': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Failed to create database backup: {e}")
        error_message = str(e)
        status_code = 503 if "mongodb-database-tools" in error_message else 500
        
        return jsonify({
            'success': False,
            'error': 'Failed to create backup',
            'message': error_message
        }), status_code


@backup_bp.route('<collection>', methods=['GET'])
@jwt_required()
def backup_collection(collection):
    """Create backup of specific collection with optional filters"""
    logger.info(f"/backup/{collection} endpoint called for collection backup")
    
    # Check if MongoDB tools are available
    tools_available, tools_message = check_tools_and_log()
    if not tools_available:
        return jsonify({
            'success': False,
            'error': 'MongoDB tools not available',
            'message': tools_message,
            'installation_guide': {
                'ubuntu_debian': 'sudo apt-get install mongodb-database-tools',
                'centos_rhel': 'sudo yum install mongodb-database-tools',
                'macos': 'brew install mongodb/brew/mongodb-database-tools'
            }
        }), 503  # Service Unavailable
    
    try:
        # Validate collection name
        if not collection or not collection.replace('_', '').isalnum():
            raise ValueError("Invalid collection name")
        
        # Parse query filters
        filters = parse_query_filters()
        
        # Create backup instance (skip validation since we already checked)
        backup_instance = BackupFactory.get_mongodb_backup_instance(validate_tools=False)
        
        # Create collection backup
        backup_path = backup_instance.backup_collection(
            collection=collection,
            filters=filters if filters else None
        )
        
        # Send file as download
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=f"mongodb_collection_backup_{collection}_{int(__import__('time').time())}.tar.gz",
            mimetype='application/gzip'
        )
        
    except ValueError as e:
        logger.error(f"Invalid parameters for collection backup: {e}")
        return jsonify({
            'success': False,
            'error': 'Invalid parameters',
            'message': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Failed to create collection backup: {e}")
        error_message = str(e)
        status_code = 503 if "mongodb-database-tools" in error_message else 500
        
        return jsonify({
            'success': False,
            'error': 'Failed to create backup',
            'message': error_message
        }), status_code


# Restore Routes
@backup_bp.route('restore', methods=['POST'])
@jwt_required()
def restore_full_database():
    """Restore full database from uploaded MongoDB backup file"""
    logger.info("/backup/restore endpoint called for full database restore")
    
    # Check if MongoDB tools are available
    tools_available, tools_message = check_tools_and_log()
    if not tools_available:
        return jsonify({
            'success': False,
            'error': 'MongoDB tools not available',
            'message': tools_message,
            'installation_guide': {
                'ubuntu_debian': 'sudo apt-get install mongodb-database-tools',
                'centos_rhel': 'sudo yum install mongodb-database-tools',
                'macos': 'brew install mongodb/brew/mongodb-database-tools'
            }
        }), 503  # Service Unavailable
    
    try:
        # Check if file is uploaded
        if 'restore_file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file uploaded',
                'message': 'MongoDB backup file is required'
            }), 400
        
        file = request.files['restore_file']
        
        # Validate uploaded file
        if not validate_mongodb_file(file):
            return jsonify({
                'success': False,
                'error': 'Invalid file',
                'message': 'Please upload a valid MongoDB backup file (.tar.gz, .tgz, or .bson)'
            }), 400
        
        # Get drop_existing parameter
        drop_existing = request.form.get('drop_existing') == True
        
        # Save uploaded file to temporary location
        temp_dir = tempfile.mkdtemp(prefix='mongodb_restore_upload_')
        file_path = os.path.join(temp_dir, secure_filename(file.filename))
        file.save(file_path)
        
        try:
            # Create restore instance (skip validation since we already checked)
            restore_instance = BackupFactory.get_mongodb_restore_instance(validate_tools=False)
            
            # Restore database
            success = restore_instance.restore_database(
                archive_path=file_path,
                drop_existing=drop_existing
            )
            
            if success:
                return jsonify({
                    'success': True,
                    'message': 'Database restored successfully',
                    'dropped_existing': drop_existing
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'error': 'Restore failed',
                    'message': 'Database restore operation failed'
                }), 500
                
        finally:
            # Clean up temporary file
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except Exception:
                pass
        
    except Exception as e:
        logger.error(f"Failed to restore database: {e}")
        error_message = str(e)
        status_code = 503 if "mongodb-database-tools" in error_message else 500
        
        return jsonify({
            'success': False,
            'error': 'Failed to restore database',
            'message': error_message
        }), status_code


@backup_bp.route('restore/<collection>', methods=['POST'])
@jwt_required()
def restore_collection(collection):
    """Restore specific collection from uploaded MongoDB backup file"""
    logger.info(f"/backup/restore/{collection} endpoint called for collection restore")
    
    # Check if MongoDB tools are available
    tools_available, tools_message = check_tools_and_log()
    if not tools_available:
        return jsonify({
            'success': False,
            'error': 'MongoDB tools not available',
            'message': tools_message,
            'installation_guide': {
                'ubuntu_debian': 'sudo apt-get install mongodb-database-tools',
                'centos_rhel': 'sudo yum install mongodb-database-tools',
                'macos': 'brew install mongodb/brew/mongodb-database-tools'
            }
        }), 503  # Service Unavailable
    
    try:
        # Validate collection name
        if not collection or not collection.replace('_', '').isalnum():
            return jsonify({
                'success': False,
                'error': 'Invalid collection name',
                'message': 'Collection name can only contain alphanumeric characters and underscores'
            }), 400
        
        # Check if file is uploaded
        if 'restore_file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file uploaded',
                'message': 'MongoDB backup file is required'
            }), 400
        
        file = request.files['restore_file']
        
        # Validate uploaded file
        if not validate_mongodb_file(file):
            return jsonify({
                'success': False,
                'error': 'Invalid file',
                'message': 'Please upload a valid MongoDB backup file (.tar.gz, .tgz, or .bson)'
            }), 400
        
        # Get drop_existing parameter
        drop_existing = request.form.get('drop_existing') == True
        
        # Save uploaded file to temporary location
        temp_dir = tempfile.mkdtemp(prefix=f'mongodb_restore_{collection}_upload_')
        file_path = os.path.join(temp_dir, secure_filename(file.filename))
        file.save(file_path)
        
        try:
            # Create restore instance (skip validation since we already checked)
            restore_instance = BackupFactory.get_mongodb_restore_instance(validate_tools=False)
            
            # Restore collection
            success = restore_instance.restore_collection(
                collection=collection,
                archive_path=file_path,
                drop_existing=drop_existing
            )
            
            if success:
                return jsonify({
                    'success': True,
                    'message': f'Collection {collection} restored successfully',
                    'collection': collection,
                    'dropped_existing': drop_existing
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'error': 'Restore failed',
                    'message': f'Collection {collection} restore operation failed'
                }), 500
                
        finally:
            # Clean up temporary file
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except Exception:
                pass
        
    except Exception as e:
        logger.error(f"Failed to restore collection {collection}: {e}")
        error_message = str(e)
        status_code = 503 if "mongodb-database-tools" in error_message else 500
        
        return jsonify({
            'success': False,
            'error': 'Failed to restore collection',
            'message': error_message
        }), status_code


# Health check endpoint
@backup_bp.route('status', methods=['GET'])
@jwt_required()
def backup_restore_status():
    """Check backup/restore service status"""
    logger.info("/backup/status endpoint called")
    
    try:
        # Check MongoDB tools availability
        tools_status = BackupFactory.check_tools_availability()
        tools_available = all(tools_status.values())
        
        if not tools_available:
            missing_tools = [tool for tool, available in tools_status.items() if not available]
            return jsonify({
                'success': False,
                'status': 'tools_unavailable',
                'message': f'MongoDB tools not available: {", ".join(missing_tools)}',
                'tools_status': tools_status,
                'installation_guide': {
                    'ubuntu_debian': 'sudo apt-get install mongodb-database-tools',
                    'centos_rhel': 'sudo yum install mongodb-database-tools',
                    'macos': 'brew install mongodb/brew/mongodb-database-tools'
                }
            }), 503
        
        # Test connection by getting database info (skip tool validation)
        backup_instance = BackupFactory.get_mongodb_backup_instance(validate_tools=False)
        db_info = backup_instance.get_database_info()
        
        return jsonify({
            'success': True,
            'status': 'operational',
            'message': 'Backup and restore service is fully operational',
            'tools_status': tools_status,
            'database': {
                'host': db_info['host'],
                'port': db_info['port'],
                'database': db_info['database'],
                'collections_count': len(db_info['collections'])
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Backup/restore service status check failed: {e}")
        
        # Check if it's a tools issue
        tools_status = BackupFactory.check_tools_availability()
        tools_available = all(tools_status.values())
        
        if not tools_available:
            missing_tools = [tool for tool, available in tools_status.items() if not available]
            return jsonify({
                'success': False,
                'status': 'tools_unavailable',
                'message': f'MongoDB tools not available: {", ".join(missing_tools)}',
                'tools_status': tools_status,
                'error': str(e)
            }), 503
        else:
            return jsonify({
                'success': False,
                'status': 'error',
                'message': 'Backup and restore service is not available',
                'tools_status': tools_status,
                'error': str(e)
            }), 500