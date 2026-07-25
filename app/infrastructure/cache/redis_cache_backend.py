"""Redis-backed DistributedCacheBackend -- the shared L2 rule-pack cache
every application replica reads through, per Settings.cache_backend="redis"
(docs/policy-platform.md).

Atomic pointer swap, concretely: a write is two Redis SETs, not one --

    1. SET {prefix}:{key}:snapshot:{token}  <json>  EX <ttl>
       Write the full new snapshot first, under a token nothing is
       reading yet -- by the time anything can see this key, the value
       behind it is already 100% complete.
    2. SET {prefix}:{key}:pointer  {token}  EX <ttl>
       THEN flip what "active" means for this key. A single Redis SET is
       atomic, so no reader ever observes a half-updated pointer, and no
       reader can reach a snapshot key before step 1 finished writing it
       -- there is no window in which "active" points at a partially
       written value.

Old snapshot keys are never explicitly deleted -- they simply expire via
their own TTL once nothing points at them anymore ("Old Cache Released").
This trades a little Redis memory for one less moving part: no explicit
cleanup step that could itself fail, race, or delete a snapshot another
replica's in-flight read still needs.

Every method here swallows connectivity failures and logs a warning
rather than raising -- per DistributedCacheBackend's contract, this layer
is a performance optimization RuleCache falls through around (to
PostgreSQL), never a dependency its correctness relies on. This is what
satisfies the "Redis unavailable -> fall back to PostgreSQL -> never
crash" failure-strategy requirement structurally rather than by
convention."""

import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from app.domain.interfaces.distributed_cache_backend import DistributedCacheBackend

logger = logging.getLogger(__name__)


class RedisCacheBackend(DistributedCacheBackend):
    def __init__(
        self, client, key_prefix: str = "decisiox:rulecache",
        snapshot_ttl_seconds: float = 3600.0, metrics=None,
    ):
        """`client` is any redis-py-compatible client (real redis.Redis,
        or fakeredis.FakeRedis in tests -- same interface, no live Redis
        server needed to exercise this class's logic). `metrics` is
        optional and duck-typed (see app/core/metrics.py's PolicyMetrics)
        -- None means "record nothing," so this class has zero hard
        dependency on the observability subsystem."""
        self._client = client
        self._prefix = key_prefix
        self._ttl = max(1, int(snapshot_ttl_seconds))
        self._metrics = metrics

    def _pointer_key(self, key: str) -> str:
        return f"{self._prefix}:{key}:pointer"

    def _snapshot_key(self, key: str, token: str) -> str:
        return f"{self._prefix}:{key}:snapshot:{token}"

    def read_active(self, key: str) -> Optional[Dict[str, Any]]:
        start = time.perf_counter()
        try:
            token = self._client.get(self._pointer_key(key))
            if token is None:
                return None
            if isinstance(token, bytes):
                token = token.decode("utf-8")
            raw = self._client.get(self._snapshot_key(key, token))
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis read_active(%s) failed -- falling back to the source of truth: %s", key, exc)
            return None
        finally:
            if self._metrics is not None:
                self._metrics.observe_redis_latency(time.perf_counter() - start)

    def write_active(self, key: str, snapshot: Dict[str, Any]) -> None:
        start = time.perf_counter()
        try:
            token = uuid.uuid4().hex
            payload = json.dumps(snapshot)
            self._client.set(self._snapshot_key(key, token), payload, ex=self._ttl)
            self._client.set(self._pointer_key(key), token, ex=self._ttl)
        except Exception as exc:
            logger.warning(
                "Redis write_active(%s) failed -- local cache is still updated for this replica, "
                "but other replicas won't see the new version until they hit PostgreSQL themselves: %s",
                key, exc,
            )
        finally:
            if self._metrics is not None:
                self._metrics.observe_redis_latency(time.perf_counter() - start)

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False
