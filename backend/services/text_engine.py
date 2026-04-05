from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from itertools import islice
from itertools import product

from backend.models.schemas import AnalyzeRequest
from backend.services.cricket_logic import MatchContext
from backend.services.predictor_engine import PredictionProfile
from backend.services.prompt_engine import PromptEnvelope
from backend.services.scoring_engine import IntelligenceProfile
from backend.services.signal_engine import SignalProfile
from backend.services.trend_engine import TrendProfile


TOKEN_PATTERN = re.compile(r"[a-zA-Z']+")


@dataclass(frozen=True)
class PhraseOption:
    text: str
    weight: float
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SentenceCandidate:
    text: str
    score: float


@dataclass(frozen=True)
class ResponseCandidate:
    text: str
    score: float


class TextGenerationEngine:
    def __init__(self, model_name: str = "signal-synthesizer-v1", default_seed: int = 7) -> None:
        self.model_name = model_name
        self.default_seed = default_seed

    @property
    def ready(self) -> bool:
        return True

    def generate(
        self,
        request: AnalyzeRequest,
        prompt: PromptEnvelope,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
        intelligence: IntelligenceProfile,
    ) -> str:
        rng = self._build_rng(request, prompt, context, signals, predictions, trend, intelligence)
        line_one_candidates = self._build_line_one_candidates(prompt, request, context, signals, predictions, trend, intelligence)
        line_two_candidates = self._build_line_two_candidates(prompt, context, signals, predictions, trend, intelligence)
        response_candidates = self._build_response_candidates(
            prompt,
            context,
            signals,
            predictions,
            trend,
            intelligence,
            line_one_candidates,
            line_two_candidates,
        )
        return self._select_response_candidate(rng, response_candidates)

    def _build_rng(
        self,
        request: AnalyzeRequest,
        prompt: PromptEnvelope,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
        intelligence: IntelligenceProfile,
    ) -> random.Random:
        effective_seed = request.seed if request.seed is not None else self.default_seed
        seed_material = (
            f"{self.model_name}|{effective_seed}|{prompt.version}|{prompt.tone}|{request.model_dump_json()}|"
            f"{context.current_run_rate:.2f}|{signals.pressure_score:.2f}|{signals.control_score:.2f}|"
            f"{signals.volatility_score:.2f}|{predictions.win_probability:.2f}|{predictions.collapse_probability:.2f}|"
            f"{trend.trend}|{trend.trend_strength:.2f}|{intelligence.match_intelligence_score:.2f}"
        )
        digest = hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
        return random.Random(int(digest[:16], 16))

    def _build_line_one_candidates(
        self,
        prompt: PromptEnvelope,
        request: AnalyzeRequest,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
        intelligence: IntelligenceProfile,
    ) -> list[SentenceCandidate]:
        phase_label = {
            "powerplay": "powerplay",
            "middle": "middle stretch",
            "death": "closing stretch",
        }[context.phase]
        state_options = [
            PhraseOption("well under control", 0.88, ("control", "prob_high")),
            PhraseOption("tilting in their favor", 0.84, ("control", "trend_up")),
            PhraseOption("holding steady but still live", 0.86, ("balanced",)),
            PhraseOption("finely balanced", 0.9, ("balanced",)),
            PhraseOption("turning volatile", 0.82, ("volatility",)),
            PhraseOption("tightening against the batting side", 0.86, ("pressure", "prob_low")),
            PhraseOption("slipping under pressure", 0.84, ("pressure", "trend_down")),
            PhraseOption("on the edge of a swing", 0.8, ("volatility", "urgent")),
        ]
        opener_options = {
            "neutral": [
                PhraseOption("This {phase} passage is {state}; {runs}/{wickets} after {overs}.", 0.88),
                PhraseOption("{runs}/{wickets} after {overs} and this {phase} remains {state}.", 0.82),
                PhraseOption("The live picture stays {state}; {runs}/{wickets} after {overs}.", 0.78),
            ],
            "aggressive": [
                PhraseOption("The {phase} has real edge now; {runs}/{wickets} after {overs} and it feels {state}.", 0.9, ("urgent",)),
                PhraseOption("This match is humming; {runs}/{wickets} after {overs} and the {phase} is {state}.", 0.84, ("attack",)),
                PhraseOption("The tempo is live here; {runs}/{wickets} after {overs} and this {phase} is {state}.", 0.8, ("attack",)),
            ],
            "analytical": [
                PhraseOption("The live picture is {state}; {runs}/{wickets} after {overs} in this {phase}.", 0.92, ("analytical",)),
                PhraseOption("From a control view, this {phase} is {state}; {runs}/{wickets} after {overs}.", 0.86, ("control", "analytical")),
                PhraseOption("This {phase} profile is {state}; {runs}/{wickets} after {overs} at {crr} RPO.", 0.82, ("analytical",)),
            ],
        }

        ranked_states = self._rank_phrases(state_options, prompt, context, signals, predictions, trend, intelligence)
        ranked_openers = self._rank_phrases(opener_options[prompt.tone], prompt, context, signals, predictions, trend, intelligence)
        candidates: list[SentenceCandidate] = []

        for opener, state in product(islice(ranked_openers, 0, 4), islice(ranked_states, 0, 4)):
            sentence = opener.text.format(
                phase=phase_label,
                state=state.text,
                runs=request.runs,
                wickets=request.wickets,
                overs=context.overs_completed,
                crr=f"{context.current_run_rate:.2f}",
            )
            score = opener.weight + state.weight + self._sentence_quality_score(
                sentence,
                prompt,
                context,
                signals,
                predictions,
                trend,
                intelligence,
            )
            candidates.append(SentenceCandidate(text=sentence, score=round(score, 4)))

        return candidates

    def _build_line_two_candidates(
        self,
        prompt: PromptEnvelope,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
        intelligence: IntelligenceProfile,
    ) -> list[SentenceCandidate]:
        tactical_options = {
            "powerplay|stable": [
                PhraseOption("This is still the phase to build stability before the field spreads.", 0.86, ("control",)),
                PhraseOption("There is room to cash in, but clean batting matters more than force.", 0.84, ("attack",)),
                PhraseOption("Powerplay control is worth more than a low-percentage swing.", 0.82, ("analytical",)),
            ],
            "powerplay|unstable": [
                PhraseOption("Stability has to come first before any push in tempo.", 0.88, ("protect",)),
                PhraseOption("Another wicket now would distort the whole innings shape.", 0.86, ("pressure", "urgent")),
                PhraseOption("The first correction is to settle the base, not chase headlines.", 0.82, ("analytical", "protect")),
            ],
            "middle|stable": [
                PhraseOption("This is the bridge to a strong finish if they keep the base intact.", 0.9, ("control",)),
                PhraseOption("The next overs can unlock acceleration without forcing the equation.", 0.88, ("attack", "analytical")),
                PhraseOption("This is still a controllable middle-overs passage.", 0.84, ("analytical",)),
            ],
            "middle|unstable": [
                PhraseOption("Momentum has to be rebuilt before they can chase a launch.", 0.88, ("protect", "trend_down")),
                PhraseOption("The next few balls matter because another wobble would deepen the squeeze.", 0.86, ("pressure", "urgent")),
                PhraseOption("Singles and shape are more valuable than a risky release shot right now.", 0.84, ("analytical", "protect")),
            ],
            "death|stable": [
                PhraseOption("The finish is there if execution stays clean under the lights.", 0.9, ("attack", "prob_high")),
                PhraseOption("Death-overs control now matters more than raw intent.", 0.88, ("analytical",)),
                PhraseOption("One clean over could move this sharply in their favor.", 0.86, ("attack", "trend_up")),
            ],
            "death|unstable": [
                PhraseOption("Every quiet ball now drags the equation the wrong way.", 0.9, ("pressure", "urgent")),
                PhraseOption("The death overs are amplifying every mistake at this point.", 0.88, ("pressure", "volatility")),
                PhraseOption("Risk is unavoidable here, but wicket loss would be fatal.", 0.86, ("protect", "urgent")),
            ],
        }
        prediction_options = [
            PhraseOption("Win probability is leaning their way if this passage stays clean.", 0.86, ("prob_high", "control")),
            PhraseOption("Win probability is starting to drift because the rate pressure is climbing.", 0.86, ("prob_low", "pressure")),
            PhraseOption("The next two overs project a manageable scoring window.", 0.8, ("projection_high", "control")),
            PhraseOption("The next two overs project only a narrow scoring return unless they reset control.", 0.82, ("projection_low", "pressure")),
            PhraseOption("Collapse probability is staying contained for now.", 0.78, ("collapse_low",)),
            PhraseOption("Collapse probability is rising with the wicket-risk curve.", 0.86, ("collapse_high", "pressure")),
        ]
        trend_options = [
            PhraseOption("Momentum has shifted after consecutive tight passages.", 0.86, ("shift", "trend_down")),
            PhraseOption("The recent trend is nudging control back toward the batting side.", 0.84, ("trend_up", "control")),
            PhraseOption("The recent pattern is steady, so this still turns on execution.", 0.78, ("balanced",)),
            PhraseOption("Pressure trend is rising and that is squeezing their margin.", 0.84, ("pressure", "trend_down")),
        ]
        pressure_options = {
            "low": [
                PhraseOption("Pressure is manageable.", 0.82, ("control",)),
                PhraseOption("Pressure is still under control.", 0.8, ("control",)),
            ],
            "medium": [
                PhraseOption("Pressure is building.", 0.86, ("pressure",)),
                PhraseOption("Pressure is rising through this phase.", 0.84, ("pressure", "analytical")),
            ],
            "high": [
                PhraseOption("Pressure is fully on.", 0.9, ("pressure", "urgent")),
                PhraseOption("Pressure is right on top of them now.", 0.88, ("pressure", "urgent")),
            ],
        }
        enrichment_options = [
            PhraseOption("The acceleration window is open if they keep shape.", 0.82, ("attack", "control")),
            PhraseOption("The wicket-risk curve is now the hidden variable.", 0.84, ("pressure", "analytical")),
            PhraseOption("Volatility is climbing, so the next over carries outsized value.", 0.86, ("volatility", "urgent")),
            PhraseOption("Control score still gives them a route back into the chase.", 0.8, ("control", "trend_up")),
        ]

        tactical_key = f"{context.phase}|{signals.stability}"
        ranked_tactical = self._rank_phrases(tactical_options[tactical_key], prompt, context, signals, predictions, trend, intelligence)
        ranked_prediction = self._rank_phrases(prediction_options, prompt, context, signals, predictions, trend, intelligence)
        ranked_trend = self._rank_phrases(trend_options, prompt, context, signals, predictions, trend, intelligence)
        ranked_pressure = self._rank_phrases(pressure_options[signals.pressure], prompt, context, signals, predictions, trend, intelligence)
        ranked_enrichment = self._rank_phrases(enrichment_options, prompt, context, signals, predictions, trend, intelligence)

        candidates: list[SentenceCandidate] = []
        for tactical, prediction, trend_phrase, pressure, enrichment in product(
            islice(ranked_tactical, 0, 3),
            islice(ranked_prediction, 0, 4),
            islice(ranked_trend, 0, 3),
            islice(ranked_pressure, 0, 2),
            islice(ranked_enrichment, 0, 2),
        ):
            fragments = [tactical.text]

            if trend.trend_strength >= 0.22 or trend.momentum_shift:
                fragments.append(trend_phrase.text)

            if abs(predictions.win_probability - 0.5) >= 0.1 or predictions.collapse_probability >= 0.5:
                fragments.append(prediction.text)

            if signals.volatility_score >= 0.62 or context.phase == "death":
                fragments.append(enrichment.text)

            fragments.append(pressure.text)
            sentence = self._merge_fragments(fragments, prompt)
            score = (
                tactical.weight
                + prediction.weight
                + pressure.weight
                + (0.24 * trend_phrase.weight)
                + (0.18 * enrichment.weight)
            )
            score += self._sentence_quality_score(
                sentence,
                prompt,
                context,
                signals,
                predictions,
                trend,
                intelligence,
            )
            candidates.append(SentenceCandidate(text=sentence, score=round(score, 4)))

        return candidates

    def _build_response_candidates(
        self,
        prompt: PromptEnvelope,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
        intelligence: IntelligenceProfile,
        line_one_candidates: list[SentenceCandidate],
        line_two_candidates: list[SentenceCandidate],
    ) -> list[ResponseCandidate]:
        ranked_line_one = sorted(line_one_candidates, key=lambda item: item.score, reverse=True)
        ranked_line_two = sorted(line_two_candidates, key=lambda item: item.score, reverse=True)
        candidates: list[ResponseCandidate] = []

        for line_one, line_two in product(islice(ranked_line_one, 0, 5), islice(ranked_line_two, 0, 8)):
            score = line_one.score + line_two.score
            score += self._response_context_score(
                line_one.text,
                line_two.text,
                prompt,
                context,
                signals,
                predictions,
                trend,
                intelligence,
            )
            score -= self._response_diversity_penalty(line_one.text, line_two.text)
            candidates.append(
                ResponseCandidate(
                    text=self._normalize(f"{line_one.text}\n{line_two.text}"),
                    score=round(score, 4),
                )
            )

        return candidates

    def _rank_phrases(
        self,
        phrases: list[PhraseOption],
        prompt: PromptEnvelope,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
        intelligence: IntelligenceProfile,
    ) -> list[PhraseOption]:
        def phrase_score(option: PhraseOption) -> float:
            score = option.weight
            tags = set(option.tags)

            if "control" in tags:
                score += 0.34 * signals.control_score
            if "attack" in tags:
                score += 0.26 * signals.acceleration_window
            if "protect" in tags:
                score += 0.3 * predictions.collapse_probability
            if "pressure" in tags:
                score += 0.32 * signals.pressure_score
            if "balanced" in tags:
                score += 0.16 * (1 - abs(predictions.win_probability - 0.5) * 2)
            if "urgent" in tags:
                score += 0.22 * max(signals.pressure_score, signals.volatility_score, predictions.collapse_probability)
            if "analytical" in tags and prompt.tone == "analytical":
                score += 0.16
            if "trend_up" in tags and trend.trend == "improving":
                score += 0.18 * max(trend.trend_strength, 0.2)
            if "trend_down" in tags and trend.trend == "declining":
                score += 0.18 * max(trend.trend_strength, 0.2)
            if "prob_high" in tags:
                score += 0.2 * predictions.win_probability
            if "prob_low" in tags:
                score += 0.2 * (1 - predictions.win_probability)
            if "collapse_high" in tags:
                score += 0.18 * predictions.collapse_probability
            if "collapse_low" in tags:
                score += 0.14 * (1 - predictions.collapse_probability)
            if "projection_high" in tags:
                score += 0.12 * min(predictions.scoring_projection.expected_runs / 16.0, 1.0)
            if "projection_low" in tags:
                score += 0.12 * max((8.0 - predictions.scoring_projection.expected_runs) / 8.0, 0.0)
            if "volatility" in tags:
                score += 0.16 * signals.volatility_score
            if "shift" in tags and trend.momentum_shift:
                score += 0.16
            if any(note in option.text.lower() for note in prompt.voice_notes):
                score += 0.06
            if intelligence.match_intelligence_score >= 0.65 and "control" in tags:
                score += 0.08
            return score

        return sorted(phrases, key=phrase_score, reverse=True)

    def _sentence_quality_score(
        self,
        sentence: str,
        prompt: PromptEnvelope,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
        intelligence: IntelligenceProfile,
    ) -> float:
        tokens = self._tokenize(sentence)
        lexical_diversity = len(set(tokens)) / max(len(tokens), 1)
        ideal_length = 104 if prompt.tone == "analytical" else 92
        length_penalty = abs(len(sentence) - ideal_length) / 120
        score = (0.42 * lexical_diversity) - length_penalty

        lowered = sentence.lower()
        if context.phase == "death" and any(word in lowered for word in ("death", "finish", "quiet ball", "late-over")):
            score += 0.06
        if predictions.win_probability <= 0.42 and "win probability" in lowered:
            score += 0.08
        if predictions.collapse_probability >= 0.52 and "collapse probability" in lowered:
            score += 0.08
        if trend.momentum_shift and "momentum has shifted" in lowered:
            score += 0.08
        if signals.volatility_score >= 0.62 and "volatility" in lowered:
            score += 0.06
        if prompt.tone == "analytical" and any(word in lowered for word in ("control", "curve", "projection", "equation")):
            score += 0.06
        if intelligence.match_intelligence_score <= 0.42 and any(word in lowered for word in ("pressure", "risk", "tightening")):
            score += 0.05
        return score

    def _response_context_score(
        self,
        line_one: str,
        line_two: str,
        prompt: PromptEnvelope,
        context: MatchContext,
        signals: SignalProfile,
        predictions: PredictionProfile,
        trend: TrendProfile,
        intelligence: IntelligenceProfile,
    ) -> float:
        combined = f"{line_one} {line_two}".lower()
        score = 0.0

        if predictions.win_probability <= 0.42 and "win probability" in combined:
            score += 0.08
        if predictions.collapse_probability >= 0.52 and "collapse probability" in combined:
            score += 0.08
        if trend.trend == "declining" and any(word in combined for word in ("momentum", "trend", "tightening")):
            score += 0.07
        if trend.trend == "improving" and any(word in combined for word in ("control", "trend", "favor")):
            score += 0.07
        if trend.momentum_shift and "momentum has shifted" in combined:
            score += 0.07
        if signals.pressure_score >= 0.65 and "pressure" in combined:
            score += 0.06
        if signals.volatility_score >= 0.62 and "volatility" in combined:
            score += 0.06
        if intelligence.match_intelligence_score >= 0.65 and "control" in combined:
            score += 0.05
        if context.phase == "death" and any(word in combined for word in ("death", "finish", "quiet ball")):
            score += 0.05
        if prompt.tone == "analytical" and any(word in combined for word in ("curve", "projection", "equation")):
            score += 0.04
        return score

    def _response_diversity_penalty(self, left: str, right: str) -> float:
        overlap = self._lexical_overlap(left, right)
        repeated_tokens = len(set(self._tokenize(left)) & set(self._tokenize(right)))
        return (0.76 * overlap) + (0.03 * repeated_tokens)

    def _merge_fragments(self, fragments: list[str], prompt: PromptEnvelope) -> str:
        max_length = 172 if prompt.tone == "analytical" else 152
        merged: list[str] = []
        for fragment in fragments:
            trial = " ".join(merged + [fragment]).strip()
            if not merged or len(trial) <= max_length:
                merged.append(fragment)
        return " ".join(merged)

    def _select_response_candidate(self, rng: random.Random, candidates: list[ResponseCandidate]) -> str:
        ranked = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
        if not ranked:
            return ""

        unique_candidates: list[ResponseCandidate] = []
        seen = set()
        for candidate in ranked:
            normalized = candidate.text.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique_candidates.append(candidate)
            if len(unique_candidates) == 6:
                break

        if len(unique_candidates) == 1:
            return unique_candidates[0].text

        finalists = unique_candidates[: min(3, len(unique_candidates))]
        if finalists[0].score - finalists[min(1, len(finalists) - 1)].score >= 0.18:
            return finalists[0].text

        weights = [max(candidate.score, 0.01) for candidate in finalists]
        return rng.choices([candidate.text for candidate in finalists], weights=weights, k=1)[0]

    def _tokenize(self, value: str) -> list[str]:
        return TOKEN_PATTERN.findall(value.lower())

    def _lexical_overlap(self, left: str, right: str) -> float:
        left_tokens = set(self._tokenize(left))
        right_tokens = set(self._tokenize(right))
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    def _normalize(self, value: str) -> str:
        lines = [" ".join(line.split()) for line in value.splitlines()]
        cleaned = [line.strip() for line in lines if line.strip()]
        return "\n".join(cleaned[:2])
