from __future__ import annotations

from dataclasses import dataclass

from backend.services.cricket_logic import MatchContext, clamp
from backend.services.predictor_engine import PredictionProfile
from backend.services.signal_engine import SignalProfile
from backend.services.trend_engine import TrendProfile


@dataclass(frozen=True)
class IntelligenceProfile:
    match_intelligence_score: float
    confidence_score: float


class ScoringEngine:
    def score(
        self,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
    ) -> IntelligenceProfile:
        return self._score_core(
            innings_progress=context.innings_progress,
            data_consistency_score=signals.data_consistency_score,
            control_score=signals.control_score,
            pressure_score=signals.pressure_score,
            momentum_score=signals.momentum_score,
            stability_score=signals.stability_score,
            volatility_score=signals.volatility_score,
            win_probability=predictions.win_probability,
            collapse_probability=predictions.collapse_probability,
            trend=trend.trend,
            trend_strength=trend.trend_strength,
        )

    def score_snapshot(
        self,
        *,
        innings_progress: float,
        data_consistency_score: float,
        control_score: float,
        pressure_score: float,
        momentum_score: float,
        stability_score: float,
        volatility_score: float,
        win_probability: float,
        collapse_probability: float,
        trend: str,
        trend_strength: float,
    ) -> IntelligenceProfile:
        return self._score_core(
            innings_progress=innings_progress,
            data_consistency_score=data_consistency_score,
            control_score=control_score,
            pressure_score=pressure_score,
            momentum_score=momentum_score,
            stability_score=stability_score,
            volatility_score=volatility_score,
            win_probability=win_probability,
            collapse_probability=collapse_probability,
            trend=trend,
            trend_strength=trend_strength,
        )

    def _score_core(
        self,
        *,
        innings_progress: float,
        data_consistency_score: float,
        control_score: float,
        pressure_score: float,
        momentum_score: float,
        stability_score: float,
        volatility_score: float,
        win_probability: float,
        collapse_probability: float,
        trend: str,
        trend_strength: float,
    ) -> IntelligenceProfile:
        trend_factor = {"improving": 0.74, "stable": 0.5, "declining": 0.26}[trend]
        stability_bias = 1.0 - abs(volatility_score - 0.45)

        match_intelligence_score = (
            (0.22 * control_score)
            + (0.15 * (1.0 - pressure_score))
            + (0.12 * momentum_score)
            + (0.1 * stability_score)
            + (0.16 * win_probability)
            + (0.11 * (1.0 - collapse_probability))
            + (0.08 * trend_factor)
            + (0.06 * stability_bias)
        )

        innings_information = clamp(0.35 + (0.65 * innings_progress), 0.35, 1.0)
        confidence_score = (
            (0.28 * data_consistency_score)
            + (0.18 * innings_information)
            + (0.16 * (1.0 - abs(win_probability - 0.5)))
            + (0.14 * max(trend_strength, 0.2))
            + (0.12 * (1.0 - volatility_score))
            + (0.12 * match_intelligence_score)
        )

        return IntelligenceProfile(
            match_intelligence_score=round(clamp(match_intelligence_score, 0.0, 1.0), 2),
            confidence_score=round(clamp(confidence_score, 0.35, 0.97), 2),
        )
