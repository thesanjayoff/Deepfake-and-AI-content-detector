"""Orchestrates per-media-type analysis into one unified report dict."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from . import config
from .combine import combine
from .forensics import audio_forensics, c2pa_check, image_forensics, metadata, ml_models, text_forensics, video_forensics
from .quality import (
    QualityWarning,
    audio_quality_warnings,
    image_quality_warnings,
    text_quality_warnings,
    video_quality_warnings,
)
from .signals import Signal
from .verification import SCAM_CALL_SAFE_WORD_TIP, steps_for


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _evidence_dir_for(report_id: str) -> Path:
    d = config.EVIDENCE_DIR / report_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_evidence(evidence_dir: Path, name: str, data: bytes | None) -> str | None:
    if not data:
        return None
    path = evidence_dir / name
    path.write_bytes(data)
    return name


def analyze_image(path: Path, settings: dict[str, str], report_id: str) -> dict[str, Any]:
    evidence_dir = _evidence_dir_for(report_id)
    enable_ml = settings.get("use_optional_ml_models") == "true"

    from PIL import Image
    with Image.open(path) as im:
        width, height = im.size
        is_jpeg = im.format == "JPEG"
    size_bytes = path.stat().st_size
    estimated_quality = image_forensics.estimate_jpeg_quality(path) if is_jpeg else None

    qw = image_quality_warnings(width, height, size_bytes, is_jpeg, estimated_quality)

    c2pa_signal = c2pa_check.check_c2pa(path)
    meta_signal, meta_raw = metadata.analyze_image_metadata(path)

    ela_signal, ela_png = image_forensics.error_level_analysis(path)
    noise_signal, noise_png = image_forensics.noise_residual_analysis(path)
    ghost_signal, ghost_png = image_forensics.double_compression_ghost(path)
    copymove_signal, copymove_png = image_forensics.copy_move_detection(path)
    lighting_signal = image_forensics.lighting_consistency_heuristic(path)
    ml_signal = ml_models.ai_image_detector_signal(path, enable_ml)

    evidence_files = {}
    evidence_files["ela_heatmap"] = _save_evidence(evidence_dir, "ela_heatmap.png", ela_png)
    evidence_files["noise_heatmap"] = _save_evidence(evidence_dir, "noise_heatmap.png", noise_png)
    evidence_files["ghost_heatmap"] = _save_evidence(evidence_dir, "ghost_heatmap.png", ghost_png)
    evidence_files["copymove_overlay"] = _save_evidence(evidence_dir, "copymove_overlay.png", copymove_png)
    evidence_files = {k: v for k, v in evidence_files.items() if v}

    signals = [c2pa_signal, meta_signal, ela_signal, noise_signal, ghost_signal, copymove_signal, lighting_signal, ml_signal]
    combination = combine(signals, qw)

    return {
        "media_type": "image",
        "dimensions": {"width": width, "height": height},
        "estimated_jpeg_quality": estimated_quality,
        "quality_warnings": [w.to_dict() for w in qw],
        "signals": [s.to_dict() for s in signals],
        "combination": combination.to_dict(),
        "verification_steps": steps_for("image"),
        "evidence": evidence_files,
        "metadata_raw": meta_raw,
        "robustness_note": image_forensics.robustness_note(estimated_quality, width, height),
    }


def analyze_text(path: Path, settings: dict[str, str], report_id: str) -> dict[str, Any]:
    enable_ml = settings.get("use_optional_ml_models") == "true"
    text = path.read_text(encoding="utf-8", errors="replace")
    stats = text_forensics.basic_stats(text)
    qw = text_quality_warnings(stats["num_chars"], stats["num_words"])

    burst = text_forensics.burstiness_signal(text)
    rep = text_forensics.repetition_signal(text)
    style = text_forensics.style_consistency_signal(text)
    perplex = text_forensics.perplexity_signal(text, enable_ml)
    scam = text_forensics.scam_text_indicators(text)
    meta_signal = metadata.analyze_text_file_metadata(path)

    signals = [meta_signal, burst, rep, style, perplex, scam]
    combination = combine(signals, qw)

    return {
        "media_type": "text",
        "mandatory_warning": text_forensics.MANDATORY_TEXT_WARNING,
        "num_words": stats["num_words"],
        "num_sentences": stats["num_sentences"],
        "quality_warnings": [w.to_dict() for w in qw],
        "signals": [s.to_dict() for s in signals],
        "combination": combination.to_dict(),
        "verification_steps": steps_for("text"),
        "evidence": {},
        "text_preview": text[:4000],
    }


def _audio_signals(path: Path, reference_path: Path | None) -> tuple[list[Signal], dict[str, Any], list[QualityWarning]]:
    props = audio_forensics.basic_audio_properties(path)
    qw = audio_quality_warnings(props["duration_s"], props["sample_rate"])

    meta_signal = metadata.analyze_audio_metadata(path)
    breathing_signal = audio_forensics.breathing_and_room_noise(path)
    codec_signal = audio_forensics.codec_trace_heuristic(path, props["sample_rate"])
    spoof_signal = audio_forensics.spoofing_heuristic(path)

    signals: list[Signal] = [meta_signal, breathing_signal, codec_signal, spoof_signal]
    if reference_path is not None:
        signals.append(audio_forensics.speaker_comparison(path, reference_path))
    return signals, props, qw


def analyze_audio(path: Path, settings: dict[str, str], report_id: str,
                   reference_path: Path | None = None) -> dict[str, Any]:
    evidence_dir = _evidence_dir_for(report_id)
    signals, props, qw = _audio_signals(path, reference_path)

    spectrogram_png = None
    try:
        spectrogram_png = audio_forensics.make_spectrogram_png(path)
    except Exception:
        pass
    evidence_files = {"spectrogram": _save_evidence(evidence_dir, "spectrogram.png", spectrogram_png)}
    evidence_files = {k: v for k, v in evidence_files.items() if v}

    combination = combine(signals, qw)

    return {
        "media_type": "audio",
        "duration_s": props["duration_s"],
        "sample_rate": props["sample_rate"],
        "quality_warnings": [w.to_dict() for w in qw],
        "signals": [s.to_dict() for s in signals],
        "combination": combination.to_dict(),
        "verification_steps": steps_for("audio"),
        "evidence": evidence_files,
        "scam_call_checklist": audio_forensics.SCAM_CALL_CHECKLIST,
        "safe_word_guidance": SCAM_CALL_SAFE_WORD_TIP,
    }


def analyze_video(path: Path, settings: dict[str, str], report_id: str) -> dict[str, Any]:
    evidence_dir = _evidence_dir_for(report_id)
    info = video_forensics.probe_video(path)
    frames = video_forensics.extract_sampled_frames(path)
    qw = video_quality_warnings(info["duration_s"], info["width"], info["height"], len(frames))

    meta_signal = metadata.analyze_video_metadata(path)
    frame_signal, flicker_signal, timeline_data, thumb_png = video_forensics.analyze_frames(frames)
    blink_sig, lipsync_sig, avalign_sig = video_forensics.blink_and_lipsync_unavailable()

    signals: list[Signal] = [meta_signal, frame_signal, flicker_signal, blink_sig, lipsync_sig, avalign_sig]

    audio_report = None
    audio_spectrogram_png = None
    if info["has_audio"]:
        audio_wav = evidence_dir / "extracted_audio.wav"
        if video_forensics.extract_audio_track(path, audio_wav):
            audio_signals, audio_props, audio_qw = _audio_signals(audio_wav, None)
            for s in audio_signals:
                s.key = f"video.audio_track.{s.key}"
                s.label = f"[Audio track] {s.label}"
                signals.append(s)
            audio_combination = combine(audio_signals, audio_qw)
            try:
                audio_spectrogram_png = audio_forensics.make_spectrogram_png(audio_wav)
            except Exception:
                pass
            audio_report = {
                "duration_s": audio_props["duration_s"],
                "sample_rate": audio_props["sample_rate"],
                "quality_warnings": [w.to_dict() for w in audio_qw],
                "signals": [s.to_dict() for s in audio_signals],
                "combination": audio_combination.to_dict(),
            }

    evidence_files = {"frame_thumbnail": _save_evidence(evidence_dir, "frame_thumbnail.png", thumb_png)}
    evidence_files["audio_spectrogram"] = _save_evidence(evidence_dir, "audio_spectrogram.png", audio_spectrogram_png)
    evidence_files = {k: v for k, v in evidence_files.items() if v}

    combination = combine(signals, qw)

    return {
        "media_type": "video",
        "duration_s": info["duration_s"],
        "dimensions": {"width": info["width"], "height": info["height"]},
        "fps": info["fps"],
        "has_audio": info["has_audio"],
        "quality_warnings": [w.to_dict() for w in qw],
        "signals": [s.to_dict() for s in signals],
        "combination": combination.to_dict(),
        "verification_steps": steps_for("video"),
        "evidence": evidence_files,
        "timeline": timeline_data.get("timeline", []),
        "audio_track_report": audio_report,
    }
