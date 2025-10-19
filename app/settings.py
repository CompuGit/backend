import os

enable_cors = os.getenv('ENABLE_CORS', 'False').lower() in ('true', '1', 't')
cors_config = {
        "origins": os.getenv('CORS_ORIGINS', '*').split(','),  # e.g., "http://localhost:3000,http://example.com"
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }