from pathlib import Path

import pytest

from app.forensics.c2pa_check import check_c2pa

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_absent_manifest_is_not_treated_as_suspicious():
    sig = check_c2pa(FIXTURES / "plain_photo.jpg")
    assert sig.applicable is True
    assert sig.direction <= 0.2
    assert "No C2PA" in sig.summary


@pytest.mark.skipif(not (FIXTURES / "c2pa_signed_valid.jpg").exists(), reason="c2pa fixtures unavailable")
def test_valid_signature_leans_authentic_and_is_not_tampered():
    sig = check_c2pa(FIXTURES / "c2pa_signed_valid.jpg")
    assert sig.direction < 0
    assert "validation_errors" in sig.details
    assert sig.details["validation_errors"] == []


@pytest.mark.skipif(not (FIXTURES / "c2pa_tampered.jpg").exists(), reason="c2pa fixtures unavailable")
def test_tampered_signature_is_flagged_invalid():
    sig = check_c2pa(FIXTURES / "c2pa_tampered.jpg")
    assert sig.direction > 0.5
    assert len(sig.details["validation_errors"]) > 0
    assert "INVALID" in sig.summary
