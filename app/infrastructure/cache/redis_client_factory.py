"""Builds the real redis-py client used by RedisCacheBackend in production.
Isolated in its own tiny module so tests never need to import the `redis`
package at all -- they construct RedisCacheBackend directly with a
fakeredis.FakeRedis client instead (see tests/test_redis_cache_backend.py),
which is what keeps this whole layer testable with no live Redis server."""

import redis

from app.core.settings import Settings


def create_redis_client(settings: Settings) -> "redis.Redis":
    return redis.Redis.from_url(
        settings.redis_url,
        socket_timeout=settings.redis_socket_timeout_seconds,
        socket_connect_timeout=settings.redis_socket_timeout_seconds,
        decode_responses=False,
    )
