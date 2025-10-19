from flask import Blueprint, jsonify
from datetime import datetime
from app.applogger import logger

health_bp = Blueprint('health', __name__)


@health_bp.route('', methods=['GET'])
def health_check():
    """Health check endpoint"""
    logger.info("/health endpoint called")
    return jsonify({
        'message': 'Flask JWT API is running',
        'timestamp': datetime.now().isoformat(),
        'status': 'healthy'
    }), 200
