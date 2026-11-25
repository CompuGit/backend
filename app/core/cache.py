import json
from typing import Any, Optional

from redis import Redis


class JsonCache:
    def __init__(self, client: Optional[Redis], namespace: str = "app"):
        self.client = client
        self.namespace = namespace

    def get(self, key: str) -> Optional[Any]:
        if self.client is None:
            return None
        value = self.client.get(self._key(key))
        return json.loads(value) if value is not None else None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("Cache TTL must be positive")
        if self.client is None:
            return
        self.client.set(
            self._key(key),
            json.dumps(value, separators=(",", ":")),
            ex=ttl_seconds,
        )

    def delete(self, key: str) -> None:
        if self.client is not None:
            self.client.delete(self._key(key))

    def _key(self, key: str) -> str:
        if not key:
            raise ValueError("Cache key must not be empty")
        return f"{self.namespace}:cache:{key}"
