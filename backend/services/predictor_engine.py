from __future__ import annotations

from dataclasses import dataclass
from math import exp

from backend.services.cricket_logic import MatchContext, clamp
from backend.services.signal_engine import SignalProfile


@dataclass(frozen=True)
class ProjectionProfile:
    expected_runs: float
    low_runs: int
    high_runs: int
    projected_run_rate: float


@dataclass(frozen=True)
class PredictionProfile:
    win_probability: float
    collapse_probability: float
    scoring_projection: ProjectionProfile


class PredictorEngine:
    def predict(self, context: MatchContext, signals: SignalProfile) -> PredictionProfile:
        win_probability = self._win_probability(context, signals)
        collapse_probability = self._collapse_probability(context, signals)
        scoring_projection = self._scoring_projection(context, signals, collapse_probability)
        return PredictionProfile(
            win_probability=win_probability,
            collapse_probability=collapse_probability,
            scoring_projection=scoring_projection,
        )

    def _win_probability(self, context: MatchContext, signals: SignalProfile) -> float:
        rate_pressure = clamp((context.required_vs_current_ratio - 1.0) / 0.85, -1.0, 1.0) if context.required_rate > 0 else 0.0
        wickets_remaining = clamp(context.wickets_in_hand_ratio, 0.0, 1.0)
        balls_remaining = clamp(context.balls_remaining_ratio, 0.0, 1.0)
        phase_bias = {"powerplay": 0.14, "middle": 0.02, "death": -0.16}[context.phase]

        advantage = (
            (1.18 * (signals.control_score - 0.5))
            + (0.88 * (wickets_remaining - 0.5))
            + (0.54 * (balls_remaining - 0.35))
            - (0.94 * rate_pressure)
            - (0.72 * (signals.collapse_risk - 0.4))
            + phase_bias
        )

        if context.phase == "death":
            advantage += 0.18 * context.rate_gap
        elif context.phase == "powerplay":
            advantage += 0.08 * (signals.stability_score - 0.5)

        probability = 1 / (1 + exp(-2.7 * advantage))
        return round(clamp(probability, 0.03, 0.97), 2)

    def _collapse_probability(self, context: MatchContext, signals: SignalProfile) -> float:
        phase_risk = {"powerplay": 0.18, "middle": 0.32, "death": 0.44}[context.phase]
        score = (
            (0.34 * signals.pressure_score)
            + (0.22 * signals.pressure_acceleration)
            + (0.2 * signals.wicket_risk_curve)
            + (0.14 * signals.volatility_score)
            + (0.1 * phase_risk)
        )
        return round(clamp(score, 0.04, 0.96), 2)

    def _scoring_projection(
        self,
        context: MatchContext,
        signals: SignalProfile,
        collapse_probability: float,
    ) -> ProjectionProfile:
        phase_base = {"powerplay": 8.2, "middle": 7.4, "death": 10.8}[context.phase]
        projected_run_rate = (
            (0.52 * context.current_run_rate)
            + (0.22 * phase_base)
            + (0.16 * (signals.acceleration_window * 10.5))
            - (0.12 * (collapse_probability * 5.5))
            - (0.08 * (signals.pressure_score * 3.2))
        )

        if context.required_rate > 0:
            projected_run_rate += 0.16 * context.required_rate
        if context.phase == "death":
            projected_run_rate += 0.48 * max(context.rate_gap, 0.0)

        projected_run_rate = round(clamp(projected_run_rate, 2.0, 18.5), 2)
        expected_runs = round(clamp((projected_run_rate / 6) * min(context.balls_remaining, 12), 0.0, 36.0), 1)
        range_spread = max(1, round(1.8 + (signals.volatility_score * 3.6) + (collapse_probability * 2.2)))
        low_runs = max(0, int(round(expected_runs - range_spread)))
        high_runs = min(36, int(round(expected_runs + range_spread)))

        return ProjectionProfile(
            expected_runs=expected_runs,
            low_runs=low_runs,
            high_runs=high_runs,
            projected_run_rate=projected_run_rate,
        )
