from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


OVERS_PATTERN = re.compile(r"^\d+(?:\.[0-5])?$")


def normalize_overs_input(value: Union[str, int, float]) -> str:
    if isinstance(value, str):
        normalized = value.strip()
    else:
        normalized = str(value)

    if "." not in normalized:
        normalized = f"{normalized}.0"

    if not OVERS_PATTERN.fullmatch(normalized):
        raise ValueError("Overs must use cricket notation such as 7.2 or 14.0")

    return normalized


def overs_to_balls(overs: str) -> int:
    whole, _, partial = overs.partition(".")
    return (int(whole) * 6) + int(partial or "0")


class AnalyzeRequest(BaseModel):
    runs: int = Field(..., ge=0, le=500, description="Current team runs")
    wickets: int = Field(..., ge=0, le=10, description="Wickets lost")
    overs: str = Field(..., description="Overs completed in cricket notation, for example 12.4")
    required_rate: float = Field(..., ge=0, le=36, description="Required run rate for the chase")
    total_overs: int = Field(default=20, ge=5, le=50, description="Innings length in overs")
    tone: Literal["neutral", "aggressive", "analytical", "excited"] = Field(default="analytical")
    prompt_version: Optional[str] = Field(default=None, description="Optional prompt version override")
    seed: int = Field(default=7, ge=0, le=1_000_000, description="Seed for deterministic variation")

    @field_validator("overs", mode="before")
    @classmethod
    def normalize_overs(cls, value: Union[str, int, float]) -> str:
        return normalize_overs_input(value)

    @field_validator("tone", mode="before")
    @classmethod
    def normalize_tone(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized == "excited":
            return "aggressive"
        return normalized

    @field_validator("prompt_version")
    @classmethod
    def validate_prompt_version(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if len(normalized) > 32:
            raise ValueError("Prompt version must be 32 characters or fewer")
        return normalized

    @model_validator(mode="after")
    def validate_match_state(self) -> "AnalyzeRequest":
        balls_used = overs_to_balls(self.overs)
        innings_balls = self.total_overs * 6
        if balls_used > innings_balls:
            raise ValueError("Overs cannot exceed the innings length")
        if balls_used == 0 and self.required_rate > 0 and self.runs > 36:
            raise ValueError("Runs look implausibly high for zero overs completed")
        return self


class TrendSummary(BaseModel):
    trend: Literal["improving", "declining", "stable"]
    momentum_shift: bool
    run_rate_trend: Literal["increasing", "decreasing", "flat"]
    pressure_trend: Literal["rising", "falling", "steady"]
    wicket_fall_pattern: Literal["stable", "watchful", "fragile"]
    trend_strength: float = Field(..., ge=0.0, le=1.0)


class ScoringProjection(BaseModel):
    expected_runs: float = Field(..., ge=0.0, le=60.0)
    low_runs: int = Field(..., ge=0, le=60)
    high_runs: int = Field(..., ge=0, le=60)
    projected_run_rate: float = Field(..., ge=0.0, le=36.0)


class SignalSummary(BaseModel):
    pressure: Literal["low", "medium", "high"]
    momentum: Literal["positive", "neutral", "negative"]
    stability: Literal["stable", "unstable"]
    pressure_score: float = Field(..., ge=0.0, le=1.0)
    momentum_score: float = Field(..., ge=0.0, le=1.0)
    stability_score: float = Field(..., ge=0.0, le=1.0)
    control_score: float = Field(..., ge=0.0, le=1.0)
    match_control_index: float = Field(..., ge=0.0, le=1.0)
    volatility_score: float = Field(..., ge=0.0, le=1.0)
    pressure_acceleration: float = Field(..., ge=0.0, le=1.0)
    wicket_risk_curve: float = Field(..., ge=0.0, le=1.0)
    collapse_risk: float = Field(..., ge=0.0, le=1.0)
    acceleration_window: float = Field(..., ge=0.0, le=1.0)
    data_consistency_score: float = Field(..., ge=0.0, le=1.0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)


class ComputedMetrics(BaseModel):
    current_run_rate: float
    required_rate: float
    wickets_in_hand: int
    wickets_in_hand_ratio: float = Field(..., ge=0.0, le=1.0)
    phase: Literal["powerplay", "middle", "death"]
    overs_completed: str
    balls_remaining: int
    chase_context: str
    innings_progress: float = Field(..., ge=0.0, le=1.0)
    phase_progress: float = Field(..., ge=0.0, le=1.0)
    scoring_pressure_index: float = Field(..., ge=0.0, le=1.0)
    required_vs_current_ratio: float = Field(..., ge=0.0, le=10.0)
    rate_gap: float


class InsightResponse(BaseModel):
    insight: str
    source: Literal["engine", "fallback"]
    cached: bool = False
    prompt_version: str
    tone: Literal["neutral", "aggressive", "analytical"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    win_probability: float = Field(..., ge=0.0, le=1.0)
    collapse_probability: float = Field(..., ge=0.0, le=1.0)
    match_intelligence_score: float = Field(..., ge=0.0, le=1.0)
    scoring_projection: ScoringProjection
    trend: TrendSummary
    signals: SignalSummary
    metrics: ComputedMetrics
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    cache: Literal["up", "degraded"]
    text_engine: Literal["ready"]
    prompt_version: str
    environment: str


class ErrorResponse(BaseModel):
    detail: str
    error_code: str
