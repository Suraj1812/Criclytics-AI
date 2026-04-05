from backend.models.schemas import AnalyzeRequest
from backend.services.cricket_logic import MatchContext
from backend.services.predictor_engine import PredictionProfile
from backend.services.scoring_engine import IntelligenceProfile
from backend.services.signal_engine import SignalProfile
from backend.services.trend_engine import TrendProfile


class FallbackInsightService:
    def generate(
        self,
        match_state: AnalyzeRequest,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
        intelligence: IntelligenceProfile,
    ) -> str:
        line_one = (
            f"{context.phase.capitalize()} phase: {match_state.runs}/{match_state.wickets} after "
            f"{context.overs_completed}, momentum is {signals.momentum} and win probability is {predictions.win_probability:.2f}."
        )

        if context.required_rate > 0:
            line_two = (
                f"Pressure is {signals.pressure}; with {context.wickets_in_hand} wickets left, "
                f"they need control against {context.required_rate:.2f} RPO while collapse probability sits at {predictions.collapse_probability:.2f}."
            )
        else:
            line_two = (
                f"Stability is {signals.stability}; the next two overs project {predictions.scoring_projection.expected_runs:.1f} runs if control holds."
            )

        if trend.trend != "stable" and trend.trend_strength >= 0.2:
            line_two = f"{line_two[:-1]} and the recent trend is {trend.trend}."
        elif intelligence.match_intelligence_score <= 0.42:
            line_two = f"{line_two[:-1]} and the overall intelligence score is fragile."

        return "\n".join([line_one, line_two])
