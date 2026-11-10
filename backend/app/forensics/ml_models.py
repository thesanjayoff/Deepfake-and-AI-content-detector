"""
Optional, heavier pretrained-model signals (Hugging Face image classifiers,
GPT-2 perplexity in text_forensics.py). Off by default -- enable via Settings
-> 'Use optional ML models', which requires installing requirements-ml.txt.

Every model here is reported as its OWN separate signal with explicit
training-data provenance and known limits, never folded silently into a
black-box score, per the project's honesty requirements.
"""
from __future__ import annotations

from pathlib import Path

from ..signals import Signal

_IMAGE_PIPELINE_CACHE: dict[str, object] = {}

IMAGE_MODEL_NAME = "umm-maybe/AI-image-detector"
LIMITS_IMAGE_MODEL = (
    f"This is a single third-party model ('{IMAGE_MODEL_NAME}') trained on a specific, limited set "
    "of real/AI image pairs. It generalizes poorly to generators or image styles unlike its "
    "training data, can be fooled by simple resizing/cropping/recompression, and should never be "
    "treated as authoritative on its own -- it is one weak vote among many signals in this report."
)


def ai_image_detector_signal(path: Path, enable_ml: bool) -> Signal:
    if not enable_ml:
        return Signal(
            key="image.ml_detector", label="Pretrained AI-Image Detector", category="model",
            direction=0.0, strength=0.0,
            summary="Not run: optional ML models are disabled in Settings.",
            limits=LIMITS_IMAGE_MODEL, applicable=False,
        )
    try:
        from transformers import pipeline
    except ImportError:
        return Signal(
            key="image.ml_detector", label="Pretrained AI-Image Detector", category="model",
            direction=0.0, strength=0.0,
            summary="Not available: optional ML dependencies (torch/transformers) are not installed. "
                    "See README 'Optional ML extras'.",
            limits=LIMITS_IMAGE_MODEL, applicable=False,
        )

    try:
        if IMAGE_MODEL_NAME not in _IMAGE_PIPELINE_CACHE:
            _IMAGE_PIPELINE_CACHE[IMAGE_MODEL_NAME] = pipeline("image-classification", model=IMAGE_MODEL_NAME)
        clf = _IMAGE_PIPELINE_CACHE[IMAGE_MODEL_NAME]
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGB")
            results = clf(im)
    except Exception as e:
        return Signal(
            key="image.ml_detector", label="Pretrained AI-Image Detector", category="model",
            direction=0.0, strength=0.0,
            summary=f"Model could not run (it may need to download on first use with internet "
                    f"access, which 'fully local mode' blocks): {e}",
            limits=LIMITS_IMAGE_MODEL, applicable=False,
        )

    ai_score = 0.0
    for r in results:
        label = str(r.get("label", "")).lower()
        if "fake" in label or "ai" in label or "generated" in label or "artificial" in label:
            ai_score = max(ai_score, float(r.get("score", 0.0)))

    direction = float((ai_score - 0.5) * 1.6)
    strength = 0.5
    summary = (
        f"Model's top signal for 'AI-generated' style content: {ai_score*100:.0f}% confidence "
        f"(model's own confidence score, not a calibrated probability of being fake)."
    )

    return Signal(
        key="image.ml_detector", label="Pretrained AI-Image Detector", category="model",
        direction=direction, strength=strength, summary=summary, limits=LIMITS_IMAGE_MODEL,
        details={"model": IMAGE_MODEL_NAME, "raw_results": results},
    )
