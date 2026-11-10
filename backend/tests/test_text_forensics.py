from pathlib import Path

from app.forensics.text_forensics import (
    MANDATORY_TEXT_WARNING,
    burstiness_signal,
    repetition_signal,
    scam_text_indicators,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_mandatory_warning_text_exists_and_is_strong():
    assert "HIGH" in MANDATORY_TEXT_WARNING
    assert "never" in MANDATORY_TEXT_WARNING.lower()


def test_repetitive_text_flagged_higher_than_human_text():
    human = (FIXTURES / "sample_human_text.txt").read_text(encoding="utf-8")
    ai_like = (FIXTURES / "sample_ai_like_text.txt").read_text(encoding="utf-8")
    human_rep = repetition_signal(human)
    ai_rep = repetition_signal(ai_like)
    assert ai_rep.details["repeated_fraction"] > human_rep.details["repeated_fraction"]


def test_scam_text_flags_urgency_and_payment_and_secrecy():
    scam_text = (FIXTURES / "sample_scam_text.txt").read_text(encoding="utf-8")
    sig = scam_text_indicators(scam_text)
    assert sig.direction > 0.3
    assert sig.details["urgency_hits"] or sig.details["payment_hits"]


def test_clean_text_has_no_scam_indicators():
    sig = scam_text_indicators("The weather today is sunny with a light breeze from the west.")
    assert sig.direction == 0.0


def test_burstiness_not_applicable_on_tiny_text():
    sig = burstiness_signal("Hi there. How are you?")
    assert sig.applicable is False
