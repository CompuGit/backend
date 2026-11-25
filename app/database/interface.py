from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from typing import Any

class DatabaseInterface(ABC):
    db_type: str

    @property
    @abstractmethod
    def native(self) -> Any:
        """Return the connected backend handle for backend-specific operations."""
        raise NotImplementedError

    @abstractmethod
    def connect(self) -> None:
        """Establish database connection"""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        """Close database connection"""
        raise NotImplementedError

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if database is connected"""
        raise NotImplementedError

    def session_scope(self) -> AbstractContextManager[Any]:
        """Return a short-lived relational session context when supported."""
        raise NotImplementedError