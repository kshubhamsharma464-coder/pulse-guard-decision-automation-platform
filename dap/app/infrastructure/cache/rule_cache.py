"""RuleCache -- the concrete cache the dynamic Rule Management platform's
hot-path repository (PostgresRuleRepository) reads through. This is the
Decision Engine's actual "distributed policy cache": local process memory
(L1) in front of an optional shared Redis layer (L2, Settings.cache_backend
="redis") in front of PostgreSQL (L3, the source of truth, read only on a
genuine cache miss or an explicit refresh). See docs/policy-platform.md
for the full design rationale; this docstring covers the mechanics.

Three read/write paths, each with a distinct purpose:

- get()/warmup() -- READ-THROUGH. Local TTL fresh? Return it, zero I/O.
  Local stale? Check Redis (no PostgreSQL hit on a Redis hit -- this is
  what makes "Decision Engine MUST NEVER query PostgreSQL on every
  request" true even across many replicas sharing one Redis). Redis miss
  or unreachable? Fall through to PostgreSQL, then best-effort write
  through to Redis so the NEXT reader (this replica or any other) gets a
  Redis hit instead.
- refresh() -- WRITE-PATH. Always goes straight to PostgreSQL (skips the
  Redis-read step entirely -- a refresh exists specifically because
  something changed, so trusting a Redis value that might still be the
  old one would defeat the point), builds the new value fully, and only
  after that succeeds does it become the local cache's active value AND
  Redis's active value -- via TTLCache.set(), an atomic reference swap,
  never an invalidate-then-lazily-reload gap. If PostgreSQL raises, the
  local cache's PREVIOUS value is completely untouched and this method
  re-raises (a caller like ActivateRulePackUseCase gets a real error to
  report); no request anywhere ever observes a partially-updated rule
  set, and a refresh failure never takes down an already-working cache.
- reload() -- EVENT-DRIVEN LAZY INVALIDATE, the original Phase 2.5
  behavior, still exactly what happens when no default loader has been
  bound (bind_loader() is optional -- see below). Cross-replica
  cache-refresh events land here by default; the next get() on that
  replica rebuilds it read-through.

bind_loader() is the one genuinely new piece of surface area: if the
composition root gives this cache a loader up front, cache-refresh events
(rule pack published/activated/rolled back/deleted -- see
CacheRefreshNotifier) trigger an EAGER refresh() (build, validate by
virtue of successfully deserializing, warm both Redis and local, atomic
swap) instead of a lazy local-only invalidate -- this is what makes "no
request should fail during cache refresh" true even for the very first
request after an activation, and what actually propagates a change to
Redis (and therefore every other replica) rather than only this one
process's local cache. Every existing call site and test that never
calls bind_loader() keeps the exact original lazy-invalidate behavior --
this is purely additive."""

import logging
import time
from typing import Any, Callable, Dict, Optional

from app.core.cache import TTLCache
from app.domain.interfaces.cache_refresh_notifier import CacheRefreshNotifier, CacheRefreshEvent
from app.domain.interfaces.distributed_cache_backend import DistributedCacheBackend
from app.domain.entities.rule_pack import RulePack
from app.infrastructure.cache.rule_snapshot import rule_pack_to_snapshot, rule_pack_from_snapshot

logger = logging.getLogger(__name__)


