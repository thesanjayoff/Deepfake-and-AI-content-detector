from pathlib import Path

from app.forensics.audio_forensics import basic_audio_properties, codec_trace_heuristic, speaker_comparison

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_basic_properties_reads_duration_and_rate():
    props = basic_audio_properties(FIXTURES / "voice_clean.wav")
    assert props["duration_s"] > 3.0
    assert props["sample_rate"] > 0


def test_telephony_rate_detected():
    props = basic_audio_properties(FIXTURES / "voice_phone_noisy.wav")
    sig = codec_trace_heuristic(FIXTURES / "voice_phone_noisy.wav", props["sample_rate"])
    assert "phone" in sig.summary.lower() or "codec" in sig.summary.lower()


def test_speaker_comparison_same_source_is_more_similar_than_different_speaker():
    same = speaker_comparison(FIXTURES / "voice_clean.wav", FIXTURES / "voice_reference.wav")
    different = speaker_comparison(FIXTURES / "voice_clean.wav", FIXTURES / "voice_different_speaker.wav")
    assert same.details["cosine_similarity"] > different.details["cosine_similarity"]


def test_speaker_comparison_never_contributes_to_combination():
    # High voice similarity must NOT be treated as evidence of authenticity --
    # this is a hard product requirement, enforced by strength=0.
    sig = speaker_comparison(FIXTURES / "voice_clean.wav", FIXTURES / "voice_reference.wav")
    assert sig.strength == 0.0
    assert "NOT prove authenticity" in sig.limits or "not" in sig.limits.lower()
