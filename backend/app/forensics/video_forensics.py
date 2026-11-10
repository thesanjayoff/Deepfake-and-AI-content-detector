"""
Video forensics: frame sampling, per-frame forensic scoring (a timeline), a
face-region temporal-flicker heuristic, container/re-encode anomaly checks,
and audio-track extraction so the full audio pipeline can run on it too.

Decoding uses PyAV, which bundles its own FFmpeg libraries -- no system
ffmpeg install is required.

Honesty note: genuine blink-rate and lip-sync mismatch detection require a
facial-landmark model this app does not bundle (keeping the install light
and fully local). Those two checks are reported as explicitly unavailable
rather than faked with a weaker proxy that could mislead.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import av
import cv2
import numpy as np
import soundfile as sf
from PIL import Image

from ..config import MAX_VIDEO_SAMPLED_FRAMES
from ..signals import Signal, unavailable

_FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

LIMITS_FRAME_FORENSICS = (
    "Per-frame checks reuse the same image-forensics heuristics (error level, noise residual) on "
    "a sparse sample of frames -- video compression (especially inter-frame/B-frame compression) "
    "produces its own artifacts that can be mistaken for editing, and sampling will miss short-"
    "lived artifacts between sampled frames."
)
LIMITS_FLICKER = (
    "This tracks frame-to-frame brightness changes specifically within the detected face region "
    "versus the rest of the frame. Real faces also flicker under changing light, camera auto-"
    "exposure, or compression -- and face-swap artifacts can be subtle enough to evade this "
    "simple heuristic entirely."
)
LIMITS_CONTAINER = (
    "Re-encoding and container-anomaly checks can flag ordinary re-exports (e.g. messaging app "
    "compression) as well as genuine edits -- they tell you the file has an editing/transcoding "
    "history, not what was changed or why."
)


def _sample_timestamps(duration_s: float, max_frames: int) -> list[float]:
    if duration_s <= 0:
        return [0.0]
    n = max(2, min(max_frames, int(duration_s * 2)))  # ~2 fps sampling, capped
    return list(np.linspace(0.05 * duration_s, 0.95 * duration_s, n))


def probe_video(path: Path) -> dict[str, Any]:
    with av.open(str(path)) as container:
        vstream = next((s for s in container.streams if s.type == "video"), None)
        astream = next((s for s in container.streams if s.type == "audio"), None)
        duration_s = float(container.duration / 1_000_000) if container.duration else 0.0
        width = vstream.width if vstream else 0
        height = vstream.height if vstream else 0
        fps = float(vstream.average_rate) if vstream and vstream.average_rate else 0.0
        return {
            "duration_s": duration_s, "width": width, "height": height, "fps": fps,
            "has_audio": astream is not None,
        }


def extract_sampled_frames(path: Path, max_frames: int = MAX_VIDEO_SAMPLED_FRAMES) -> list[tuple[float, np.ndarray]]:
    info = probe_video(path)
    duration_s = info["duration_s"] or 1.0
    targets = _sample_timestamps(duration_s, max_frames)

    frames: list[tuple[float, np.ndarray]] = []
    with av.open(str(path)) as container:
        vstream = next((s for s in container.streams if s.type == "video"), None)
        if vstream is None:
            return frames
        vstream.thread_type = "AUTO"
        next_target_idx = 0
        for frame in container.decode(vstream):
            if next_target_idx >= len(targets):
                break
            t = float(frame.pts * frame.time_base) if frame.pts is not None else 0.0
            if t >= targets[next_target_idx]:
                arr = frame.to_ndarray(format="rgb24")
                frames.append((t, arr))
                next_target_idx += 1
    return frames


def extract_audio_track(path: Path, out_wav_path: Path) -> bool:
    try:
        with av.open(str(path)) as container:
            astream = next((s for s in container.streams if s.type == "audio"), None)
            if astream is None:
                return False
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            chunks = []
            for frame in container.decode(astream):
                for rframe in resampler.resample(frame):
                    chunks.append(rframe.to_ndarray())
            if not chunks:
                return False
            data = np.concatenate(chunks, axis=1).astype(np.int16).flatten()
            sf.write(out_wav_path, data, 16000, subtype="PCM_16")
            return True
    except Exception:
        return False


def _frame_forensic_score(arr: np.ndarray) -> float:
    """Lightweight per-frame ELA-like score (0..1) for the timeline chart."""
    im = Image.fromarray(arr)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    buf.seek(0)
    with Image.open(buf) as rc:
        rc_arr = np.array(rc, dtype=np.float32)
    diff = np.abs(arr.astype(np.float32) - rc_arr).mean()
    return float(np.clip(diff / 20.0, 0.0, 1.0))


def _detect_face(gray: np.ndarray) -> tuple[int, int, int, int] | None:
    faces = _FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(40, 40))
    if len(faces) == 0:
        return None
    return tuple(max(faces, key=lambda f: f[2] * f[3]))  # largest face


def analyze_frames(frames: list[tuple[float, np.ndarray]]) -> tuple[Signal, Signal, dict[str, Any], bytes | None]:
    """Returns (frame_forensics_signal, flicker_signal, timeline_dict, sample_thumbnail_png)."""
    if not frames:
        unavailable_sig = unavailable("video.frame_forensics", "Per-Frame Forensics", "forensic", "No frames could be decoded.")
        unavailable_flicker = unavailable("video.face_flicker", "Face-Region Temporal Flicker", "forensic", "No frames decoded.")
        return unavailable_sig, unavailable_flicker, {"timeline": []}, None

    timeline = []
    face_boxes: list[tuple[float, tuple[int, int, int, int]] | None] = []
    prev_face_gray_mean = None
    prev_frame_gray_mean = None
    face_deltas = []
    frame_deltas = []

    for t, arr in frames:
        score = _frame_forensic_score(arr)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        face = _detect_face(gray)
        entry: dict[str, Any] = {"t": round(t, 3), "frame_score": round(score, 4), "face_detected": face is not None}

        frame_mean = float(gray.mean())
        if prev_frame_gray_mean is not None:
            frame_deltas.append(abs(frame_mean - prev_frame_gray_mean))
        prev_frame_gray_mean = frame_mean

        if face is not None:
            x, y, w, h = face
            face_mean = float(gray[y:y + h, x:x + w].mean())
            entry["face_box"] = [int(x), int(y), int(w), int(h)]
            if prev_face_gray_mean is not None:
                face_deltas.append(abs(face_mean - prev_face_gray_mean))
            prev_face_gray_mean = face_mean
        else:
            prev_face_gray_mean = None

        timeline.append(entry)

    scores = [e["frame_score"] for e in timeline]
    mean_score = float(np.mean(scores))
    peak_score = float(np.max(scores))
    hot_frames = [e for e in timeline if e["frame_score"] > mean_score + 2 * np.std(scores) and e["frame_score"] > 0.3]

    direction1 = float(np.clip((peak_score - 0.4) * 1.5, -0.1, 0.7)) if hot_frames else -0.05
    strength1 = float(np.clip(len(hot_frames) / max(1, len(timeline)) * 4, 0.1, 0.7))
    summary1 = (
        f"Mean per-frame forensic score {mean_score:.2f}, peak {peak_score:.2f} across {len(timeline)} "
        f"sampled frames. "
        + (f"{len(hot_frames)} frame(s) stand out well above the rest." if hot_frames
           else "No frames stand out as unusually different from the rest.")
    )
    frame_signal = Signal(
        key="video.frame_forensics", label="Per-Frame Forensics (sampled)", category="forensic",
        direction=direction1, strength=strength1, summary=summary1, limits=LIMITS_FRAME_FORENSICS,
        details={"hot_frame_timestamps": [e["t"] for e in hot_frames]},
    )

    faces_seen = sum(1 for e in timeline if e["face_detected"])
    if faces_seen < 3 or not face_deltas:
        flicker_signal = Signal(
            key="video.face_flicker", label="Face-Region Temporal Flicker", category="forensic",
            direction=0.0, strength=0.1,
            summary=f"Face detected in only {faces_seen}/{len(timeline)} sampled frames -- not enough "
                    f"to assess temporal flicker reliably.",
            limits=LIMITS_FLICKER,
        )
    else:
        avg_face_delta = float(np.mean(face_deltas))
        avg_frame_delta = float(np.mean(frame_deltas)) + 1e-6
        ratio = avg_face_delta / avg_frame_delta
        direction2 = float(np.clip((ratio - 1.4) * 0.6, -0.1, 0.6))
        strength2 = float(np.clip((ratio - 1.0) * 0.5, 0.15, 0.55))
        summary2 = (
            f"Face-region brightness changes {ratio:.2f}x faster frame-to-frame than the rest of the "
            f"frame (across {faces_seen} frames with a detected face). "
            + ("This is elevated and can indicate boundary/blending artifacts from face "
               "manipulation -- or just changing facial expression/lighting." if ratio > 1.4
               else "This is within a normal range.")
        )
        flicker_signal = Signal(
            key="video.face_flicker", label="Face-Region Temporal Flicker", category="forensic",
            direction=direction2, strength=strength2, summary=summary2, limits=LIMITS_FLICKER,
            details={"face_to_frame_delta_ratio": ratio, "faces_seen": faces_seen},
        )

    thumb_png = None
    try:
        mid = frames[len(frames) // 2][1]
        thumb_png = _to_png(Image.fromarray(mid).resize((480, int(480 * mid.shape[0] / mid.shape[1]))))
    except Exception:
        pass

    return frame_signal, flicker_signal, {"timeline": timeline}, thumb_png


def _to_png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def blink_and_lipsync_unavailable() -> tuple[Signal, Signal, Signal]:
    return (
        unavailable(
            "video.blink_rate", "Blink-Rate Analysis", "forensic",
            "requires a facial-landmark model not bundled in this local-first build",
        ),
        unavailable(
            "video.lip_sync", "Lip-Sync Mismatch Detection", "forensic",
            "requires a facial-landmark + audio-alignment model not bundled in this local-first build",
        ),
        unavailable(
            "video.audio_video_alignment", "Audio-Video Alignment", "forensic",
            "requires the same landmark/alignment modeling as lip-sync detection, not bundled here",
        ),
    )
