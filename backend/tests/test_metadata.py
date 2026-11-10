from pathlib import Path

from app.forensics.metadata import analyze_image_metadata, analyze_text_file_metadata

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_missing_exif_is_not_flagged_as_suspicious():
    sig, meta = analyze_image_metadata(FIXTURES / "plain_photo.jpg")
    assert sig.direction <= 0.1
    assert "not" in sig.summary.lower() or "no" in sig.summary.lower()


def test_text_metadata_is_not_applicable():
    sig = analyze_text_file_metadata(FIXTURES / "sample_human_text.txt")
    assert sig.applicable is False
