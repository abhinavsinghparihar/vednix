"""
Minimal async-native rate limiting (audit SC6: Enter-spam → unbounded threads).
Token bucket per key; used for REST (per-IP) and WebSocket (per-connection).
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict


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
