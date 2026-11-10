from app.combine import combine
from app.quality import QualityWarning
from app.signals import Signal


def _sig(key, direction, strength, weight=1.0, applicable=True):
    return Signal(
        key=key, label=key, category="forensic", direction=direction, strength=strength,
        summary="", limits="", weight_in_combination=weight, applicable=applicable,
    )


def test_no_usable_signals_is_inconclusive_insufficient():
    result = combine([_sig("a", 0.0, 0.0)], [])
    assert result.verdict == "inconclusive"
    assert result.confidence_band == "insufficient"


def test_strong_consistent_manipulated_signals_yield_likely_manipulated():
    signals = [_sig("a", 0.9, 0.8), _sig("b", 0.8, 0.7)]
    result = combine(signals, [])
    assert result.verdict == "likely_manipulated"


def test_strong_consistent_authentic_signals_yield_likely_authentic():
    signals = [_sig("a", -0.9, 0.8), _sig("b", -0.8, 0.7)]
    result = combine(signals, [])
    assert result.verdict == "likely_authentic"


def test_conflicting_strong_signals_force_inconclusive():
    signals = [_sig("a", 0.9, 0.9), _sig("b", -0.9, 0.9)]
    result = combine(signals, [])
    assert result.verdict == "inconclusive"
    assert result.confidence_band == "conflicting"


def test_quality_warnings_dampen_toward_inconclusive():
    signals = [_sig("a", 0.6, 0.6)]
    result_good = combine(signals, [])
    result_bad_quality = combine(signals, [QualityWarning("q", "bad", 0.2)])
    assert abs(result_bad_quality.lean_score) < abs(result_good.lean_score)


def test_non_applicable_signals_are_excluded():
    signals = [_sig("a", 0.9, 0.9, applicable=False), _sig("b", 0.0, 0.0)]
    result = combine(signals, [])
    assert result.contributions == []


def test_contributions_are_sorted_by_magnitude():
    signals = [_sig("small", 0.2, 0.3), _sig("big", 0.9, 0.9)]
    result = combine(signals, [])
    assert result.contributions[0].key == "big"
