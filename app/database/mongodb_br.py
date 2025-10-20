import os
import subprocess
import tempfile
import shutil
from typing import Optional, Dict, Any, List
from datetime import datetime
import pymongo
from bson import json_util
import json

from app.applogger import logger


def check_mongodb_tools() -> Dict[str, bool]:
    """
    Check if MongoDB database tools are installed and available
    
    Returns:
        Dictionary with tool availability status
    """
    tools_status = {}
    
    for tool in ['mongodump', 'mongorestore']:
        try:
            result = subprocess.run(['which', tool], capture_output=True, text=True)
            tools_status[tool] = result.returncode == 0
            if tools_status[tool]:
                logger.info(f"{tool} is available at: {result.stdout.strip()}")
            else:
                logger.warning(f"{tool} is not installed or not in PATH")
        except Exception as e:
            logger.error(f"Error checking {tool} availability: {e}")
            tools_status[tool] = False
    
    return tools_status


def validate_mongodb_tools(required_tools: List[str] = None) -> bool:
    """
    Validate that required MongoDB tools are available
    
    Args:
        required_tools: List of required tools (default: ['mongodump', 'mongorestore'])
    
    Returns:
        True if all required tools are available
    
    Raises:
        Exception: If required tools are not available
    """
    if required_tools is None:
        required_tools = ['mongodump', 'mongorestore']
    
    tools_status = check_mongodb_tools()
    missing_tools = [tool for tool in required_tools if not tools_status.get(tool, False)]
    
    if missing_tools:
        error_msg = (
            f"Required MongoDB tools not found: {', '.join(missing_tools)}. "
            f"Please install mongodb-database-tools package. "
            f"Installation instructions: "
            f"Ubuntu/Debian: sudo apt-get install mongodb-database-tools, "
            f"CentOS/RHEL: sudo yum install mongodb-database-tools, "
            f"macOS: brew install mongodb/brew/mongodb-database-tools"
        )
        logger.error(error_msg)
        raise Exception(error_msg)
    
    logger.info(f"All required MongoDB tools are available: {', '.join(required_tools)}")
    return True


