"""
The core evidence vocabulary shared by every analysis module.

Every forensic check in this app produces a `Signal`, never a bare number.
A Signal always carries: what was found, how strong that finding is, which
direction it points (authentic vs. manipulated) and -- mandatorily -- its
known limitations in plain English. `combine.py` is the only place these are
aggregated, and it does so transparently (see combine.py docstring).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Direction(float, Enum):
    """Which way a signal points. Values double as the vote used in combine.py."""
    STRONGLY_AUTHENTIC = -1.0
    LEANS_AUTHENTIC = -0.5
    NEUTRAL = 0.0
    LEANS_MANIPULATED = 0.5
    STRONGLY_MANIPULATED = 1.0


@dataclass
class Signal:
    key: str                      # stable machine id, e.g. "image.ela"
    label: str                    # human label, e.g. "Error Level Analysis"
    category: str                 # "provenance" | "forensic" | "model" | "scam" | "quality"
    direction: float              # -1..1, see Direction
    strength: float               # 0..1 how much weight this signal deserves
    summary: str                  # one-line plain-English finding
    limits: str                   # mandatory: known weaknesses / false-positive modes
    weight_in_combination: float = 1.0  # relative importance vs other signals of this media type
    applicable: bool = True       # False if the check could not run (e.g. missing tool)
    details: dict[str, Any] = field(default_factory=dict)  # extra data for the UI (paths, numbers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "category": self.category,
            "direction": self.direction,
            "strength": self.strength,
            "summary": self.summary,
            "limits": self.limits,
            "weight_in_combination": self.weight_in_combination,
            "applicable": self.applicable,
            "details": self.details,
        }


def neutral(key: str, label: str, category: str, summary: str, limits: str, **kw: Any) -> Signal:
    """Helper for a signal that ran but found nothing informative (not the
    same as 'not applicable' -- it genuinely looked and found no anomaly)."""
    return Signal(
        key=key, label=label, category=category, direction=0.0, strength=kw.pop("strength", 0.2),
        summary=summary, limits=limits, **kw,
    )


def unavailable(key: str, label: str, category: str, reason: str) -> Signal:
    """Helper for a signal that could not run at all (missing optional tool,
    unsupported format, etc). Absence of a check is never evidence either way."""
    return Signal(
        key=key, label=label, category=category, direction=0.0, strength=0.0,
        summary=f"Not available: {reason}",
        limits="This check did not run, so it contributes no evidence in either direction.",
        applicable=False,
    )
