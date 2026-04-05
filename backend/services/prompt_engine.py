from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.models.schemas import AnalyzeRequest
from backend.prompts.insight_v1 import PROMPT_VERSION as PROMPT_V1, SYSTEM_PROMPT as SYSTEM_V1, USER_TEMPLATE as USER_V1
from backend.prompts.insight_v2 import PROMPT_VERSION as PROMPT_V2, SYSTEM_PROMPT as SYSTEM_V2, USER_TEMPLATE as USER_V2
from backend.services.cricket_logic import MatchContext
from backend.services.predictor_engine import PredictionProfile
from backend.services.scoring_engine import IntelligenceProfile
from backend.services.signal_engine import SignalProfile
from backend.services.trend_engine import TrendProfile


@dataclass(frozen=True)
class PromptDefinition:
    version: str
    system_prompt: str
    user_template: str


@dataclass(frozen=True)
class PromptEnvelope:
    version: str
    tone: str
    system_prompt: str
    user_prompt: str
    voice_notes: tuple[str, ...]
    context_enrichment: tuple[str, ...]
    trend_label: str
    trend_strength: float
    win_probability: float
    collapse_probability: float
    match_intelligence_score: float


PROMPT_REGISTRY: dict[str, PromptDefinition] = {
    PROMPT_V1: PromptDefinition(version=PROMPT_V1, system_prompt=SYSTEM_V1, user_template=USER_V1),
    PROMPT_V2: PromptDefinition(version=PROMPT_V2, system_prompt=SYSTEM_V2, user_template=USER_V2),
}


class PromptEngine:
    def __init__(self, default_version: str) -> None:
        self.default_version = default_version if default_version in PROMPT_REGISTRY else PROMPT_V2

    @property
    def supported_versions(self) -> tuple[str, ...]:
        return tuple(PROMPT_REGISTRY.keys())

    def resolve_version(self, requested_version: Optional[str]) -> str:
        if requested_version in self.supported_versions:
            return requested_version
        return self.default_version

    def build(
        self,
        request: AnalyzeRequest,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
        intelligence: IntelligenceProfile,
    ) -> PromptEnvelope:
        version = self.resolve_version(request.prompt_version)
        prompt_definition = PROMPT_REGISTRY[version]
        tone = self._resolve_tone(request.tone, signals, predictions, trend)
        voice_notes = self._tone_notes(tone)
        context_enrichment = self._context_enrichment(context, signals, predictions, trend, intelligence)

        user_prompt = prompt_definition.user_template.format(
            tone=tone,
            runs=request.runs,
            wickets=request.wickets,
            match_format=f"{context.total_overs}-over match",
            overs=context.overs_completed,
            current_run_rate=f"{context.current_run_rate:.2f}",
            required_rate=f"{context.required_rate:.2f}",
            wickets_in_hand=context.wickets_in_hand,
            balls_remaining=context.balls_remaining,
            phase=context.phase,
            pressure=signals.pressure,
            momentum=signals.momentum,
            stability=signals.stability,
            control_score=f"{signals.control_score:.2f}",
            volatility_score=f"{signals.volatility_score:.2f}",
            pressure_acceleration=f"{signals.pressure_acceleration:.2f}",
            wicket_risk_curve=f"{signals.wicket_risk_curve:.2f}",
            collapse_risk=f"{signals.collapse_risk:.2f}",
            acceleration_window=f"{signals.acceleration_window:.2f}",
            win_probability=f"{predictions.win_probability:.2f}",
            collapse_probability=f"{predictions.collapse_probability:.2f}",
            scoring_projection=f"{predictions.scoring_projection.expected_runs:.1f}",
            projected_run_rate=f"{predictions.scoring_projection.projected_run_rate:.2f}",
            trend=trend.trend,
            trend_strength=f"{trend.trend_strength:.2f}",
            pressure_trend=trend.pressure_trend,
            run_rate_trend=trend.run_rate_trend,
            momentum_shift=str(trend.momentum_shift).lower(),
            confidence_score=f"{intelligence.confidence_score:.2f}",
            intelligence_score=f"{intelligence.match_intelligence_score:.2f}",
            scoring_pressure_index=f"{context.scoring_pressure_index:.2f}",
            required_vs_current_ratio=f"{context.required_vs_current_ratio:.2f}",
            phase_progress=f"{context.phase_progress:.2f}",
            context_enrichment=" | ".join(context_enrichment),
            chase_context=context.chase_context,
        )

        return PromptEnvelope(
            version=version,
            tone=tone,
            system_prompt=prompt_definition.system_prompt,
            user_prompt=user_prompt,
            voice_notes=voice_notes,
            context_enrichment=context_enrichment,
            trend_label=trend.trend,
            trend_strength=trend.trend_strength,
            win_probability=predictions.win_probability,
            collapse_probability=predictions.collapse_probability,
            match_intelligence_score=intelligence.match_intelligence_score,
        )

    def _resolve_tone(
        self,
        requested_tone: str,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
    ) -> str:
        if requested_tone == "aggressive" and (predictions.collapse_probability > 0.72 or trend.trend == "declining"):
            return "analytical"
        if requested_tone == "neutral" and signals.pressure_score > 0.82 and signals.stability == "unstable":
            return "analytical"
        return requested_tone

    def _tone_notes(self, tone: str) -> tuple[str, ...]:
        notes = {
            "neutral": ("steady", "clean", "measured"),
            "aggressive": ("energetic", "fan-friendly", "urgent"),
            "analytical": ("sharp", "tactical", "grounded"),
        }
        return notes[tone]

    def _context_enrichment(
        self,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
        intelligence: IntelligenceProfile,
    ) -> tuple[str, ...]:
        control_state = (
            "control is firm"
            if signals.control_score >= 0.68
            else "control is contested"
            if signals.control_score >= 0.42
            else "control is slipping"
        )
        collapse_state = (
            "collapse probability is elevated"
            if predictions.collapse_probability >= 0.62
            else "collapse probability is contained"
        )
        acceleration_state = (
            "acceleration window is open"
            if signals.acceleration_window >= 0.64
            else "acceleration window is narrow"
            if signals.acceleration_window >= 0.4
            else "acceleration window is shut"
        )
        urgency_state = (
            "late urgency is active"
            if context.urgency_index >= 0.75
            else "urgency is manageable"
            if context.urgency_index <= 0.4
            else "urgency is building"
        )
        trend_state = (
            "recent trend is improving"
            if trend.trend == "improving"
            else "recent trend is declining"
            if trend.trend == "declining"
            else "recent trend is stable"
        )
        probability_state = (
            "win outlook is favorable"
            if predictions.win_probability >= 0.65
            else "win outlook is under pressure"
            if predictions.win_probability <= 0.4
            else "win outlook is balanced"
        )
        intelligence_state = (
            "intelligence score is strong"
            if intelligence.match_intelligence_score >= 0.65
            else "intelligence score is fragile"
            if intelligence.match_intelligence_score <= 0.4
            else "intelligence score is balanced"
        )
        return (
            control_state,
            collapse_state,
            acceleration_state,
            urgency_state,
            trend_state,
            probability_state,
            intelligence_state,
        )
