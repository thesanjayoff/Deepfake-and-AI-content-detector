from app.quality import audio_quality_warnings, image_quality_warnings, text_quality_warnings, video_quality_warnings


def test_small_image_flagged():
    warnings = image_quality_warnings(200, 150, 5000, True, 80)
    assert any(w.key == "image.very_small" for w in warnings)


def test_large_clean_image_not_flagged():
    warnings = image_quality_warnings(3000, 2000, 2_000_000, True, 92)
    assert warnings == []


def test_heavy_jpeg_compression_flagged():
    warnings = image_quality_warnings(2000, 1500, 100_000, True, 35)
    assert any(w.key == "image.heavy_compression" for w in warnings)


def test_short_audio_flagged():
    warnings = audio_quality_warnings(1.0, 16000)
    assert any(w.key == "audio.very_short" for w in warnings)


def test_telephony_rate_flagged_but_not_fatal():
    warnings = audio_quality_warnings(10.0, 8000)
    assert any(w.key == "audio.telephony_rate" for w in warnings)
    w = next(w for w in warnings if w.key == "audio.telephony_rate")
    assert 0.0 < w.reliability_factor < 1.0


def test_short_text_flagged():
    warnings = text_quality_warnings(100, 20)
    assert any(w.key == "text.very_short" for w in warnings)


def test_low_res_video_flagged():
    warnings = video_quality_warnings(10.0, 320, 240, 20)
    assert any(w.key == "video.low_resolution" for w in warnings)
