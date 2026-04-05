from __future__ import annotations

import hashlib
from time import perf_counter
from typing import Optional

from backend.models.schemas import AnalyzeRequest, ComputedMetrics, InsightResponse, ScoringProjection, SignalSummary, TrendSummary
from backend.services.cache_service import CacheService
from backend.services.cricket_logic import MatchContext, build_match_context
from backend.services.fallback_service import FallbackInsightService
from backend.services.predictor_engine import PredictionProfile
from backend.services.predictor_engine import PredictorEngine
from backend.services.prompt_engine import PromptEngine
from backend.services.scoring_engine import IntelligenceProfile
from backend.services.scoring_engine import ScoringEngine
from backend.services.signal_engine import SignalEngine
from backend.services.signal_engine import SignalProfile
from backend.services.text_engine import TextGenerationEngine
from backend.services.trend_engine import TrendEngine
from backend.services.trend_engine import TrendProfile
from backend.utils.config import Settings
from backend.utils.logging import get_logger
from backend.utils.monitoring import record_event, record_metric


logger = get_logger("criclytics.analysis")


class AnalysisService:
    def __init__(
        self,
        settings: Settings,
        cache_service: CacheService,
        signal_engine: SignalEngine,
        predictor_engine: PredictorEngine,
        trend_engine: TrendEngine,
        scoring_engine: ScoringEngine,
        prompt_engine: PromptEngine,
        text_engine: TextGenerationEngine,
        fallback_service: FallbackInsightService,
    ) -> None:
        self.settings = settings
        self.cache_service = cache_service
        self.signal_engine = signal_engine
        self.predictor_engine = predictor_engine
        self.trend_engine = trend_engine
        self.scoring_engine = scoring_engine
        self.prompt_engine = prompt_engine
        self.text_engine = text_engine
        self.fallback_service = fallback_service

    async def analyze(self, match_state: AnalyzeRequest, client_id: str = "anonymous") -> InsightResponse:
        started_at = perf_counter()
        prompt_version = self.prompt_engine.resolve_version(match_state.prompt_version)
        cache_key = self._build_cache_key(match_state, prompt_version)

        stage_timings: dict[str, float] = {}
        cache_lookup_started = perf_counter()
        cached_payload = await self.cache_service.get_json(cache_key)
        self._record_stage(stage_timings, "cache_lookup", cache_lookup_started)

        if cached_payload:
            cached_response = InsightResponse.model_validate(cached_payload)
            refreshed = await self._refresh_cached_response(client_id, cached_response)
            refreshed.cached = True
            record_metric("analysis.cache_hit", 1)
            record_metric("analysis.cache_hit_ratio_sample", 1.0)
            record_metric("analysis.total_ms", round((perf_counter() - started_at) * 1000, 2), {"source": "cache"})
            record_event("analysis.stage_timings", {name: str(value) for name, value in stage_timings.items()})
            return refreshed

        record_metric("analysis.cache_miss", 1)
        record_metric("analysis.cache_hit_ratio_sample", 0.0)

        engine_started = perf_counter()

        context_started = perf_counter()
        context = build_match_context(match_state)
        self._record_stage(stage_timings, "context", context_started)

        signals_started = perf_counter()
        signals = self.signal_engine.build(context)
        self._record_stage(stage_timings, "signals", signals_started)

        predictor_started = perf_counter()
        predictions = self.predictor_engine.predict(context, signals)
        self._record_stage(stage_timings, "predictor", predictor_started)

        trend_started = perf_counter()
        trend = await self.trend_engine.observe(client_id, context, signals, predictions)
        self._record_stage(stage_timings, "trend", trend_started)

        scoring_started = perf_counter()
        intelligence = self.scoring_engine.score(context, signals, predictions, trend)
        self._record_stage(stage_timings, "scoring", scoring_started)

        prompt_started = perf_counter()
        prompt = self.prompt_engine.build(match_state, context, signals, predictions, trend, intelligence)
        self._record_stage(stage_timings, "prompt", prompt_started)
        record_event(
            "analysis.prompt_built",
            {
                "version": prompt.version,
                "phase": context.phase,
                "tone": prompt.tone,
                "trend": trend.trend,
            },
        )

        source = "engine"
        try:
            text_started = perf_counter()
            insight = self.text_engine.generate(match_state, prompt, context, signals, predictions, trend, intelligence)
            self._record_stage(stage_timings, "text", text_started, tags={"source": "engine"})
            record_metric("analysis.engine_success", 1)
        except Exception as exc:
            logger.warning("Text generation failed, using fallback: %s", exc)
            fallback_started = perf_counter()
            insight = self.fallback_service.generate(match_state, context, signals, predictions, trend, intelligence)
            source = "fallback"
            self._record_stage(stage_timings, "text", fallback_started, tags={"source": "fallback"})
            record_metric("analysis.engine_fallback", 1)

        engine_duration_ms = round((perf_counter() - engine_started) * 1000, 2)
        record_metric("analysis.engine_ms", engine_duration_ms, {"source": source})

        response = InsightResponse(
            insight=insight,
            source=source,
            prompt_version=prompt.version,
            tone=prompt.tone,
            confidence=intelligence.confidence_score,
            win_probability=predictions.win_probability,
            collapse_probability=predictions.collapse_probability,
            match_intelligence_score=intelligence.match_intelligence_score,
            scoring_projection=self._build_projection(predictions),
            trend=self._build_trend_summary(trend),
            signals=self._build_signal_summary(signals, intelligence),
            metrics=self._build_metrics(context),
        )

        cache_write_started = perf_counter()
        await self.cache_service.set_json(
            cache_key,
            response.model_dump(mode="json"),
            ttl_seconds=self._resolve_cache_ttl(context, signals, predictions, trend),
        )
        self._record_stage(stage_timings, "cache_write", cache_write_started)

        total_ms = round((perf_counter() - started_at) * 1000, 2)
        record_metric("analysis.total_ms", total_ms, {"source": source})
        record_event("analysis.stage_timings", {name: str(value) for name, value in stage_timings.items()})

        return response

    async def _refresh_cached_response(self, client_id: str, response: InsightResponse) -> InsightResponse:
        trend = await self.trend_engine.observe_cached(
            client_id,
            current_run_rate=response.metrics.current_run_rate,
            wickets=10 - response.metrics.wickets_in_hand,
            pressure_score=response.signals.pressure_score,
            control_score=response.signals.control_score,
            win_probability=response.win_probability,
        )
        intelligence = self.scoring_engine.score_snapshot(
            innings_progress=response.metrics.innings_progress,
            data_consistency_score=response.signals.data_consistency_score,
            control_score=response.signals.control_score,
            pressure_score=response.signals.pressure_score,
            momentum_score=response.signals.momentum_score,
            stability_score=response.signals.stability_score,
            volatility_score=response.signals.volatility_score,
            win_probability=response.win_probability,
            collapse_probability=response.collapse_probability,
            trend=trend.trend,
            trend_strength=trend.trend_strength,
        )
        updated_signals = response.signals.model_copy(update={"confidence_score": intelligence.confidence_score})
        return response.model_copy(
            update={
                "trend": self._build_trend_summary(trend),
                "confidence": intelligence.confidence_score,
                "match_intelligence_score": intelligence.match_intelligence_score,
                "signals": updated_signals,
            }
        )

    def _build_signal_summary(self, signals: SignalProfile, intelligence: IntelligenceProfile) -> SignalSummary:
        return SignalSummary(
            pressure=signals.pressure,
            momentum=signals.momentum,
            stability=signals.stability,
            pressure_score=signals.pressure_score,
            momentum_score=signals.momentum_score,
            stability_score=signals.stability_score,
            control_score=signals.control_score,
            match_control_index=signals.match_control_index,
            volatility_score=signals.volatility_score,
            pressure_acceleration=signals.pressure_acceleration,
            wicket_risk_curve=signals.wicket_risk_curve,
            collapse_risk=signals.collapse_risk,
            acceleration_window=signals.acceleration_window,
            data_consistency_score=signals.data_consistency_score,
            confidence_score=intelligence.confidence_score,
        )

    def _build_trend_summary(self, trend: TrendProfile) -> TrendSummary:
        return TrendSummary(
            trend=trend.trend,
            momentum_shift=trend.momentum_shift,
            run_rate_trend=trend.run_rate_trend,
            pressure_trend=trend.pressure_trend,
            wicket_fall_pattern=trend.wicket_fall_pattern,
            trend_strength=trend.trend_strength,
        )

    def _build_projection(self, predictions: PredictionProfile) -> ScoringProjection:
        return ScoringProjection(
            expected_runs=predictions.scoring_projection.expected_runs,
            low_runs=predictions.scoring_projection.low_runs,
            high_runs=predictions.scoring_projection.high_runs,
            projected_run_rate=predictions.scoring_projection.projected_run_rate,
        )

    def _build_metrics(self, context: MatchContext) -> ComputedMetrics:
        return ComputedMetrics(
            current_run_rate=context.current_run_rate,
            required_rate=context.required_rate,
            wickets_in_hand=context.wickets_in_hand,
            wickets_in_hand_ratio=context.wickets_in_hand_ratio,
            phase=context.phase,
            overs_completed=context.overs_completed,
            balls_remaining=context.balls_remaining,
            chase_context=context.chase_context,
            innings_progress=context.innings_progress,
            phase_progress=context.phase_progress,
            scoring_pressure_index=context.scoring_pressure_index,
            required_vs_current_ratio=context.required_vs_current_ratio,
            rate_gap=context.rate_gap,
        )

    def _build_cache_key(self, match_state: AnalyzeRequest, prompt_version: str) -> str:
        fingerprint = "|".join(
            [
                self.settings.cache_namespace,
                self.settings.text_engine_model,
                prompt_version,
                match_state.tone,
                str(match_state.total_overs),
                str(match_state.seed),
                str(match_state.runs),
                str(match_state.wickets),
                match_state.overs,
                f"{match_state.required_rate:.2f}",
            ]
        ).encode("utf-8")
        digest = hashlib.blake2b(fingerprint, digest_size=10).hexdigest()
        return f"analysis:{self.settings.cache_namespace}:{prompt_version}:{digest}"

    def _resolve_cache_ttl(
        self,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
    ) -> int:
        ttl = self.settings.cache_ttl_seconds

        phase_adjustments = {"powerplay": 26, "middle": -8, "death": -72}
        ttl += phase_adjustments[context.phase]
        ttl -= int(signals.volatility_score * 54)
        ttl -= int(predictions.collapse_probability * 38)
        ttl -= int((1 - abs(predictions.win_probability - 0.5) * 2) * 18)
        ttl += int(signals.stability_score * 20)
        ttl += 8 if trend.trend == "stable" else -10

        if context.balls_remaining <= 18:
            ttl -= 18
        if context.phase == "death" and context.balls_remaining <= 12:
            ttl -= 10

        return max(self.settings.cache_ttl_min_seconds, min(self.settings.cache_ttl_max_seconds, ttl))

    def _record_stage(
        self,
        stage_timings: dict[str, float],
        stage_name: str,
        started_at: float,
        tags: Optional[dict[str, str]] = None,
    ) -> None:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        stage_timings[stage_name] = duration_ms
        record_metric(f"analysis.{stage_name}_ms", duration_ms, tags=tags)
