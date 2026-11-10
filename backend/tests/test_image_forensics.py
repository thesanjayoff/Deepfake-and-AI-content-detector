from pathlib import Path

from app.forensics.image_forensics import copy_move_detection, noise_residual_analysis

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_copy_move_detects_duplicated_region_in_spliced_image():
    plain_sig, _ = copy_move_detection(FIXTURES / "plain_photo.jpg")
    spliced_sig, _ = copy_move_detection(FIXTURES / "spliced_photo.jpg")
    assert spliced_sig.details["largest_displacement_cluster"] > plain_sig.details["largest_displacement_cluster"]
    assert spliced_sig.strength > plain_sig.strength
    assert spliced_sig.direction > 0.5


def test_plain_photo_does_not_strongly_trigger_copy_move():
    sig, _ = copy_move_detection(FIXTURES / "plain_photo.jpg")
    assert sig.strength < 0.5


def test_noise_residual_runs_without_crashing_on_plain_photo():
    sig, heatmap = noise_residual_analysis(FIXTURES / "plain_photo.jpg")
    assert 0.0 <= sig.strength <= 1.0
    assert heatmap is not None
