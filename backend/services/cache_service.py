from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from typing import Optional

from redis.asyncio import Redis

from backend.utils.config import Settings
from backend.utils.logging import get_logger
from backend.utils.monitoring import record_metric


logger = get_logger("criclytics.cache")


class CacheService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._redis: Optional[Redis] = None
        self._memory_store: dict[str, tuple[float, str]] = {}
        self._lock = asyncio.Lock()

    @property
    def client(self) -> Optional[Redis]:
        return self._redis

    async def connect(self) -> None:
        if self.settings.cache_backend != "redis":
            logger.info("Using in-memory cache backend")
            return

        for attempt in range(1, 4):
            try:
                redis = Redis.from_url(
                    self.settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_timeout=self.settings.request_timeout_seconds,
                )
                await redis.ping()
                self._redis = redis
                logger.info("Redis cache connected")
                return
            except Exception as exc:
                logger.warning("Redis connection attempt %s failed: %s", attempt, exc)
                await asyncio.sleep(attempt * 0.25)

        logger.warning("Falling back to in-memory cache store")

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()

    async def ping(self) -> str:
        if self.settings.cache_backend != "redis":
            return "up"

        if self._redis is None:
            return "degraded"

        try:
            await self._redis.ping()
            return "up"
        except Exception as exc:
            logger.warning("Redis ping failed: %s", exc)
            return "degraded"

    async def get_json(self, key: str) -> Optional[Any]:
        started_at = time.perf_counter()
        if self._redis is not None:
            try:
                payload = await self._redis.get(key)
                record_metric("cache.redis_get_ms", round((time.perf_counter() - started_at) * 1000, 2))
                return json.loads(payload) if payload else None
            except Exception as exc:
                logger.warning("Redis read failed for key=%s: %s", key, exc)

        cached = await self._get_from_memory(key)
        record_metric("cache.memory_get_ms", round((time.perf_counter() - started_at) * 1000, 2))
        return cached

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        started_at = time.perf_counter()
        serialized = json.dumps(value, default=str, separators=(",", ":"))
        if self._redis is not None:
            try:
                await self._redis.set(key, serialized, ex=ttl_seconds)
                record_metric("cache.redis_set_ms", round((time.perf_counter() - started_at) * 1000, 2))
                return
            except Exception as exc:
                logger.warning("Redis write failed for key=%s: %s", key, exc)

        await self._set_in_memory(key, serialized, ttl_seconds)
        record_metric("cache.memory_set_ms", round((time.perf_counter() - started_at) * 1000, 2))

    async def _get_from_memory(self, key: str) -> Optional[Any]:
        async with self._lock:
            item = self._memory_store.get(key)
            if not item:
                return None

            expires_at, payload = item
            if time.time() > expires_at:
                self._memory_store.pop(key, None)
                return None

            return json.loads(payload)

    async def _set_in_memory(self, key: str, payload: str, ttl_seconds: int) -> None:
        async with self._lock:
            self._memory_store[key] = (time.time() + ttl_seconds, payload)
