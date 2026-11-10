"""Evaluation metrics: accuracy/precision/recall/FPR with abstention, and
calibration (Expected Calibration Error + reliability diagram bins).

Abstention policy: this app can legitimately answer "Inconclusive" instead of
picking a side. We report abstention rate separately and compute
accuracy/precision/recall/FPR only over the non-abstained predictions --
scoring "Inconclusive" as simply wrong would punish exactly the honest
behavior this project is designed to prefer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class BinaryEvalResult:
    n_total: int
    n_abstained: int
    n_decided: int
    accuracy: float | None
    precision: float | None
    recall: float | None
    false_positive_rate: float | None
    confusion: dict[str, int] = field(default_factory=dict)

    def to_dict(self):
        return {
            "n_total": self.n_total,
            "n_abstained": self.n_abstained,
            "n_decided": self.n_decided,
            "abstention_rate": round(self.n_abstained / self.n_total, 4) if self.n_total else None,
            "accuracy": round(self.accuracy, 4) if self.accuracy is not None else None,
            "precision": round(self.precision, 4) if self.precision is not None else None,
            "recall": round(self.recall, 4) if self.recall is not None else None,
            "false_positive_rate": round(self.false_positive_rate, 4) if self.false_positive_rate is not None else None,
            "confusion": self.confusion,
        }


def evaluate_binary(y_true: list[bool], y_pred: list[bool | None]) -> BinaryEvalResult:
    """y_true: True = positive class (e.g. 'is manipulated/fake').
    y_pred: True/False, or None for 'Inconclusive' (abstained)."""
    n_total = len(y_true)
    tp = fp = tn = fn = 0
    abstained = 0
    for t, p in zip(y_true, y_pred):
        if p is None:
            abstained += 1
            continue
        if t and p:
            tp += 1
        elif t and not p:
            fn += 1
        elif not t and p:
            fp += 1
        else:
            tn += 1

    n_decided = n_total - abstained
    accuracy = (tp + tn) / n_decided if n_decided else None
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    fpr = fp / (fp + tn) if (fp + tn) else None

    return BinaryEvalResult(
        n_total=n_total, n_abstained=abstained, n_decided=n_decided,
        accuracy=accuracy, precision=precision, recall=recall, false_positive_rate=fpr,
        confusion={"tp": tp, "fp": fp, "tn": tn, "fn": fn},
    )


def lean_score_to_probability(lean_score: float) -> float:
    """Maps the internal -1..1 'lean' to a 0..1 pseudo-probability PURELY for
    calibration diagnostics in this eval harness. The live app UI never shows
    this number -- it only exists here so we can honestly measure how
    over/under-confident the underlying signals are."""
    return 1.0 / (1.0 + math.exp(-3.0 * lean_score))


def expected_calibration_error(probs: list[float], y_true: list[bool], n_bins: int = 10) -> dict:
    bins = [[] for _ in range(n_bins)]
    for p, t in zip(probs, y_true):
        idx = min(n_bins - 1, int(p * n_bins))
        bins[idx].append((p, t))

    total = len(probs)
    ece = 0.0
    table = []
    for i, bucket in enumerate(bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        if not bucket:
            table.append({"bin_range": [round(lo, 2), round(hi, 2)], "count": 0, "avg_confidence": None, "accuracy": None})
            continue
        avg_conf = sum(p for p, _ in bucket) / len(bucket)
        acc = sum(1 for _, t in bucket if t) / len(bucket)
        weight = len(bucket) / total
        ece += weight * abs(avg_conf - acc)
        table.append({
            "bin_range": [round(lo, 2), round(hi, 2)], "count": len(bucket),
            "avg_confidence": round(avg_conf, 3), "accuracy": round(acc, 3),
        })
    return {"ece": round(ece, 4), "bins": table}
