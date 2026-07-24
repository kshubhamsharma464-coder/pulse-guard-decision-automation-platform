"""Unit tests for the cache primitives the dynamic Rule Management
platform's hot path reads through -- TTLCache's warmup/refresh/reload
aliases (app/core/cache.py) and RuleCache + CacheRefreshNotifier's
observer wiring (app/infrastructure/cache/)."""

from app.core.cache import TTLCache
from app.infrastructure.cache.rule_cache import RuleCache
from app.infrastructure.cache.in_memory_cache_refresh_notifier import InMemoryCacheRefreshNotifier
from app.domain.interfaces.cache_refresh_notifier import CacheRefreshEvent


def test_ttlcache_warmup_is_a_noop_if_already_warm():
    cache = TTLCache(ttl_seconds=60)
    calls = []
    cache.warmup(lambda: calls.append(1) or "v1")
    cache.warmup(lambda: calls.append(2) or "v2")
    assert calls == [1]  # second loader never invoked


def test_ttlcache_refresh_always_reloads():
    cache = TTLCache(ttl_seconds=60)
    cache.get(lambda: "v1")
    assert cache.refresh(lambda: "v2") == "v2"


def test_ttlcache_reload_invalidates_without_eager_load():
    cache = TTLCache(ttl_seconds=60)
    cache.get(lambda: "v1")
    cache.reload()
    assert cache.get(lambda: "v2") == "v2"


def test_rule_cache_self_invalidates_on_notified_event():
    notifier = InMemoryCacheRefreshNotifier()
    cache = RuleCache(notifier=notifier, ttl_seconds=60)
    assert cache.warmup(lambda: "pack-v1") == "pack-v1"
    assert cache.get(lambda: "should-not-load") == "pack-v1"

    notifier.publish(CacheRefreshEvent(entity_type="rule_pack", entity_id="x", action="activated"))
    assert cache.get(lambda: "pack-v2") == "pack-v2"


def test_rule_cache_ignores_unrelated_event_types():
    notifier = InMemoryCacheRefreshNotifier()
    cache = RuleCache(notifier=notifier, ttl_seconds=60)
    cache.warmup(lambda: "pack-v1")
    notifier.publish(CacheRefreshEvent(entity_type="user", entity_id="x", action="updated"))
    assert cache.get(lambda: "should-not-load") == "pack-v1"


def test_multiple_subscribers_all_notified():
    notifier = InMemoryCacheRefreshNotifier()
    received = []
    notifier.subscribe(lambda e: received.append(("a", e.action)))
    notifier.subscribe(lambda e: received.append(("b", e.action)))
    notifier.publish(CacheRefreshEvent(entity_type="rule_pack", entity_id="x", action="published"))
    assert received == [("a", "published"), ("b", "published")]
