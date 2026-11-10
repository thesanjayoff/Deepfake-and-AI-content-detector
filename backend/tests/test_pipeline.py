from pathlib import Path

from app import config, pipeline

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_scam_text_does_not_flip_the_authenticity_verdict():
    """A scam message is almost always human-typed -- the scam/fraud signal
    must be shown but must not drive the AI/manipulation verdict."""
    report = pipeline.analyze_text(FIXTURES / "sample_scam_text.txt", config.DEFAULT_SETTINGS, "t_scam")
    scam_signal = next(s for s in report["signals"] if s["key"] == "text.scam_indicators")
    assert scam_signal["direction"] > 0.3  # the scam signal itself still fires
    contributions = {c["key"] for c in report["combination"]["contributions"]}
    assert "text.scam_indicators" not in contributions


def test_image_pipeline_flags_known_splice_as_manipulated():
    report = pipeline.analyze_image(FIXTURES / "spliced_photo.jpg", config.DEFAULT_SETTINGS, "t_splice")
    assert report["combination"]["verdict"] == "likely_manipulated"


def test_image_pipeline_leaves_plain_photo_inconclusive():
    report = pipeline.analyze_image(FIXTURES / "plain_photo.jpg", config.DEFAULT_SETTINGS, "t_plain")
    assert report["combination"]["verdict"] != "likely_manipulated"
