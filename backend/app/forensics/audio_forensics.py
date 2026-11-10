"""
Audio forensics: spectrogram generation, breathing/room-noise and codec-trace
heuristics, a basic (non-ML) spoofing heuristic, and speaker comparison via
MFCC embeddings. All of this runs fully offline with librosa/numpy/scipy.

Speaker comparison is explicitly scoped to "compare this clip against a
reference clip the user supplies" -- never to identify who an unknown voice
belongs to. See README "Responsible use."
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import librosa
import numpy as np
from PIL import Image

from ..signals import Signal

LIMITS_SPECTROGRAM = (
    "The spectrogram is a visualization, not a verdict -- read it alongside the other audio "
    "signals below."
)
LIMITS_BREATHING = (
    "This checks for the near-total absence of breath sounds and room/background noise floor, "
    "which is common (not universal) in TTS/voice-cloning output and in heavily denoised real "
    "recordings alike. A skilled clone or a lightly-noised real recording can evade this easily."
)
LIMITS_SPOOF_HEURISTIC = (
    "This is a basic spectral heuristic (flatness / high-frequency roll-off / harmonic "
    "regularity), NOT a trained ASVspoof-style anti-spoofing model. It is weaker than a properly "
    "trained classifier and should be treated as a rough indicator only. Enable the optional ML "
    "extras for a trained-model signal."
)
LIMITS_SPEAKER_COMPARE = (
    "Voice similarity uses generic MFCC-based acoustic embeddings, not a state-of-the-art speaker "
    "verification model. HIGH similarity to your reference clip does NOT prove authenticity -- "
    "voice cloning tools are specifically designed to maximize this kind of similarity. LOW "
    "similarity can also simply mean a bad recording, different phone/mic, or different mood/health. "
    "Never use this to identify a stranger's voice -- only to compare against a reference you "
    "already have consent to use."
)


def load_audio_mono(path: Path, sr: int | None = None) -> tuple[np.ndarray, int]:
    y, sr_out = librosa.load(str(path), sr=sr, mono=True)
    return y, sr_out


def basic_audio_properties(path: Path) -> dict[str, Any]:
    y, sr = load_audio_mono(path)
    duration = float(len(y) / sr) if sr else 0.0
    rms = float(np.sqrt(np.mean(y ** 2))) if len(y) else 0.0
    return {"duration_s": duration, "sample_rate": sr, "samples": len(y), "rms": rms}


def make_spectrogram_png(path: Path) -> bytes:
    y, sr = load_audio_mono(path)
    if len(y) == 0:
        y = np.zeros(sr or 16000)
    S = librosa.stft(y, n_fft=1024, hop_length=256)
    S_db = librosa.amplitude_to_db(np.abs(S), ref=np.max)
    norm = (S_db - S_db.min()) / (S_db.max() - S_db.min() + 1e-9)
    norm = np.flipud(norm)
    img_u8 = (norm * 255).astype(np.uint8)
    import cv2
    colored = cv2.applyColorMap(img_u8, cv2.COLORMAP_MAGMA)
    colored = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
    im = Image.fromarray(colored).resize((900, 300))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def breathing_and_room_noise(path: Path) -> Signal:
    y, sr = load_audio_mono(path)
    if len(y) < sr * 0.5:
        return Signal(
            key="audio.breathing_room_noise", label="Breathing / Room Noise Check", category="forensic",
            direction=0.0, strength=0.0, summary="Clip too short to assess.",
            limits=LIMITS_BREATHING, applicable=False,
        )

    frame_len = int(sr * 0.03)
    hop = int(sr * 0.015)
    energy = np.array([
        np.sqrt(np.mean(y[i:i + frame_len] ** 2)) for i in range(0, len(y) - frame_len, hop)
    ])
    noise_floor = float(np.percentile(energy, 10))
    peak = float(np.percentile(energy, 95)) + 1e-9
    noise_floor_ratio = noise_floor / peak

    silence_threshold = noise_floor + 0.15 * (peak - noise_floor)
    is_quiet = energy < silence_threshold
    quiet_runs = []
    run = 0
    for q in is_quiet:
        if q:
            run += 1
        else:
            if run > 0:
                quiet_runs.append(run)
            run = 0
    if run > 0:
        quiet_runs.append(run)
    long_silences = [r for r in quiet_runs if r * hop / sr > 0.25]

    direction = 0.0
    strength = 0.25
    notes = []
    if noise_floor_ratio < 0.01 and len(long_silences) > 0:
        notes.append(
            f"Noise floor is extremely low relative to peak level (ratio {noise_floor_ratio:.4f}) "
            f"with {len(long_silences)} near-silent gap(s) that contain almost no breath/room noise "
            "at all -- a pattern more common in synthetic/TTS audio than real-room recordings."
        )
        direction = 0.45
        strength = 0.4
    elif noise_floor_ratio < 0.03:
        notes.append(
            f"Noise floor is quite low relative to peak level (ratio {noise_floor_ratio:.4f}), "
            "which can indicate synthetic audio OR simply a good microphone/quiet room/denoising."
        )
        direction = 0.15
        strength = 0.3
    else:
        notes.append(
            f"Normal room-noise floor detected (ratio {noise_floor_ratio:.4f}), consistent with a "
            "real-world recording environment."
        )
        direction = -0.1
        strength = 0.3

    return Signal(
        key="audio.breathing_room_noise", label="Breathing / Room Noise Check", category="forensic",
        direction=direction, strength=strength, summary=" ".join(notes), limits=LIMITS_BREATHING,
        details={"noise_floor_ratio": noise_floor_ratio, "long_silences": len(long_silences)},
    )


def codec_trace_heuristic(path: Path, sample_rate: int) -> Signal:
    y, sr = load_audio_mono(path, sr=sample_rate)
    S = np.abs(librosa.stft(y, n_fft=2048))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    high_band = S[freqs > (sr / 2) * 0.9, :]
    high_energy_fraction = float(high_band.sum() / (S.sum() + 1e-9))

    notes = []
    direction = 0.0
    if sr <= 8000:
        notes.append(
            f"Sample rate is {sr} Hz, typical of a traditional phone/VoIP narrowband codec. This "
            "is an EXPECTED property of real phone calls, not a red flag by itself."
        )
    elif high_energy_fraction < 0.002:
        notes.append(
            f"Very little energy near the top of the available frequency band ({high_energy_fraction:.4f} "
            "fraction), suggesting the audio passed through a bandwidth-limiting codec or was "
            "upsampled from a lower original rate at some point (common for voice notes forwarded "
            "multiple times, OR for some TTS output)."
        )
        direction = 0.1
    else:
        notes.append(f"Frequency content extends normally toward the top of the available band "
                      f"({high_energy_fraction:.4f} fraction).")

    return Signal(
        key="audio.codec_traces", label="Codec / Bandwidth Trace Check", category="forensic",
        direction=direction, strength=0.25, summary=" ".join(notes),
        limits="Bandwidth limiting has many innocent causes (phone codecs, old recording "
               "equipment, repeated re-encoding) and is only weak circumstantial evidence.",
        details={"sample_rate": sr, "high_energy_fraction": high_energy_fraction},
    )


def spoofing_heuristic(path: Path) -> Signal:
    y, sr = load_audio_mono(path)
    if len(y) < sr * 1.0:
        return Signal(
            key="audio.spoof_heuristic", label="Spoofing Heuristic (non-ML)", category="forensic",
            direction=0.0, strength=0.0, summary="Clip too short to assess.",
            limits=LIMITS_SPOOF_HEURISTIC, applicable=False,
        )

    flatness = float(np.mean(librosa.feature.spectral_flatness(y=y)))
    S = np.abs(librosa.stft(y))
    centroid = librosa.feature.spectral_centroid(S=S, sr=sr)
    centroid_cv = float(np.std(centroid) / (np.mean(centroid) + 1e-9))

    f0, voiced_flag, _ = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"), sr=sr,
    )
    voiced_f0 = f0[voiced_flag] if voiced_flag is not None and f0 is not None else np.array([])
    pitch_jitter = float(np.std(np.diff(voiced_f0)) / (np.mean(voiced_f0) + 1e-9)) if len(voiced_f0) > 5 else None

    notes = [f"Spectral flatness {flatness:.3f}, spectral-centroid variability {centroid_cv:.3f}."]
    direction = 0.0
    strength = 0.3
    if flatness < 0.05 and centroid_cv < 0.25:
        notes.append(
            "Unusually smooth/regular spectral characteristics across the clip -- can be "
            "consistent with synthetic speech, but also with a calm, consistent real speaker."
        )
        direction = 0.3
    if pitch_jitter is not None:
        notes.append(f"Pitch (F0) frame-to-frame jitter: {pitch_jitter:.3f}.")
        if pitch_jitter < 0.01:
            notes.append(
                "Extremely low natural pitch jitter, more regular than most real speech -- a "
                "weak indicator of synthetic generation."
            )
            direction = max(direction, 0.35)
            strength = 0.4

    return Signal(
        key="audio.spoof_heuristic", label="Spoofing Heuristic (non-ML)", category="forensic",
        direction=direction, strength=strength, summary=" ".join(notes), limits=LIMITS_SPOOF_HEURISTIC,
        details={"spectral_flatness": flatness, "centroid_cv": centroid_cv, "pitch_jitter": pitch_jitter},
    )


def _mfcc_embedding(y: np.ndarray, sr: int) -> np.ndarray:
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    delta = librosa.feature.delta(mfcc)
    feat = np.concatenate([mfcc.mean(axis=1), mfcc.std(axis=1), delta.mean(axis=1)])
    norm = np.linalg.norm(feat) + 1e-9
    return feat / norm


def speaker_comparison(clip_path: Path, reference_path: Path) -> Signal:
    y1, sr1 = load_audio_mono(clip_path, sr=16000)
    y2, sr2 = load_audio_mono(reference_path, sr=16000)
    if len(y1) < sr1 * 0.5 or len(y2) < sr2 * 0.5:
        return Signal(
            key="audio.speaker_comparison", label="Speaker Comparison vs. Reference", category="model",
            direction=0.0, strength=0.0, summary="One or both clips are too short to compare.",
            limits=LIMITS_SPEAKER_COMPARE, applicable=False,
        )

    e1 = _mfcc_embedding(y1, sr1)
    e2 = _mfcc_embedding(y2, sr2)
    cosine_sim = float(np.dot(e1, e2) / (np.linalg.norm(e1) * np.linalg.norm(e2) + 1e-9))

    summary = (
        f"Acoustic similarity to the reference clip: {cosine_sim:.2f} (range -1 to 1, higher = more "
        f"similar vocal characteristics). "
    )
    if cosine_sim > 0.85:
        summary += "This is HIGH similarity -- but see the mandatory caveat below before treating it as reassuring."
    elif cosine_sim > 0.6:
        summary += "This is MODERATE similarity."
    else:
        summary += "This is LOW similarity -- the clip's vocal characteristics differ noticeably from the reference."

    return Signal(
        key="audio.speaker_comparison", label="Speaker Comparison vs. Reference", category="model",
        direction=0.0, strength=0.0,  # explicitly excluded from the authentic/fake combination --
        # see docstring: high similarity is not evidence of authenticity, so this never pushes the verdict.
        summary=summary, limits=LIMITS_SPEAKER_COMPARE,
        details={"cosine_similarity": cosine_sim},
    )


SCAM_CALL_CHECKLIST = [
    "Urgent request for money, gift cards, crypto, or wire transfer -- especially 'right now' pressure.",
    "Caller asks you to keep it secret or not tell other family members / colleagues.",
    "Caller is using a new or unfamiliar phone number, even if the voice sounds exactly right.",
    "Caller avoids specific shared personal details only the real person would know.",
    "Caller refuses or deflects a live video call or a callback to the number you already have saved.",
    "Emotional urgency (crying, panic, 'don't ask questions') used to shut down verification.",
]

SAFE_WORD_GUIDANCE = (
    "Agree on a private safe word or phrase with family/colleagues ahead of time -- something "
    "never written online or said over a recorded line. If a call claiming to be them doesn't "
    "know it, treat the call as suspicious regardless of how the voice sounds. Rotate it "
    "periodically and never share it over the channel you're trying to protect."
)
