from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

class DatabaseInterface(ABC):
    @abstractmethod
    def connect(self) -> None:
        """Establish database connection"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close database connection"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if database is connected"""
        pass

    @abstractmethod
    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user"""
        pass

    @abstractmethod
    def get_user_by_email_or_username_or_userId(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Get user by email, username, or userId"""
        pass

    @abstractmethod
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users"""
        pass

    @abstractmethod
    def update_user(self, email: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update user data"""
        pass

    @abstractmethod
    def delete_user(self, email: str) -> bool:
        """Delete user"""
        pass