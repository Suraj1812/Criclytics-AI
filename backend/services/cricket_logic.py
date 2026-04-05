from __future__ import annotations

from dataclasses import dataclass

from backend.models.schemas import AnalyzeRequest, overs_to_balls


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _round_metric(value: float, digits: int = 3) -> float:
    return round(value, digits)


@dataclass(frozen=True)
class MatchContext:
    runs: int
    wickets: int
    total_overs: int
    total_balls: int
    overs_completed: str
    balls_bowled: int
    balls_remaining: int
    balls_remaining_ratio: float
    current_run_rate: float
    required_rate: float
    wickets_in_hand: int
    phase: str
    chase_context: str
    innings_progress: float
    phase_progress: float
    wickets_lost_ratio: float
    wickets_in_hand_ratio: float
    rate_gap: float
    required_vs_current_ratio: float
    urgency_index: float
    scoring_pressure_index: float


def build_match_context(match_state: AnalyzeRequest) -> MatchContext:
    balls_bowled = overs_to_balls(match_state.overs)
    total_balls = match_state.total_overs * 6
    balls_remaining = max(total_balls - balls_bowled, 0)
    balls_remaining_ratio = _round_metric(clamp(balls_remaining / total_balls if total_balls else 0.0, 0.0, 1.0))
    wickets_in_hand = max(10 - match_state.wickets, 0)

    current_run_rate = 0.0
    if balls_bowled > 0:
        current_run_rate = round((match_state.runs * 6) / balls_bowled, 2)

    required_rate = round(match_state.required_rate, 2)
    phase = determine_phase(balls_bowled, match_state.total_overs)
    innings_progress = _round_metric(clamp(balls_bowled / total_balls if total_balls else 0.0, 0.0, 1.0))
    phase_progress = _round_metric(compute_phase_progress(balls_bowled, match_state.total_overs, phase))
    wickets_lost_ratio = _round_metric(clamp(match_state.wickets / 10, 0.0, 1.0))
    wickets_in_hand_ratio = _round_metric(clamp(wickets_in_hand / 10, 0.0, 1.0))
    rate_gap = round(current_run_rate - required_rate, 2)
    required_vs_current_ratio = _round_metric(
        required_rate / max(current_run_rate, 0.25),
    ) if required_rate > 0 else 0.0
    urgency_index = _round_metric(compute_urgency_index(phase, phase_progress, balls_remaining_ratio, required_vs_current_ratio))
    scoring_pressure_index = _round_metric(
        compute_scoring_pressure_index(
            phase=phase,
            total_overs=match_state.total_overs,
            current_run_rate=current_run_rate,
            required_rate=required_rate,
            required_vs_current_ratio=required_vs_current_ratio,
            wickets_in_hand_ratio=wickets_in_hand_ratio,
            balls_remaining_ratio=balls_remaining_ratio,
        )
    )
    chase_context = determine_chase_context(current_run_rate, required_rate, rate_gap)

    return MatchContext(
        runs=match_state.runs,
        wickets=match_state.wickets,
        total_overs=match_state.total_overs,
        total_balls=total_balls,
        overs_completed=match_state.overs,
        balls_bowled=balls_bowled,
        balls_remaining=balls_remaining,
        balls_remaining_ratio=balls_remaining_ratio,
        current_run_rate=current_run_rate,
        required_rate=required_rate,
        wickets_in_hand=wickets_in_hand,
        phase=phase,
        chase_context=chase_context,
        innings_progress=innings_progress,
        phase_progress=phase_progress,
        wickets_lost_ratio=wickets_lost_ratio,
        wickets_in_hand_ratio=wickets_in_hand_ratio,
        rate_gap=rate_gap,
        required_vs_current_ratio=required_vs_current_ratio,
        urgency_index=urgency_index,
        scoring_pressure_index=scoring_pressure_index,
    )


def determine_phase(balls_bowled: int, total_overs: int) -> str:
    powerplay_end, death_start = _phase_boundaries(total_overs)
    if balls_bowled < powerplay_end:
        return "powerplay"
    if balls_bowled < death_start:
        return "middle"
    return "death"


def compute_phase_progress(balls_bowled: int, total_overs: int, phase: str) -> float:
    powerplay_end, death_start = _phase_boundaries(total_overs)
    total_balls = total_overs * 6

    if phase == "powerplay":
        phase_start, phase_end = 0, max(powerplay_end, 1)
    elif phase == "middle":
        phase_start, phase_end = powerplay_end, max(death_start, powerplay_end + 1)
    else:
        phase_start, phase_end = death_start, max(total_balls, death_start + 1)

    phase_span = max(phase_end - phase_start, 1)
    return clamp((balls_bowled - phase_start) / phase_span, 0.0, 1.0)


def compute_urgency_index(
    phase: str,
    phase_progress: float,
    balls_remaining_ratio: float,
    required_vs_current_ratio: float,
) -> float:
    phase_pressure = {"powerplay": 0.22, "middle": 0.52, "death": 0.84}[phase]
    rate_component = clamp((required_vs_current_ratio - 0.94) / 0.92, 0.0, 1.0) if required_vs_current_ratio > 0 else 0.0
    return clamp(
        (0.42 * (1.0 - balls_remaining_ratio))
        + (0.28 * phase_progress)
        + (0.18 * phase_pressure)
        + (0.12 * rate_component),
        0.0,
        1.0,
    )


def compute_scoring_pressure_index(
    *,
    phase: str,
    total_overs: int,
    current_run_rate: float,
    required_rate: float,
    required_vs_current_ratio: float,
    wickets_in_hand_ratio: float,
    balls_remaining_ratio: float,
) -> float:
    phase_component = {"powerplay": 0.24, "middle": 0.48, "death": 0.82}[phase]
    resource_component = clamp(1.0 - wickets_in_hand_ratio, 0.0, 1.0)
    time_component = clamp(1.0 - balls_remaining_ratio, 0.0, 1.0)

    if required_rate > 0:
        rate_component = clamp((required_vs_current_ratio - 0.9) / 0.88, 0.0, 1.0)
    else:
        baseline_rate = _phase_baseline_rate(total_overs, phase)
        rate_component = clamp((baseline_rate - current_run_rate + 2.4) / 6.0, 0.0, 1.0)

    return clamp(
        (0.46 * rate_component)
        + (0.22 * resource_component)
        + (0.18 * time_component)
        + (0.14 * phase_component),
        0.0,
        1.0,
    )


def determine_chase_context(current_run_rate: float, required_rate: float, rate_gap: float) -> str:
    if required_rate <= 0:
        return "setting up the innings"
    if rate_gap >= 0.75:
        return "ahead of the asking rate"
    if rate_gap >= -0.35:
        return "tracking the asking rate"
    return "behind the asking rate"


def _phase_boundaries(total_overs: int) -> tuple[int, int]:
    if total_overs <= 20:
        return 36, 90

    total_balls = total_overs * 6
    powerplay_end = max(int(total_balls * 0.2), 1)
    death_start = max(int(total_balls * 0.8), powerplay_end + 1)
    return powerplay_end, death_start


def _phase_baseline_rate(total_overs: int, phase: str) -> float:
    format_factor = clamp(20 / max(total_overs, 5), 0.45, 1.35)
    base_rates = {"powerplay": 7.6, "middle": 7.0, "death": 9.1}
    return base_rates[phase] * format_factor
