from __future__ import annotations

from dataclasses import dataclass

from backend.services.cricket_logic import MatchContext, clamp


@dataclass(frozen=True)
class SignalProfile:
    pressure: str
    momentum: str
    stability: str
    pressure_score: float
    momentum_score: float
    stability_score: float
    control_score: float
    match_control_index: float
    volatility_score: float
    pressure_acceleration: float
    wicket_risk_curve: float
    collapse_risk: float
    acceleration_window: float
    data_consistency_score: float


class SignalEngine:
    def build(self, context: MatchContext) -> SignalProfile:
        pressure_score = self._pressure_score(context)
        momentum_score = self._momentum_score(context, pressure_score)
        stability_score = self._stability_score(context, pressure_score)
        control_score = self._control_score(pressure_score, momentum_score, stability_score)
        volatility_score = self._volatility_score(context, pressure_score, momentum_score)
        pressure_acceleration = self._pressure_acceleration(context)
        wicket_risk_curve = self._wicket_risk_curve(context, pressure_score, pressure_acceleration)
        collapse_risk = self._collapse_risk(pressure_score, stability_score, wicket_risk_curve, volatility_score)
        acceleration_window = self._acceleration_window(context, control_score, collapse_risk, pressure_score)
        data_consistency_score = self._data_consistency_score(context)

        return SignalProfile(
            pressure=self._pressure_label(pressure_score),
            momentum=self._momentum_label(momentum_score),
            stability=self._stability_label(stability_score),
            pressure_score=pressure_score,
            momentum_score=momentum_score,
            stability_score=stability_score,
            control_score=control_score,
            match_control_index=control_score,
            volatility_score=volatility_score,
            pressure_acceleration=pressure_acceleration,
            wicket_risk_curve=wicket_risk_curve,
            collapse_risk=collapse_risk,
            acceleration_window=acceleration_window,
            data_consistency_score=data_consistency_score,
        )

    def _pressure_score(self, context: MatchContext) -> float:
        score = (
            (0.48 * context.scoring_pressure_index)
            + (0.2 * (1.0 - context.wickets_in_hand_ratio))
            + (0.2 * context.urgency_index)
            + (0.12 * context.phase_progress)
        )
        return round(clamp(score, 0.0, 1.0), 2)

    def _momentum_score(self, context: MatchContext, pressure_score: float) -> float:
        if context.required_rate > 0:
            chase_alignment = clamp(0.5 + (context.rate_gap / 4.0), 0.0, 1.0)
        else:
            chase_alignment = clamp(0.72 - (context.scoring_pressure_index * 0.7), 0.0, 1.0)

        resource_component = clamp((context.wickets_in_hand_ratio - 0.15) / 0.85, 0.0, 1.0)
        score = (0.52 * chase_alignment) + (0.28 * resource_component) + (0.2 * (1.0 - pressure_score))
        return round(clamp(score, 0.0, 1.0), 2)

    def _stability_score(self, context: MatchContext, pressure_score: float) -> float:
        runway_component = clamp(1.0 - ((0.55 * context.phase_progress) + (0.45 * context.urgency_index)), 0.0, 1.0)
        score = (
            (0.46 * context.wickets_in_hand_ratio)
            + (0.28 * (1.0 - pressure_score))
            + (0.26 * runway_component)
        )
        return round(clamp(score, 0.0, 1.0), 2)

    def _control_score(self, pressure_score: float, momentum_score: float, stability_score: float) -> float:
        score = (0.42 * momentum_score) + (0.34 * stability_score) + (0.24 * (1.0 - pressure_score))
        return round(clamp(score, 0.0, 1.0), 2)

    def _volatility_score(self, context: MatchContext, pressure_score: float, momentum_score: float) -> float:
        momentum_variance = abs(momentum_score - 0.5) * 2
        score = (
            (0.3 * pressure_score)
            + (0.24 * momentum_variance)
            + (0.24 * context.phase_progress)
            + (0.22 * (1.0 - context.wickets_in_hand_ratio))
        )
        return round(clamp(score, 0.0, 1.0), 2)

    def _pressure_acceleration(self, context: MatchContext) -> float:
        phase_curve = {"powerplay": 0.28, "middle": 0.56, "death": 0.88}[context.phase]
        score = (
            (0.44 * context.phase_progress)
            + (0.34 * context.scoring_pressure_index)
            + (0.22 * phase_curve)
        )
        return round(clamp(score, 0.0, 1.0), 2)

    def _wicket_risk_curve(
        self,
        context: MatchContext,
        pressure_score: float,
        pressure_acceleration: float,
    ) -> float:
        score = (
            (0.38 * (1.0 - context.wickets_in_hand_ratio))
            + (0.26 * pressure_score)
            + (0.2 * pressure_acceleration)
            + (0.16 * context.phase_progress)
        )
        return round(clamp(score, 0.0, 1.0), 2)

    def _collapse_risk(
        self,
        pressure_score: float,
        stability_score: float,
        wicket_risk_curve: float,
        volatility_score: float,
    ) -> float:
        score = (
            (0.34 * pressure_score)
            + (0.26 * (1.0 - stability_score))
            + (0.24 * wicket_risk_curve)
            + (0.16 * volatility_score)
        )
        return round(clamp(score, 0.0, 1.0), 2)

    def _acceleration_window(
        self,
        context: MatchContext,
        control_score: float,
        collapse_risk: float,
        pressure_score: float,
    ) -> float:
        phase_access = {"powerplay": 0.9, "middle": 0.72, "death": 0.52}[context.phase]
        score = (
            (0.3 * context.wickets_in_hand_ratio)
            + (0.22 * control_score)
            + (0.18 * phase_access)
            + (0.18 * (1.0 - collapse_risk))
            + (0.12 * (1.0 - pressure_score))
        )
        return round(clamp(score, 0.0, 1.0), 2)

    def _data_consistency_score(self, context: MatchContext) -> float:
        score = 1.0
        if context.balls_bowled == 0 and context.runs > 0:
            score -= 0.25
        if context.required_rate <= 0:
            score -= 0.08
        if context.current_run_rate > 18 or context.required_rate > 18:
            score -= 0.05
        if context.wickets == 10 and context.balls_remaining > 0:
            score -= 0.03
        if context.required_vs_current_ratio > 2.3:
            score -= 0.03
        return round(clamp(score, 0.55, 1.0), 2)

    def _pressure_label(self, pressure_score: float) -> str:
        if pressure_score < 0.38:
            return "low"
        if pressure_score < 0.7:
            return "medium"
        return "high"

    def _momentum_label(self, momentum_score: float) -> str:
        if momentum_score < 0.42:
            return "negative"
        if momentum_score > 0.58:
            return "positive"
        return "neutral"

    def _stability_label(self, stability_score: float) -> str:
        return "stable" if stability_score >= 0.55 else "unstable"
