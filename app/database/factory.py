from typing import Any, Mapping, Optional

from app.core.logging import logger
from app.database.mongodb import MongoDBConnection
from app.database.sqlalchemy import SQLAlchemyConnection


def get_database(config: Optional[Mapping[str, Any]] = None) -> MongoDBConnection | SQLAlchemyConnection:
    """
    Factory function to get the appropriate database connection based on environment configuration.
    Returns either MongoDBConnection or SQLAlchemyConnection instance.
    """
    settings = config or {}
    db_type = str(settings.get("DB_TYPE", "mongodb")).lower()
    
    try:
        if db_type == 'mongodb':
            db = MongoDBConnection(settings)
        elif db_type == 'postgresql':
            db = SQLAlchemyConnection(settings)
        else:
            logger.error(f"Unsupported database type: {db_type}")
            raise ValueError(f"Unsupported database type: {db_type}")
        
        db.connect()
        return db
    except Exception as e:
        logger.error(f"Failed to initialize database connection: {str(e)}")
        raise