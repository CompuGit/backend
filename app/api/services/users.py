from typing import Any, Dict, List, Optional


class UserService:
    def __init__(self, database: Any):
        self.database = database

    def supports(self, operation: str) -> bool:
        return hasattr(self.database, operation)

    def get_user(self, identifier: Any) -> Optional[Dict[str, Any]]:
        return self.database.get_user_by_email_or_username_or_userId(identifier)

    def list_users(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return self.database.get_all_users(filters=filters or {})

    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        return self.database.create_user(user_data)

    def update_user(
        self, identifier: Any, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        return self.database.update_user(identifier, update_data)

    def delete_user(self, identifier: Any) -> bool:
        return self.database.delete_user(identifier)
