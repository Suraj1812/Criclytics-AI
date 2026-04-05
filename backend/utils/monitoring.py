from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Mapping
from time import perf_counter
from typing import Optional

from backend.utils.logging import get_logger


logger = get_logger("criclytics.monitoring")


def record_metric(name: str, value: float = 1.0, tags: Optional[Mapping[str, str]] = None) -> None:
    rendered_tags = ",".join(f"{key}={value}" for key, value in sorted((tags or {}).items()))
    logger.info("metric=%s value=%s tags=%s", name, value, rendered_tags or "-")


def record_event(name: str, payload: Optional[Mapping[str, str]] = None) -> None:
    rendered_payload = ",".join(f"{key}={value}" for key, value in sorted((payload or {}).items()))
    logger.info("event=%s payload=%s", name, rendered_payload or "-")


def record_exception(name: str, exc: Exception, tags: Optional[Mapping[str, str]] = None) -> None:
    rendered_tags = ",".join(f"{key}={value}" for key, value in sorted((tags or {}).items()))
    logger.exception("exception=%s tags=%s error=%s", name, rendered_tags or "-", exc)


@contextmanager
def track_timing(name: str, tags: Optional[Mapping[str, str]] = None):
    started_at = perf_counter()
    try:
        yield
    finally:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        record_metric(name, duration_ms, tags=tags)
