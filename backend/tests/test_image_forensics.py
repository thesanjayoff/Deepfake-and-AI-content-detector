from pathlib import Path

from PIL import Image

from app.forensics.image_forensics import copy_move_detection, error_level_analysis, noise_residual_analysis

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


def test_ela_does_not_false_positive_on_near_lossless_recompression(tmp_path):
    # Regression test: when an image recompresses almost losslessly (tiny
    # absolute ELA error), the heterogeneity RATIO used to blow up toward
    # infinity and falsely saturate direction/strength to 1.0 on ordinary,
    # unedited images. See image_forensics.error_level_analysis.
    with Image.open(FIXTURES / "plain_photo.jpg") as im:
        small = im.convert("RGB").resize((160, 120))
        path = tmp_path / "near_lossless.jpg"
        small.save(path, "JPEG", quality=90)

    sig, _ = error_level_analysis(path, quality=90)
    assert sig.direction < 0.3
    assert sig.strength < 0.3
