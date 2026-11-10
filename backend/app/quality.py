"""Quality warnings: conditions that make ALL signals on this file less reliable."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class QualityWarning:
    key: str
    message: str
    reliability_factor: float  # multiplied into the overall reliability multiplier, <1.0

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "message": self.message, "reliability_factor": self.reliability_factor}


def image_quality_warnings(width: int, height: int, size_bytes: int, is_jpeg: bool,
                            estimated_jpeg_quality: float | None) -> list[QualityWarning]:
    warnings: list[QualityWarning] = []
    megapixels = (width * height) / 1_000_000
    if megapixels < 0.3:
        warnings.append(QualityWarning(
            "image.very_small",
            f"Very small image ({width}x{height}, {megapixels:.2f} MP). Forensic artifacts are "
            "much harder to detect reliably at low resolution.",
            0.6,
        ))
    elif megapixels < 0.8:
        warnings.append(QualityWarning(
            "image.small",
            f"Low resolution image ({width}x{height}). Some forensic signals lose reliability "
            "below ~1 megapixel.",
            0.8,
        ))
    if is_jpeg and estimated_jpeg_quality is not None and estimated_jpeg_quality < 60:
        warnings.append(QualityWarning(
            "image.heavy_compression",
            f"Heavy JPEG compression detected (estimated quality ~{estimated_jpeg_quality:.0f}/100). "
            "Compression destroys the fine detail several forensic checks rely on, and can itself "
            "mimic manipulation artifacts.",
            0.65,
        ))
    bytes_per_pixel = size_bytes / max(1, width * height)
    if is_jpeg and bytes_per_pixel < 0.15:
        warnings.append(QualityWarning(
            "image.likely_recompressed",
            "The file size is unusually small for its resolution, consistent with having been "
            "re-saved/re-compressed multiple times (e.g. downloaded, re-shared, screenshotted). "
            "This reduces confidence in error-level and double-compression analysis.",
            0.75,
        ))
    return warnings


def audio_quality_warnings(duration_s: float, sample_rate: int) -> list[QualityWarning]:
    warnings: list[QualityWarning] = []
    if duration_s < 2.0:
        warnings.append(QualityWarning(
            "audio.very_short",
            f"Very short clip ({duration_s:.1f}s). Spectral and spoofing signals need several "
            "seconds of speech to be meaningful.",
            0.5,
        ))
    elif duration_s < 5.0:
        warnings.append(QualityWarning(
            "audio.short",
            f"Short clip ({duration_s:.1f}s). Confidence is lower than for longer samples.",
            0.75,
        ))
    if sample_rate <= 8000:
        warnings.append(QualityWarning(
            "audio.telephony_rate",
            f"Low sample rate ({sample_rate} Hz), typical of phone/VoIP codecs. This both limits "
            "spectral analysis AND is itself an expected property of real phone calls -- low rate "
            "alone is not suspicious.",
            0.8,
        ))
    return warnings


def video_quality_warnings(duration_s: float, width: int, height: int, sampled_frames: int) -> list[QualityWarning]:
    warnings: list[QualityWarning] = []
    if duration_s < 2.0:
        warnings.append(QualityWarning(
            "video.very_short",
            f"Very short clip ({duration_s:.1f}s). Temporal consistency checks (flicker, blink "
            "rate, lip-sync) need more frames to be meaningful.",
            0.55,
        ))
    if min(width, height) < 360:
        warnings.append(QualityWarning(
            "video.low_resolution",
            f"Low resolution video ({width}x{height}). Face-region artifacts are much harder to "
            "detect reliably below ~360p.",
            0.65,
        ))
    if sampled_frames < 5:
        warnings.append(QualityWarning(
            "video.few_frames",
            f"Only {sampled_frames} frames could be sampled. Frame-level findings are based on a "
            "sparse sample and may miss short-lived artifacts.",
            0.7,
        ))
    return warnings


def text_quality_warnings(num_chars: int, num_words: int) -> list[QualityWarning]:
    warnings: list[QualityWarning] = []
    if num_words < 50:
        warnings.append(QualityWarning(
            "text.very_short",
            f"Very short text ({num_words} words). Statistical text signals (perplexity, "
            "burstiness, repetition) are unreliable below roughly 150-200 words and should "
            "largely be ignored here.",
            0.4,
        ))
    elif num_words < 150:
        warnings.append(QualityWarning(
            "text.short",
            f"Short text ({num_words} words). Statistical signals carry noticeably less "
            "confidence than on longer documents.",
            0.65,
        ))
    return warnings
