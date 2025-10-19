import os
from typing import Optional, Dict, Any, List
import pymongo
from datetime import datetime

from app.database.interface import DatabaseInterface
from app.applogger import logger

class MongoDBConnection(DatabaseInterface):
    def __init__(self):
        self.client = None
        self.db = None
        self.users_collection = None
        self.uri = os.getenv('DB_URI', 'mongodb://localhost:27017')
        self.db_name = os.getenv('DB_NAME', 'compugit')
        self.username = os.getenv('DB_USERNAME')
        self.password = os.getenv('DB_PASSWORD')

    def connect(self) -> None:
        try:
            # Prepare connection kwargs
            client_kwargs = {}
            if self.username and self.password:
                client_kwargs['username'] = self.username
                client_kwargs['password'] = self.password
            
            self.client = pymongo.MongoClient(self.uri, **client_kwargs)
            self.db = self.client[self.db_name]
            self.users_collection = self.db.users
            self.counters_collection = self.db.counters
            
            # Create indexes
            self.users_collection.create_index([('email', pymongo.ASCENDING)], unique=True)
            self.users_collection.create_index([('userName', pymongo.ASCENDING)], unique=True)
            self.users_collection.create_index([('userId', pymongo.ASCENDING)], unique=True)

            # Initialize userId counter if not exists
            self.counters_collection.update_one(
                {'_id': 'userId'},
                {'$setOnInsert': {'sequence_value': 10001}},
                upsert=True
            )

            # Test connection
            self.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")

            # set admin user if not exists
            admin_user = self.users_collection.find_one({'userName': 'admin'})
            if not admin_user:
                admin_data = {
                    "userName": "admin",
                    "email": "ad.compugit@gmail.com",
                    "name": "Admin Compugit",
                    "contact": "6305813208",
                    "roles": ["admin"],
                    "canLogin": True,
                    "password_hash": "scrypt:32768:8:1$nnQjROM8w60A12kb$c5525885afac48cc3ec8ca612f33168383ed9893c5acd10c6e2f60850f8b22198e67fb74e241fd156d44d4f9c8a8c9f10e094aef4906b30ba6990a22876a3515", #Admin@123
                    "departments": [],
                    "userId": 10000,
                    "created_at": datetime.now()
                }
                self.users_collection.insert_one(admin_data)
        except Exception as e:
            logger.error(f"MongoDB connection failed: {str(e)}")
            raise

    def disconnect(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            self.users_collection = None
            logger.info("MongoDB connection closed")

    def is_connected(self) -> bool:
        if self.client:
            try:
                self.client.admin.command('ping')
                return True
            except:
                return False
        return False

    # helper methods to get next IDs
    def get_next_userid(self) -> int:
        """Generate next user ID using atomic increment"""
        try:
            result = self.counters_collection.find_one_and_update(
                {'_id': 'userId'},
                {'$inc': {'sequence_value': 1}},
                return_document=pymongo.ReturnDocument.AFTER
            )
            return result['sequence_value']
        except Exception as e:
            logger.error(f"Failed to generate empid: {str(e)}")
            raise
    
    # User CRUD methods
    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user_data['userId'] = self.get_next_userid()
            user_data['created_at'] = datetime.now()
            result = self.users_collection.insert_one(user_data)
            return self.get_user_by_email_or_username_or_userId(user_data['userId'])
        except Exception as e:
            logger.error(f"Failed to create user in MongoDB: {str(e)}")
            raise

    def get_user_by_email_or_username_or_userId(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Get user by email or username or userId"""
        try:
            user = self.users_collection.find_one({
                '$or': [
                    {'email': identifier},
                    {'userName': identifier},
                    {'userId': identifier}
                ]
            })
            if user:
                del user['_id'] # = str(user['_id'])  # Convert ObjectId to string
            return user
        except Exception as e:
            logger.error(f"Failed to get user by email or username or userId from MongoDB: {str(e)}")
            raise

    def get_all_users(self, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        try:
            query = {}
            if filters:
                if 'isActive' in filters:
                    query['isActive'] = filters['isActive']

            users = list(self.users_collection.find(query))
            for user in users:
                del user['_id'] # = str(user['_id'])  # Convert ObjectId to string
            return users
        except Exception as e:
            logger.error(f"Failed to get users from MongoDB: {str(e)}")
            raise

    def update_user(self, userId: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            update_data['updated_at'] = datetime.now()
            result = self.users_collection.update_one(
                {'userId': userId},
                {'$set': update_data}
            )
            if result.modified_count:
                return self.get_user_by_email_or_username_or_userId(userId)
            return None
        except Exception as e:
            logger.error(f"Failed to update user in MongoDB: {str(e)}")
            raise

    def delete_user(self, userId: int) -> bool:
        try:
            result = self.users_collection.delete_one({'userId': userId})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete user from MongoDB: {str(e)}")
            raise