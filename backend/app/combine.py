"""
Transparent signal combination.

Method (deliberately simple and auditable -- no hidden black box):

1. Drop signals that did not run (`applicable=False`) or carry zero strength.
2. Each remaining signal casts a weighted vote: `direction * strength * weight`.
   The combined "lean" is the weighted average of those votes, in [-1, 1].
3. Any active quality warning (low resolution, heavy compression, short clip,
   short text, ...) multiplies a `reliability_multiplier` that dampens the
   lean toward zero -- poor-quality input should pull toward "Inconclusive",
   never toward a confident verdict in either direction.
4. If strong signals disagree with each other (one strongly authentic, one
   strongly manipulated), the result is forced to "Inconclusive" rather than
   letting them cancel out into a falsely confident middle score.
5. The final lean is thresholded into one of three states. Thresholds are
   wide on purpose: "Inconclusive" is the default outcome unless evidence
   clearly clears a bar in one direction.

The per-signal contributions are returned alongside the verdict so the UI can
show exactly how each signal moved (or didn't move) the result. Nothing here
is ever rendered as a bare percentage of "is this fake."
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .quality import QualityWarning
from .signals import Signal

AUTH_THRESHOLD = 0.22
MANIPULATED_THRESHOLD = 0.22
STRONG_CONFLICT_STRENGTH = 0.5


@dataclass
class Contribution:
    key: str
    label: str
    vote: float          # direction * strength * weight, before reliability dampening
    share: float          # |vote| / sum(|vote|) -- how much of the total this signal drove


@dataclass
class CombinationResult:
    verdict: str                      # "likely_authentic" | "inconclusive" | "likely_manipulated"
    confidence_band: str              # "low" | "moderate" | "high" | "conflicting" | "insufficient"
    lean_score: float                 # -1..1, for the visual "lean" bar only -- NOT a probability
    reliability_multiplier: float
    conflict_detected: bool
    contributions: list[Contribution]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "confidence_band": self.confidence_band,
            "lean_score": round(self.lean_score, 4),
            "reliability_multiplier": round(self.reliability_multiplier, 3),
            "conflict_detected": self.conflict_detected,
            "contributions": [
                {"key": c.key, "label": c.label, "vote": round(c.vote, 4), "share": round(c.share, 4)}
                for c in self.contributions
            ],
            "explanation": self.explanation,
        }


def _reliability_multiplier(warnings: list[QualityWarning]) -> float:
    mult = 1.0
    for w in warnings:
        mult *= w.reliability_factor
    return max(0.15, mult)


def combine(signals: list[Signal], quality_warnings: list[QualityWarning]) -> CombinationResult:
    usable = [s for s in signals if s.applicable and s.strength > 0]
    reliability_multiplier = _reliability_multiplier(quality_warnings)

    if not usable:
        return CombinationResult(
            verdict="inconclusive",
            confidence_band="insufficient",
            lean_score=0.0,
            reliability_multiplier=reliability_multiplier,
            conflict_detected=False,
            contributions=[],
            explanation="No signal produced usable evidence for this file, so no verdict beyond "
                         "'Inconclusive' can be responsibly given.",
        )

    votes = [(s, s.direction * s.strength * s.weight_in_combination) for s in usable]
    denom = sum(s.strength * s.weight_in_combination for s in usable)
    raw_lean = sum(v for _, v in votes) / denom if denom else 0.0

    strong_manipulated = any(s.direction >= 0.5 and s.strength >= STRONG_CONFLICT_STRENGTH for s in usable)
    strong_authentic = any(s.direction <= -0.5 and s.strength >= STRONG_CONFLICT_STRENGTH for s in usable)
    conflict_detected = strong_manipulated and strong_authentic

    effective_lean = raw_lean * reliability_multiplier

    total_abs_vote = sum(abs(v) for _, v in votes) or 1.0
    contributions = sorted(
        (Contribution(key=s.key, label=s.label, vote=v, share=abs(v) / total_abs_vote) for s, v in votes),
        key=lambda c: abs(c.vote),
        reverse=True,
    )

    if conflict_detected:
        verdict = "inconclusive"
        band = "conflicting"
        explanation = (
            "Strong signals disagree with each other (some point toward authentic, others toward "
            "manipulated/AI-generated). Rather than letting them average into a falsely confident "
            "middle result, this is reported as Inconclusive -- conflicting strong evidence needs a "
            "human to look at the specifics below."
        )
    elif effective_lean >= MANIPULATED_THRESHOLD:
        verdict = "likely_manipulated"
        band = "high" if effective_lean >= 0.55 else "moderate" if effective_lean >= 0.35 else "low"
        explanation = (
            "The combined, reliability-adjusted evidence leans toward manipulation or AI generation. "
            "This is a lean based on the signals below, not a probability of fakery -- see each "
            "signal's own limits before treating this as settled."
        )
    elif effective_lean <= -AUTH_THRESHOLD:
        verdict = "likely_authentic"
        band = "high" if effective_lean <= -0.55 else "moderate" if effective_lean <= -0.35 else "low"
        explanation = (
            "The combined, reliability-adjusted evidence leans toward authenticity. This reflects the "
            "absence of detected tampering signals, not positive proof the content is genuine."
        )
    else:
        verdict = "inconclusive"
        band = "insufficient" if denom < 0.8 else "low"
        explanation = (
            "The evidence is weak, mixed, or close to the decision boundary. Inconclusive is the "
            "honest result here -- treat the content as unverified and use the human verification "
            "steps in this report."
        )

    return CombinationResult(
        verdict=verdict,
        confidence_band=band,
        lean_score=effective_lean,
        reliability_multiplier=reliability_multiplier,
        conflict_detected=conflict_detected,
        contributions=contributions,
        explanation=explanation,
    )
