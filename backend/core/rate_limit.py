"""
Minimal async-native rate limiting (audit SC6: Enter-spam → unbounded threads).
Token bucket per key; used for REST (per-IP) and WebSocket (per-connection).
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from core.logging import get_logger

logger = get_logger(__name__)


class TokenBucket:
    """Single bucket: `rate` tokens per `per_seconds`, starts full."""

    def __init__(self, rate: int, per_seconds: float) -> None:
        self.capacity = float(rate)
        self.tokens = float(rate)
        self.rate = rate / per_seconds
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def allow(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


class RateLimiter:
    """Keyed buckets with lazy cleanup. Process-local (swap for Redis when
    multi-instance — the interface already supports it)."""

    def __init__(self, rate: int, per_seconds: float, max_keys: int = 10_000) -> None:
        self.rate = rate
        self.per = per_seconds
        self.max_keys = max_keys
        self._buckets: dict[str, TokenBucket] = defaultdict(lambda: TokenBucket(rate, per_seconds))

    async def allow(self, key: str) -> bool:
        if len(self._buckets) > self.max_keys:
            self._buckets.clear()  # crude-but-bounded reset; per-key limits survive next hit
        return await self._buckets[key].allow()


class RedisRateLimiter:
    """Phase 5: same `allow(key)` contract, state shared across instances.

    Fixed-window counter (INCR + EXPIRE) — algorithmically simpler than the
    token bucket, correct for abuse control, and safe on Redis' single-threaded
    command execution (no Lua needed for this shape).
    """

    def __init__(self, client, rate: int, per_seconds: float, *, prefix: str = "vednix:rl") -> None:
        self._redis = client  # redis.asyncio.Redis-compatible (tests: in-memory stub)
        self.rate = rate
        self.per = int(per_seconds) or 1
        self._prefix = prefix

    async def allow(self, key: str) -> bool:
        redis_key = f"{self._prefix}:{key}"
        count = await self._redis.incr(redis_key)
        if count == 1:
            await self._redis.expire(redis_key, self.per)
        return count <= self.rate


async def build_rate_limiter(redis_url: str, *, rate: int, per_seconds: float):
    """Redis when configured AND reachable; in-process otherwise (honest log,
    never a boot-time crash — offline-first means external services are icing)."""
    if redis_url:
        try:
            from redis import asyncio as aioredis  # local import: optional dependency

            client = aioredis.from_url(redis_url, socket_connect_timeout=2.0)
            await client.ping()
            logger.info("rate limiting via Redis (%s)", redis_url)
            return RedisRateLimiter(client, rate, per_seconds)
        except Exception:
            logger.warning("Redis unreachable at %s — falling back to in-process rate limiting", redis_url)
    return RateLimiter(rate=rate, per_seconds=per_seconds)
