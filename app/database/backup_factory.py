import os
from typing import Optional, Union, Dict, Any
from app.database.mongodb_br import MongoDBBackup, MongoDBRestore, check_mongodb_tools, validate_mongodb_tools
from app.applogger import logger


class BackupFactory:
    """Factory class for creating backup and restore instances"""
    
    @staticmethod
    def check_tools_availability() -> Dict[str, bool]:
        """
        Check availability of MongoDB database tools
        
        Returns:
            Dictionary with tool availability status
        """
        return check_mongodb_tools()
    
    @staticmethod
    def get_mongodb_backup_instance(connection_settings: Dict[str, Any] = None, 
                                   validate_tools: bool = True) -> MongoDBBackup:
        """
        Create MongoDB backup instance with connection settings
        
        Args:
            connection_settings: Optional dict with connection parameters
                                Can include: host, port, database, username, password
            validate_tools: Whether to validate MongoDB tools availability
        
        Returns:
            MongoDBBackup instance
            
        Raises:
            Exception: If tools validation fails and validate_tools is True
        """
        if connection_settings is None:
            # Get connection settings from environment variables
            connection_settings = BackupFactory._get_env_connection_settings()
        
        return MongoDBBackup(
            host=connection_settings.get('host'),
            port=connection_settings.get('port'),
            database=connection_settings.get('database'),
            username=connection_settings.get('username'),
            password=connection_settings.get('password'),
            validate_tools=validate_tools
        )
    
    @staticmethod
    def get_mongodb_restore_instance(connection_settings: Dict[str, Any] = None,
                                    validate_tools: bool = True) -> MongoDBRestore:
        """
        Create MongoDB restore instance with connection settings
        
        Args:
            connection_settings: Optional dict with connection parameters
                                Can include: host, port, database, username, password
            validate_tools: Whether to validate MongoDB tools availability
        
        Returns:
            MongoDBRestore instance
            
        Raises:
            Exception: If tools validation fails and validate_tools is True
        """
        if connection_settings is None:
            # Get connection settings from environment variables
            connection_settings = BackupFactory._get_env_connection_settings()
        
        return MongoDBRestore(
            host=connection_settings.get('host'),
            port=connection_settings.get('port'),
            database=connection_settings.get('database'),
            username=connection_settings.get('username'),
            password=connection_settings.get('password'),
            validate_tools=validate_tools
        )
    
    @staticmethod
    def _get_env_connection_settings() -> Dict[str, Any]:
        """
        Extract MongoDB connection settings from environment variables
        Use the same variables as the main MongoDB connection
        
        Returns:
            Dictionary with connection settings
        """
        settings = {}
        
        # Use the same environment variables as the main MongoDB connection
        db_uri = os.getenv('DB_URI', 'mongodb://localhost:27017')
        db_name = os.getenv('DB_NAME', 'compugit')
        username = os.getenv('DB_USERNAME')
        password = os.getenv('DB_PASSWORD')
        
        # Parse the URI to extract host and port
        if db_uri:
            parsed_settings = BackupFactory._parse_mongodb_uri(db_uri)
            settings.update(parsed_settings)
        
        # Override with explicit settings if provided
        db_host = os.getenv('DB_HOST')
        db_port = os.getenv('DB_PORT')
        
        if db_host:
            settings['host'] = db_host
        if db_port:
            settings['port'] = int(db_port)
        
        # Set database name and credentials
        settings['database'] = db_name
        
        # Only set username/password if both are provided and non-empty
        if username and password and username.strip() and password.strip():
            settings['username'] = username.strip()
            settings['password'] = password.strip()
        else:
            # Don't use credentials if not both are provided or if they are empty
            settings['username'] = None
            settings['password'] = None
        
        logger.info(f"MongoDB backup connection settings: host={settings.get('host', 'localhost')}, "
                   f"port={settings.get('port', 27017)}, database={settings.get('database')}")
        
        return settings
    
    @staticmethod
    def _parse_mongodb_uri(uri: str) -> Dict[str, Any]:
        """
        Parse MongoDB URI to extract connection details
        
        Args:
            uri: MongoDB connection URI
            
        Returns:
            Dictionary with extracted connection settings
        """
        settings = {}
        
        try:
            if uri.startswith('mongodb://'):
                uri_part = uri.replace('mongodb://', '')
                
                # Check for credentials
                if '@' in uri_part:
                    credentials, host_part = uri_part.split('@', 1)
                    if ':' in credentials:
                        username, password = credentials.split(':', 1)
                        settings['username'] = username
                        settings['password'] = password
                else:
                    host_part = uri_part
                
                # Parse host and port
                if '/' in host_part:
                    host_port, database_part = host_part.split('/', 1)
                    # Extract database name if provided in URI
                    if database_part:
                        settings['database'] = database_part.split('?')[0]  # Remove query params
                else:
                    host_port = host_part
                
                if ':' in host_port:
                    host, port_str = host_port.split(':', 1)
                    settings['host'] = host
                    settings['port'] = int(port_str)
                else:
                    settings['host'] = host_port
                    settings['port'] = 27017  # Default MongoDB port
                    
        except Exception as e:
            logger.warning(f"Failed to parse MongoDB URI: {e}")
            # Return default localhost settings
            settings = {'host': 'localhost', 'port': 27017}
        
        return settings
    
    @staticmethod
    def create_backup_restore_pair(connection_settings: Dict[str, Any] = None,
                                  validate_tools: bool = True) -> tuple[MongoDBBackup, MongoDBRestore]:
        """
        Create both backup and restore instances with same connection settings
        
        Args:
            connection_settings: Optional dict with connection parameters
            validate_tools: Whether to validate MongoDB tools availability
        
        Returns:
            Tuple of (MongoDBBackup, MongoDBRestore) instances
            
        Raises:
            Exception: If tools validation fails and validate_tools is True
        """
        backup_instance = BackupFactory.get_mongodb_backup_instance(connection_settings, validate_tools)
        restore_instance = BackupFactory.get_mongodb_restore_instance(connection_settings, validate_tools)
        
        return backup_instance, restore_instance
    
    @staticmethod
    def validate_connection_settings(connection_settings: Dict[str, Any]) -> bool:
        """
        Validate MongoDB connection settings
        
        Args:
            connection_settings: Dictionary with connection parameters
            
        Returns:
            True if settings are valid
        """
        required_fields = ['host', 'port', 'database']
        
        for field in required_fields:
            if field not in connection_settings or connection_settings[field] is None:
                logger.error(f"Missing required connection setting: {field}")
                return False
        
        # Validate port is integer
        try:
            port = connection_settings['port']
            if not isinstance(port, int) or port <= 0 or port > 65535:
                logger.error(f"Invalid port number: {port}")
                return False
        except (ValueError, TypeError):
            logger.error(f"Port must be a valid integer")
            return False
        
        return True