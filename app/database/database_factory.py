import os
from typing import Optional

from app.database.mongodb import MongoDBConnection
from app.database.sqlalchemy_db import SQLAlchemyConnection
from app.applogger import logger

def get_database() -> Optional[MongoDBConnection | SQLAlchemyConnection]:
    """
    Factory function to get the appropriate database connection based on environment configuration.
    Returns either MongoDBConnection or SQLAlchemyConnection instance.
    """
    db_type = os.getenv('DB_TYPE', 'mongodb').lower()
    
    try:
        if db_type == 'mongodb':
            db = MongoDBConnection()
        elif db_type == 'postgresql':
            db = SQLAlchemyConnection()
        else:
            logger.error(f"Unsupported database type: {db_type}")
            raise ValueError(f"Unsupported database type: {db_type}")
        
        db.connect()
        return db
    except Exception as e:
        logger.error(f"Failed to initialize database connection: {str(e)}")
        raise