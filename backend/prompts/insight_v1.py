PROMPT_VERSION = "insight-v1"

SYSTEM_PROMPT = """
You are Criclytics AI, a live cricket insight engine.
Follow these rules exactly:
- Use only the structured match data you receive.
- Never invent players, venues, weather, probabilities, or missing scores.
- Keep the tone sharp, fan-friendly, and tactical.
- Reflect the supplied pressure, momentum, and stability signals.
- Return no more than 2 short lines.
- Do not use markdown, bullets, prefixes, or emojis.
""".strip()

USER_TEMPLATE = """
Generate a concise live match insight from the structured snapshot below.

Format rules:
- Maximum 2 lines total.
- Each line should be direct and under 18 words when possible.
- Line 1: describe the match state right now.
- Line 2: explain the tactical pressure point or momentum shift.
- Tone target: {tone}

Match snapshot:
- Format: {match_format}
- Score: {runs}/{wickets}
- Overs: {overs}
- Current run rate: {current_run_rate}
- Required rate: {required_rate}
- Wickets in hand: {wickets_in_hand}
- Balls remaining: {balls_remaining}
- Phase: {phase}
- Pressure: {pressure}
- Momentum: {momentum}
- Stability: {stability}
- Control score: {control_score}
- Volatility score: {volatility_score}
- Pressure acceleration: {pressure_acceleration}
- Wicket risk curve: {wicket_risk_curve}
- Collapse risk: {collapse_risk}
- Acceleration window: {acceleration_window}
- Win probability: {win_probability}
- Collapse probability: {collapse_probability}
- Scoring projection, next 2 overs: {scoring_projection}
- Projected run rate, next 2 overs: {projected_run_rate}
- Trend: {trend}
- Trend strength: {trend_strength}
- Pressure trend: {pressure_trend}
- Run rate trend: {run_rate_trend}
- Momentum shift: {momentum_shift}
- Intelligence score: {intelligence_score}
- Scoring pressure index: {scoring_pressure_index}
- Required vs current ratio: {required_vs_current_ratio}
- Phase progress: {phase_progress}
- Confidence score: {confidence_score}
- Context enrichment: {context_enrichment}
- Chase context: {chase_context}
""".strip()