class MongoDBBackup:
    """MongoDB backup class using mongodump"""
    
    def __init__(self, host: str = None, port: int = None, database: str = None, 
                 username: str = None, password: str = None, validate_tools: bool = True):
        """
        Initialize MongoDB backup with connection settings
        
        Args:
            host: MongoDB host
            port: MongoDB port
            database: Database name
            username: MongoDB username
            password: MongoDB password
            validate_tools: Whether to validate MongoDB tools availability on init
        """
        self.host = host or os.getenv('DB_HOST', 'localhost')
        self.port = port or int(os.getenv('DB_PORT', '27017'))
        self.database = database or os.getenv('DB_NAME', 'compugit')
        self.username = username or os.getenv('DB_USERNAME')
        self.password = password or os.getenv('DB_PASSWORD')
        
        # Extract host and port from URI if provided
        db_uri = os.getenv('DB_URI')
        if db_uri and not host and not port:
            self._parse_uri(db_uri)
        
        # Check if MongoDB tools are available
        if validate_tools:
            try:
                validate_mongodb_tools(['mongodump'])
                self.tools_available = True
                logger.info("MongoDB backup tools validation passed")
            except Exception as e:
                self.tools_available = False
                logger.error(f"MongoDB backup tools validation failed: {e}")
        else:
            self.tools_available = None  # Not validated
    
    def _parse_uri(self, uri: str):
        """Parse MongoDB URI to extract connection details"""
        try:
            # Simple URI parsing for mongodb://host:port format
            if uri.startswith('mongodb://'):
                uri_part = uri.replace('mongodb://', '')
                if '@' in uri_part:
                    # Has credentials
                    credentials, host_part = uri_part.split('@', 1)
                    if ':' in credentials:
                        self.username, self.password = credentials.split(':', 1)
                else:
                    host_part = uri_part
                
                if ':' in host_part:
                    self.host, port_str = host_part.split(':', 1)
                    # Remove database name if present
                    if '/' in port_str:
                        port_str = port_str.split('/')[0]
                    self.port = int(port_str)
                else:
                    self.host = host_part.split('/')[0]
        except Exception as e:
            logger.warning(f"Failed to parse MongoDB URI: {e}")
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get database information including collections"""
        try:
            # Build connection string
            client_kwargs = {}
            if self.username and self.password:
                client_kwargs['username'] = self.username
                client_kwargs['password'] = self.password
            
            uri = f"mongodb://{self.host}:{self.port}"
            client = pymongo.MongoClient(uri, **client_kwargs)
            db = client[self.database]
            
            # Get database stats
            stats = db.command("dbStats")
            collections = db.list_collection_names()
            
            info = {
                'host': self.host,
                'port': self.port,
                'database': self.database,
                'collections': collections,
                'stats': {
                    'collections_count': stats.get('collections', 0),
                    'objects': stats.get('objects', 0),
                    'dataSize': stats.get('dataSize', 0),
                    'storageSize': stats.get('storageSize', 0),
                    'indexes': stats.get('indexes', 0)
                }
            }
            
            client.close()
            return info
            
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            raise Exception(f"Failed to get database info: {e}")
    
    def backup_database(self, output_dir: str = None, filters: Dict[str, Any] = None) -> str:
        """
        Backup entire database using mongodump
        
        Args:
            output_dir: Output directory for backup (temp dir if None)
            filters: Query filters to apply to backup
            
        Returns:
            Path to backup archive
            
        Raises:
            Exception: If mongodump tool is not available or backup fails
        """
        # Check if tools are available
        if self.tools_available is False:
            raise Exception("mongodump tool is not available. Please install mongodb-database-tools package.")
        elif self.tools_available is None:
            # Validate tools now if not done during init
            validate_mongodb_tools(['mongodump'])
        
        try:
            if output_dir is None:
                output_dir = tempfile.mkdtemp(prefix='mongodb_backup_')
            
            # Build mongodump command
            cmd = ['mongodump']
            cmd.extend(['--host', f"{self.host}:{self.port}"])
            cmd.extend(['--db', self.database])
            cmd.extend(['--out', output_dir])
            cmd.extend(['--authenticationDatabase=admin'])
            
            # Only use authentication if both username and password are provided and non-empty
            if self.username and self.password:
                cmd.extend(['--username', self.username])
                cmd.extend(['--password', self.password])
            
            # Add query filters if provided
            if filters:
                query = json.dumps(filters, default=json_util.default)
                cmd.extend(['--query', query])
            
            # Execute mongodump
            logger.info(f"Running mongodump command: {' '.join(cmd[:-2] + ['--password', '***'] if self.password else cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Create archive from output directory
            archive_path = f"{output_dir}.tar.gz"
            # Use the parent directory as base and specify the directory name to archive
            parent_dir = os.path.dirname(output_dir)
            dir_name = os.path.basename(output_dir)
            shutil.make_archive(output_dir, 'gztar', parent_dir, dir_name)
            
            # Clean up temporary directory
            shutil.rmtree(output_dir)
            
            logger.info(f"Database backup completed: {archive_path}")
            return archive_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"mongodump failed: {e.stderr}")
            if "command not found" in e.stderr or "No such file or directory" in str(e):
                raise Exception("mongodump tool is not installed or not in PATH. Please install mongodb-database-tools package.")
            raise Exception(f"Backup failed: {e.stderr}")
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            raise Exception(f"Backup failed: {e}")
    
    def backup_collection(self, collection: str, output_dir: str = None, 
                         filters: Dict[str, Any] = None) -> str:
        """
        Backup specific collection using mongodump
        
        Args:
            collection: Collection name to backup
            output_dir: Output directory for backup (temp dir if None)
            filters: Query filters to apply to backup
            
        Returns:
            Path to backup archive
            
        Raises:
            Exception: If mongodump tool is not available or backup fails
        """
        # Check if tools are available
        if self.tools_available is False:
            raise Exception("mongodump tool is not available. Please install mongodb-database-tools package.")
        elif self.tools_available is None:
            # Validate tools now if not done during init
            validate_mongodb_tools(['mongodump'])
        
        try:
            if output_dir is None:
                output_dir = tempfile.mkdtemp(prefix=f'mongodb_backup_{collection}_')
            
            # Build mongodump command
            cmd = ['mongodump']
            cmd.extend(['--host', f"{self.host}:{self.port}"])
            cmd.extend(['--db', self.database])
            cmd.extend(['--collection', collection])
            cmd.extend(['--out', output_dir])
            cmd.extend(['--authenticationDatabase=admin'])
            
            # Only use authentication if both username and password are provided and non-empty
            if self.username and self.password:
                cmd.extend(['--username', self.username])
                cmd.extend(['--password', self.password])
            
            # Add query filters if provided
            if filters:
                query = json.dumps(filters, default=json_util.default)
                cmd.extend(['--query', query])
            
            # Execute mongodump
            logger.info(f"Running mongodump for collection {collection}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Create archive from output directory
            archive_path = f"{output_dir}.tar.gz"
            # Use the parent directory as base and specify the directory name to archive
            parent_dir = os.path.dirname(output_dir)
            dir_name = os.path.basename(output_dir)
            shutil.make_archive(output_dir, 'gztar', parent_dir, dir_name)
            
            # Clean up temporary directory
            shutil.rmtree(output_dir)
            
            logger.info(f"Collection {collection} backup completed: {archive_path}")
            return archive_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"mongodump failed for collection {collection}: {e.stderr}")
            if "command not found" in e.stderr or "No such file or directory" in str(e):
                raise Exception("mongodump tool is not installed or not in PATH. Please install mongodb-database-tools package.")
            raise Exception(f"Collection backup failed: {e.stderr}")
        except Exception as e:
            logger.error(f"Collection backup failed: {e}")
            raise Exception(f"Collection backup failed: {e}")


class MongoDBRestore:
    """MongoDB restore class using mongorestore"""
    
    def __init__(self, host: str = None, port: int = None, database: str = None,
                 username: str = None, password: str = None, validate_tools: bool = True):
        """
        Initialize MongoDB restore with connection settings
        
        Args:
            host: MongoDB host
            port: MongoDB port
            database: Database name
            username: MongoDB username
            password: MongoDB password
            validate_tools: Whether to validate MongoDB tools availability on init
        """
        self.host = host or os.getenv('DB_HOST', 'localhost')
        self.port = port or int(os.getenv('DB_PORT', '27017'))
        self.database = database or os.getenv('DB_NAME', 'compugit')
        self.username = username or os.getenv('DB_USERNAME')
        self.password = password or os.getenv('DB_PASSWORD')
        
        # Extract host and port from URI if provided
        db_uri = os.getenv('DB_URI')
        if db_uri and not host and not port:
            self._parse_uri(db_uri)
        
        # Check if MongoDB tools are available
        if validate_tools:
            try:
                validate_mongodb_tools(['mongorestore'])
                self.tools_available = True
                logger.info("MongoDB restore tools validation passed")
            except Exception as e:
                self.tools_available = False
                logger.error(f"MongoDB restore tools validation failed: {e}")
        else:
            self.tools_available = None  # Not validated
    
    def _parse_uri(self, uri: str):
        """Parse MongoDB URI to extract connection details"""
        try:
            # Simple URI parsing for mongodb://host:port format
            if uri.startswith('mongodb://'):
                uri_part = uri.replace('mongodb://', '')
                if '@' in uri_part:
                    # Has credentials
                    credentials, host_part = uri_part.split('@', 1)
                    if ':' in credentials:
                        self.username, self.password = credentials.split(':', 1)
                else:
                    host_part = uri_part
                
                if ':' in host_part:
                    self.host, port_str = host_part.split(':', 1)
                    # Remove database name if present
                    if '/' in port_str:
                        port_str = port_str.split('/')[0]
                    self.port = int(port_str)
                else:
                    self.host = host_part.split('/')[0]
        except Exception as e:
            logger.warning(f"Failed to parse MongoDB URI: {e}")
    
    def restore_database(self, archive_path: str, drop_existing: bool = False) -> bool:
        """
        Restore entire database using mongorestore
        
        Args:
            archive_path: Path to backup archive
            drop_existing: Whether to drop existing database before restore
            
        Returns:
            True if successful
            
        Raises:
            Exception: If mongorestore tool is not available or restore fails
        """
        # Check if tools are available
        if self.tools_available is False:
            raise Exception("mongorestore tool is not available. Please install mongodb-database-tools package.")
        elif self.tools_available is None:
            # Validate tools now if not done during init
            validate_mongodb_tools(['mongorestore'])
        
        try:
            # Extract archive to temporary directory
            extract_dir = tempfile.mkdtemp(prefix='mongodb_restore_')
            # Try to extract without specifying format - let Python auto-detect
            try:
                shutil.unpack_archive(archive_path, extract_dir)
            except Exception as extract_error:
                logger.warning(f"Auto-detection failed, trying as gztar: {extract_error}")
                shutil.unpack_archive(archive_path, extract_dir, 'gztar')
            
            # Find the database directory inside extracted files
            db_path = None
            for root, dirs, files in os.walk(extract_dir):
                if self.database in dirs:
                    db_path = os.path.join(root, self.database)
                    break
            
            if not db_path:
                raise Exception(f"Database {self.database} not found in backup archive")
            
            # Build mongorestore command
            cmd = ['mongorestore']
            cmd.extend(['--host', f"{self.host}:{self.port}"])
            cmd.extend(['--db', self.database])
            cmd.extend(['--authenticationDatabase=admin'])
            
            # Only use authentication if both username and password are provided and non-empty
            if self.username and self.password:
                cmd.extend(['--username', self.username])
                cmd.extend(['--password', self.password])
            
            if drop_existing:
                cmd.append('--drop')
            
            cmd.append(db_path)
            
            # Execute mongorestore
            logger.info(f"Running mongorestore for database {self.database}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Clean up temporary directory
            shutil.rmtree(extract_dir)
            
            logger.info(f"Database restore completed successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"mongorestore failed: {e.stderr}")
            if "command not found" in e.stderr or "No such file or directory" in str(e):
                raise Exception("mongorestore tool is not installed or not in PATH. Please install mongodb-database-tools package.")
            raise Exception(f"Restore failed: {e.stderr}")
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise Exception(f"Restore failed: {e}")
    
    def restore_collection(self, collection: str, archive_path: str, 
                          drop_existing: bool = False) -> bool:
        """
        Restore specific collection using mongorestore
        
        Args:
            collection: Collection name to restore
            archive_path: Path to backup archive
            drop_existing: Whether to drop existing collection before restore
            
        Returns:
            True if successful
            
        Raises:
            Exception: If mongorestore tool is not available or restore fails
        """
        # Check if tools are available
        if self.tools_available is False:
            raise Exception("mongorestore tool is not available. Please install mongodb-database-tools package.")
        elif self.tools_available is None:
            # Validate tools now if not done during init
            validate_mongodb_tools(['mongorestore'])
        
        try:
            # Extract archive to temporary directory
            extract_dir = tempfile.mkdtemp(prefix=f'mongodb_restore_{collection}_')
            # Try to extract without specifying format - let Python auto-detect
            try:
                shutil.unpack_archive(archive_path, extract_dir)
            except Exception as extract_error:
                logger.warning(f"Auto-detection failed, trying as gztar: {extract_error}")
                shutil.unpack_archive(archive_path, extract_dir, 'gztar')
            
            # Find the collection file inside extracted files
            collection_file = None
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    if file == f"{collection}.bson":
                        collection_file = os.path.join(root, file)
                        break
                if collection_file:
                    break
            
            if not collection_file:
                raise Exception(f"Collection {collection} not found in backup archive")
            
            # Build mongorestore command
            cmd = ['mongorestore']
            cmd.extend(['--host', f"{self.host}:{self.port}"])
            cmd.extend(['--db', self.database])
            cmd.extend(['--collection', collection])
            cmd.extend(['--authenticationDatabase=admin'])
            
            # Only use authentication if both username and password are provided and non-empty
            if self.username and self.password:
                cmd.extend(['--username', self.username])
                cmd.extend(['--password', self.password])
            
            if drop_existing:
                cmd.append('--drop')
            
            cmd.append(collection_file)
            
            # Execute mongorestore
            logger.info(f"Running mongorestore for collection {collection}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Clean up temporary directory
            shutil.rmtree(extract_dir)
            
            logger.info(f"Collection {collection} restore completed successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"mongorestore failed for collection {collection}: {e.stderr}")
            if "command not found" in e.stderr or "No such file or directory" in str(e):
                raise Exception("mongorestore tool is not installed or not in PATH. Please install mongodb-database-tools package.")
            raise Exception(f"Collection restore failed: {e.stderr}")
        except Exception as e:
            logger.error(f"Collection restore failed: {e}")
            raise Exception(f"Collection restore failed: {e}")