from __future__ import annotations

import hashlib
from dataclasses import asdict
from dataclasses import dataclass
from typing import Literal

from backend.services.cache_service import CacheService
from backend.services.cricket_logic import MatchContext, clamp
from backend.services.predictor_engine import PredictionProfile
from backend.services.signal_engine import SignalProfile


@dataclass(frozen=True)
class TrendObservation:
    current_run_rate: float
    wickets: int
    pressure_score: float
    control_score: float
    win_probability: float


@dataclass(frozen=True)
class TrendProfile:
    trend: Literal["improving", "declining", "stable"]
    momentum_shift: bool
    run_rate_trend: Literal["increasing", "decreasing", "flat"]
    pressure_trend: Literal["rising", "falling", "steady"]
    wicket_fall_pattern: Literal["stable", "watchful", "fragile"]
    trend_strength: float
    movement_score: float


class TrendEngine:
    def __init__(self, cache_service: CacheService, window_size: int = 5, ttl_seconds: int = 900) -> None:
        self.cache_service = cache_service
        self.window_size = window_size
        self.ttl_seconds = ttl_seconds

    async def observe(
        self,
        client_id: str,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
    ) -> TrendProfile:
        key = self._memory_key(client_id)
        history = await self._load_history(key)
        history.append(
            TrendObservation(
                current_run_rate=context.current_run_rate,
                wickets=context.wickets,
                pressure_score=signals.pressure_score,
                control_score=signals.control_score,
                win_probability=predictions.win_probability,
            )
        )
        history = history[-self.window_size :]
        await self.cache_service.set_json(key, [asdict(item) for item in history], ttl_seconds=self.ttl_seconds)
        return self._analyze_history(history)

    async def observe_cached(
        self,
        client_id: str,
        *,
        current_run_rate: float,
        wickets: int,
        pressure_score: float,
        control_score: float,
        win_probability: float,
    ) -> TrendProfile:
        key = self._memory_key(client_id)
        history = await self._load_history(key)
        history.append(
            TrendObservation(
                current_run_rate=current_run_rate,
                wickets=wickets,
                pressure_score=pressure_score,
                control_score=control_score,
                win_probability=win_probability,
            )
        )
        history = history[-self.window_size :]
        await self.cache_service.set_json(key, [asdict(item) for item in history], ttl_seconds=self.ttl_seconds)
        return self._analyze_history(history)

    async def _load_history(self, key: str) -> list[TrendObservation]:
        payload = await self.cache_service.get_json(key)
        if not isinstance(payload, list):
            return []

        observations: list[TrendObservation] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                observations.append(
                    TrendObservation(
                        current_run_rate=float(item["current_run_rate"]),
                        wickets=int(item["wickets"]),
                        pressure_score=float(item["pressure_score"]),
                        control_score=float(item["control_score"]),
                        win_probability=float(item["win_probability"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return observations

    def _analyze_history(self, history: list[TrendObservation]) -> TrendProfile:
        if len(history) < 2:
            return TrendProfile(
                trend="stable",
                momentum_shift=False,
                run_rate_trend="flat",
                pressure_trend="steady",
                wicket_fall_pattern="stable",
                trend_strength=0.0,
                movement_score=0.0,
            )

        current = history[-1]
        previous = history[:-1]
        count = max(len(previous), 1)
        avg_run_rate = sum(item.current_run_rate for item in previous) / count
        avg_pressure = sum(item.pressure_score for item in previous) / count
        avg_control = sum(item.control_score for item in previous) / count
        avg_win_probability = sum(item.win_probability for item in previous) / count
        oldest_wickets = previous[0].wickets if previous else current.wickets

        run_rate_delta = current.current_run_rate - avg_run_rate
        pressure_delta = current.pressure_score - avg_pressure
        control_delta = current.control_score - avg_control
        win_probability_delta = current.win_probability - avg_win_probability
        wickets_delta = current.wickets - oldest_wickets

        run_rate_trend = "increasing" if run_rate_delta > 0.45 else "decreasing" if run_rate_delta < -0.45 else "flat"
        pressure_trend = "rising" if pressure_delta > 0.08 else "falling" if pressure_delta < -0.08 else "steady"
        wicket_fall_pattern = "fragile" if wickets_delta >= 2 else "watchful" if wickets_delta == 1 else "stable"

        movement_score = (
            (0.28 * clamp(run_rate_delta / 2.4, -1.0, 1.0))
            - (0.24 * clamp(pressure_delta / 0.28, -1.0, 1.0))
            + (0.24 * clamp(control_delta / 0.28, -1.0, 1.0))
            + (0.24 * clamp(win_probability_delta / 0.22, -1.0, 1.0))
        )
        if wickets_delta >= 1:
            movement_score -= 0.12 * wickets_delta

        if movement_score >= 0.1:
            trend = "improving"
        elif movement_score <= -0.1:
            trend = "declining"
        else:
            trend = "stable"

        prior_movement = 0.0
        if len(previous) >= 2:
            mid = previous[-1]
            earlier = previous[:-1]
            earlier_count = max(len(earlier), 1)
            prior_movement = (
                (0.28 * clamp((mid.current_run_rate - (sum(item.current_run_rate for item in earlier) / earlier_count)) / 2.4, -1.0, 1.0))
                - (0.24 * clamp((mid.pressure_score - (sum(item.pressure_score for item in earlier) / earlier_count)) / 0.28, -1.0, 1.0))
                + (0.24 * clamp((mid.control_score - (sum(item.control_score for item in earlier) / earlier_count)) / 0.28, -1.0, 1.0))
                + (0.24 * clamp((mid.win_probability - (sum(item.win_probability for item in earlier) / earlier_count)) / 0.22, -1.0, 1.0))
            )

        momentum_shift = abs(movement_score - prior_movement) > 0.24 and (movement_score * prior_movement < 0 or abs(prior_movement) < 0.05)
        trend_strength = round(clamp(abs(movement_score) * 2.4, 0.0, 1.0), 2)

        return TrendProfile(
            trend=trend,
            momentum_shift=momentum_shift,
            run_rate_trend=run_rate_trend,
            pressure_trend=pressure_trend,
            wicket_fall_pattern=wicket_fall_pattern,
            trend_strength=trend_strength,
            movement_score=round(movement_score, 3),
        )

    def _memory_key(self, client_id: str) -> str:
        digest = hashlib.blake2b(client_id.encode("utf-8"), digest_size=10).hexdigest()
        return f"trend:history:{digest}"