class RuleCache:
    def __init__(
        self,
        notifier: Optional[CacheRefreshNotifier] = None,
        ttl_seconds: float = 10.0,
        distributed_backend: Optional[DistributedCacheBackend] = None,
        cache_key: str = "default",
        metrics=None,
    ):
        self._ttl_cache = TTLCache(ttl_seconds=ttl_seconds)
        self._notifier = notifier
        self._distributed = distributed_backend
        self._cache_key = cache_key
        self._metrics = metrics  # duck-typed, see app/core/metrics.py's PolicyMetrics -- None records nothing
        self._default_loader: Optional[Callable[[], RulePack]] = None
        # In-process "last known good" -- a second, independent fallback
        # layer beyond Redis: if PostgreSQL AND Redis are both
        # unreachable (or cache_backend="memory" so there's no Redis at
        # all) at the moment of a refresh, this is what lets the cache
        # keep serving instead of raising into a live request. Set on
        # every successful PostgreSQL load, in EVERY configuration.
        self._last_known_good: Optional[RulePack] = None
        if notifier is not None:
            notifier.subscribe(self._on_event)

    def bind_loader(self, loader: Callable[[], RulePack]) -> None:
        """Optional. See module docstring's "bind_loader()" section --
        lets cache-refresh events eagerly rebuild and write through to
        Redis instead of only invalidating this one replica's local
        copy. Composition root only (dependencies.py); nothing about
        RuleCache's public contract requires callers to know this
        exists."""
        self._default_loader = loader

    # -- event handling -----------------------------------------------

    def _on_event(self, event: CacheRefreshEvent) -> None:
        if event.entity_type not in ("rule_pack", "rule"):
            return
        if self._default_loader is None:
            self.reload()
            return
        try:
            self.refresh(self._default_loader)
        except Exception:
            # refresh() already logged a critical event and left the old
            # cache value fully intact -- an event handler must never let
            # that propagate back into the publisher (the use case that
            # just successfully committed a real database change; it
            # should not see its own HTTP response turn into a 500
            # because of an unrelated cache-warm problem).
            pass

    # -- distributed (Redis) layer helpers ------------------------------

    def _distributed_read(self) -> Optional[RulePack]:
        if self._distributed is None:
            return None
        snapshot = self._distributed.read_active(self._cache_key)
        if snapshot is None:
            if self._metrics is not None:
                self._metrics.record_cache_miss("redis")
            return None
        if self._metrics is not None:
            self._metrics.record_cache_hit("redis")
        try:
            return rule_pack_from_snapshot(snapshot)
        except Exception:
            logger.warning("Redis snapshot for key=%s was unreadable -- treating as a miss", self._cache_key, exc_info=True)
            return None

    def _distributed_write(self, pack: RulePack) -> None:
        if self._distributed is None:
            return
        self._distributed.write_active(self._cache_key, rule_pack_to_snapshot(pack))

    # -- the two resolution strategies -----------------------------------

    def _load_from_source_and_propagate(self, loader: Callable[[], RulePack]) -> RulePack:
        """Always calls loader() (PostgreSQL) -- used by refresh() (a
        refresh exists because something is known to have changed, so a
        stale Redis value must never short-circuit it) and by
        _resolve_for_get() on a Redis miss."""
        try:
            pack = loader()
        except Exception:
            if self._last_known_good is not None:
                logger.critical(
                    "Rule pack load from PostgreSQL failed and no fresh Redis snapshot was available -- "
                    "serving this process's last-known-good in-memory snapshot instead of failing the request.",
                    exc_info=True,
                )
                if self._metrics is not None:
                    self._metrics.record_degraded_serve()
                return self._last_known_good
            raise
        self._last_known_good = pack
        self._distributed_write(pack)
        return pack

    def _resolve_for_get(self, loader: Callable[[], RulePack]) -> RulePack:
        pack = self._distributed_read()
        if pack is not None:
            self._last_known_good = pack
            return pack
        return self._load_from_source_and_propagate(loader)

    # -- public cache-vocabulary methods (unchanged signatures) ----------

    def warmup(self, loader: Callable[[], RulePack]) -> RulePack:
        return self._ttl_cache.warmup(lambda: self._resolve_for_get(loader))

    def get(self, loader: Callable[[], RulePack]) -> RulePack:
        return self._ttl_cache.get(lambda: self._resolve_for_get(loader))

    def refresh(self, loader: Callable[[], RulePack]) -> RulePack:
        start = time.perf_counter()
        new_value = self._load_from_source_and_propagate(loader)  # may raise -- old cache value untouched if so
        self._ttl_cache.set(new_value)
        if self._metrics is not None:
            self._metrics.record_refresh_duration(time.perf_counter() - start)
        return new_value

    def reload(self) -> None:
        self._ttl_cache.reload()

    def invalidate(self) -> None:
        self._ttl_cache.invalidate()

    # -- health/observability (readiness probe, /api/v1/metrics) ---------

    def status(self) -> Dict[str, Any]:
        pack = self._ttl_cache.peek()
        return {
            "localWarm": pack is not None,
            "activeVersion": pack.version if pack is not None else None,
            "activatedAt": pack.activated_at.isoformat() if (pack is not None and pack.activated_at) else None,
            "distributedBackendConfigured": self._distributed is not None,
            "distributedBackendReachable": (self._distributed.ping() if self._distributed is not None else None),
            "hasLastKnownGood": self._last_known_good is not None,
        }
