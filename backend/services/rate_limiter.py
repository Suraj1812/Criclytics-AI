from __future__ import annotations

import asyncio
import ipaddress
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

from redis.asyncio import Redis

from backend.utils.logging import get_logger


logger = get_logger("criclytics.rate_limit")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int
    limit: int
    remaining: int
    reset_at: int


class RateLimiter:
    def __init__(self, redis_client: Optional[Redis], limit: int, window_seconds: int, subnet_multiplier: int = 4) -> None:
        self.redis_client = redis_client
        self.limit = limit
        self.window_seconds = window_seconds
        self.window_ms = window_seconds * 1000
        self.subnet_multiplier = subnet_multiplier
        self._lock = asyncio.Lock()
        self._local_windows: dict[str, deque[float]] = {}

    async def allow(self, identifier: str) -> RateLimitDecision:
        scopes = [(f"ip:{identifier}", self.limit)]
        subnet_scope = self._subnet_scope(identifier)
        if subnet_scope:
            scopes.append((f"subnet:{subnet_scope}", self.limit * self.subnet_multiplier))

        decisions: list[RateLimitDecision] = []
        for key, scope_limit in scopes:
            if self.redis_client is not None:
                try:
                    decision = await self._allow_with_redis(key, scope_limit)
                except Exception as exc:
                    logger.warning("Redis-backed rate limit failed for %s: %s", key, exc)
                    decision = await self._allow_with_memory(key, scope_limit)
            else:
                decision = await self._allow_with_memory(key, scope_limit)

            decisions.append(decision)
            if not decision.allowed:
                return decision

        primary = decisions[0]
        return RateLimitDecision(
            allowed=True,
            retry_after=0,
            limit=self.limit,
            remaining=primary.remaining,
            reset_at=primary.reset_at,
        )

    async def _allow_with_redis(self, key: str, limit: int) -> RateLimitDecision:
        if self.redis_client is None:
            return await self._allow_with_memory(key, limit)

        now_ms = int(time.time() * 1000)
        window_start = now_ms - self.window_ms
        request_member = f"{now_ms}:{time.time_ns()}"

        pipeline = self.redis_client.pipeline()
        pipeline.zremrangebyscore(key, 0, window_start)
        pipeline.zcard(key)
        pipeline.zadd(key, {request_member: now_ms})
        pipeline.expire(key, self.window_seconds + 1)
        _, current_count, _, _ = await pipeline.execute()
        current_count = int(current_count) + 1

        if current_count <= limit:
            remaining = max(limit - current_count, 0)
            return RateLimitDecision(
                allowed=True,
                retry_after=0,
                limit=limit,
                remaining=remaining,
                reset_at=int(time.time()) + self.window_seconds,
            )

        await self.redis_client.zrem(key, request_member)
        oldest = await self.redis_client.zrange(key, 0, 0, withscores=True)
        reset_at = int(time.time()) + self.window_seconds
        retry_after = self.window_seconds
        if oldest:
            oldest_score = int(oldest[0][1])
            retry_after = max(int(((oldest_score + self.window_ms) - now_ms) / 1000), 1)
            reset_at = int((oldest_score + self.window_ms) / 1000)

        return RateLimitDecision(
            allowed=False,
            retry_after=retry_after,
            limit=limit,
            remaining=0,
            reset_at=reset_at,
        )

    async def _allow_with_memory(self, key: str, limit: int) -> RateLimitDecision:
        now = time.time()
        cutoff = now - self.window_seconds

        async with self._lock:
            window = self._local_windows.setdefault(key, deque())
            while window and window[0] <= cutoff:
                window.popleft()

            if len(window) >= limit:
                retry_after = max(int(window[0] + self.window_seconds - now), 1)
                return RateLimitDecision(
                    allowed=False,
                    retry_after=retry_after,
                    limit=limit,
                    remaining=0,
                    reset_at=int(window[0] + self.window_seconds),
                )

            window.append(now)
            remaining = max(limit - len(window), 0)
            return RateLimitDecision(
                allowed=True,
                retry_after=0,
                limit=limit,
                remaining=remaining,
                reset_at=int(now + self.window_seconds),
            )

    def _subnet_scope(self, identifier: str) -> Optional[str]:
        try:
            address = ipaddress.ip_address(identifier)
        except ValueError:
            return None

        if address.version == 4:
            network = ipaddress.ip_network(f"{identifier}/24", strict=False)
        else:
            network = ipaddress.ip_network(f"{identifier}/64", strict=False)
        return str(network.network_address)
