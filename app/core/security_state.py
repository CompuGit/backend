import hashlib
import threading
import time
from typing import Any, Dict, Optional, Tuple

from redis import Redis
from werkzeug.exceptions import ServiceUnavailable


_RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


class SecurityState:
    def __init__(
        self,
        redis_client: Optional[Redis],
        namespace: str,
        identity_epoch_ttl_seconds: int,
    ):
        self.redis = redis_client
        self.namespace = namespace
        self.identity_epoch_ttl_seconds = identity_epoch_ttl_seconds
        self._lock = threading.Lock()
        self._revoked_tokens: Dict[str, float] = {}
        self._identity_epochs: Dict[str, Tuple[int, float]] = {}
        self._rate_limits: Dict[str, Tuple[int, float]] = {}

    def token_claims(self, identity: str) -> Dict[str, int]:
        return {"auth_epoch": self._identity_epoch(identity)}

    def is_token_revoked(self, payload: Dict[str, Any]) -> bool:
        identity = payload.get("sub")
        jti = payload.get("jti")
        if not isinstance(identity, str) or not isinstance(jti, str):
            return True

        if self.redis is not None:
            try:
                if self.redis.exists(self._key("revoked", jti)):
                    return True
                return payload.get("auth_epoch") != self._identity_epoch(identity)
            except Exception as error:
                raise self._unavailable() from error

        now = time.time()
        with self._lock:
            expiry = self._revoked_tokens.get(jti)
            if expiry is not None:
                if expiry > now:
                    return True
                del self._revoked_tokens[jti]
            current_epoch = self._local_identity_epoch(identity, now)
            if current_epoch:
                self._identity_epochs[identity] = (
                    current_epoch,
                    now + self.identity_epoch_ttl_seconds,
                )
            revoked = payload.get("auth_epoch") != current_epoch
            if len(self._revoked_tokens) > 1024:
                self._revoked_tokens = {
                    token: token_expiry
                    for token, token_expiry in self._revoked_tokens.items()
                    if token_expiry > now
                }
            return revoked

    def revoke_token(self, jti: str, expires_at: int) -> None:
        ttl = max(1, int(expires_at - time.time()))
        if self.redis is not None:
            try:
                self.redis.set(self._key("revoked", jti), "1", ex=ttl)
            except Exception as error:
                raise self._unavailable() from error
            return
        with self._lock:
            self._revoked_tokens[jti] = time.time() + ttl

    def revoke_identity(self, identity: str) -> None:
        if self.redis is not None:
            try:
                key = self._key("epoch", identity)
                self.redis.incr(key)
                self.redis.expire(key, self.identity_epoch_ttl_seconds)
            except Exception as error:
                raise self._unavailable() from error
            return
        with self._lock:
            now = time.time()
            if len(self._identity_epochs) > 1024:
                self._identity_epochs = {
                    identity_key: epoch_state
                    for identity_key, epoch_state in self._identity_epochs.items()
                    if epoch_state[1] > now
                }
            self._identity_epochs[identity] = (
                self._local_identity_epoch(identity, now) + 1,
                now + self.identity_epoch_ttl_seconds,
            )

    def allow_request(
        self, bucket: str, identity: str, limit: int, window_seconds: int
    ) -> bool:
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        key = self._key("rate", f"{bucket}:{digest}")
        if self.redis is not None:
            try:
                count = int(
                    self.redis.eval(_RATE_LIMIT_SCRIPT, 1, key, window_seconds)
                )
            except Exception as error:
                raise self._unavailable() from error
            return count <= limit

        now = time.monotonic()
        with self._lock:
            if len(self._rate_limits) > 1024:
                self._rate_limits = {
                    rate_key: state
                    for rate_key, state in self._rate_limits.items()
                    if state[1] > now
                }
            count, expiry = self._rate_limits.get(key, (0, now + window_seconds))
            if expiry <= now:
                count, expiry = 0, now + window_seconds
            count += 1
            self._rate_limits[key] = (count, expiry)
            return count <= limit

    def _identity_epoch(self, identity: str) -> int:
        if self.redis is not None:
            try:
                key = self._key("epoch", identity)
                value = self.redis.get(key)
                if value is None:
                    return 0
                self.redis.expire(key, self.identity_epoch_ttl_seconds)
                return int(value)
            except Exception as error:
                raise self._unavailable() from error
        with self._lock:
            now = time.time()
            epoch = self._local_identity_epoch(identity, now)
            if epoch:
                self._identity_epochs[identity] = (
                    epoch,
                    now + self.identity_epoch_ttl_seconds,
                )
            return epoch

    def _local_identity_epoch(self, identity: str, now: float) -> int:
        epoch_state = self._identity_epochs.get(identity)
        if epoch_state is None:
            return 0
        epoch, expires_at = epoch_state
        if expires_at <= now:
            del self._identity_epochs[identity]
            return 0
        return epoch

    def _key(self, category: str, identifier: str) -> str:
        if category == "epoch":
            identifier = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
        return f"{self.namespace}:security:{category}:{identifier}"

    @staticmethod
    def _unavailable() -> ServiceUnavailable:
        return ServiceUnavailable(
            "Authentication state is temporarily unavailable"
        )
