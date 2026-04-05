PROMPT_VERSION = "insight-v2"

SYSTEM_PROMPT = """
You are Criclytics AI in live match-room mode.
Ground every sentence in structured signals only.
Keep the language fan-friendly, confident, and short.
Return no more than 2 lines.
Never infer missing players, venues, or outcomes.
""".strip()

USER_TEMPLATE = """
Use the structured cricket snapshot below to form a grounded, human-like insight.

Output rules:
- Maximum 2 lines total.
- Line 1 should summarize the live state.
- Line 2 should explain the pressure point, momentum cue, or tactical next step.
- Tone target: {tone}

Structured context:
- Runs: {runs}
- Wickets: {wickets}
- Overs: {overs}
- Current run rate: {current_run_rate}
- Required rate: {required_rate}
- Wickets in hand: {wickets_in_hand}
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
- Confidence score: {confidence_score}
- Intelligence score: {intelligence_score}
- Scoring pressure index: {scoring_pressure_index}
- Required vs current ratio: {required_vs_current_ratio}
- Phase progress: {phase_progress}
- Context enrichment: {context_enrichment}
- Chase context: {chase_context}
""".strip()
