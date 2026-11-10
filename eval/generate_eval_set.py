"""
Generates a small, entirely self-made and synthetic labeled evaluation set.

IMPORTANT HONESTY NOTE: this is NOT FaceForensics++, DFDC, Celeb-DF,
ASVspoof, or any real AI-image/AI-text dataset. It is a small set of
programmatically generated stand-ins used to exercise the evaluation
pipeline end-to-end and produce real (if modest and not generalizable)
numbers. See eval/README.md for how to point this harness at real datasets
instead, which is required for any claim of real-world performance.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw

EVAL_DATA_DIR = Path(__file__).resolve().parent / "data"


def _base_image(w, h, seed) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 1, w)
    y = np.linspace(0, 1, h)
    xx, yy = np.meshgrid(x, y)
    phase = rng.uniform(0, 2 * np.pi)
    base = 80 + 120 * xx + 55 * np.sin(4 * yy * np.pi + phase) + rng.normal(0, 6, size=(h, w))
    arr = np.stack([
        np.clip(base + rng.uniform(-10, 25), 0, 255),
        np.clip(base, 0, 255),
        np.clip(base - rng.uniform(5, 20), 0, 255),
    ], axis=-1).astype(np.uint8)
    im = Image.fromarray(arr, "RGB")
    draw = ImageDraw.Draw(im)
    cx, cy = rng.uniform(0.2, 0.6), rng.uniform(0.2, 0.6)
    draw.ellipse((w * cx, h * cy, w * (cx + 0.2), h * (cy + 0.22)), fill=tuple(rng.integers(100, 220, 3).tolist()))
    draw.rectangle((w * 0.1, h * 0.72, w * 0.38, h * 0.9), fill=tuple(rng.integers(20, 90, 3).tolist()))
    final = np.array(im).astype(np.float32) + rng.normal(0, 4.0, size=(h, w, 3))
    return np.clip(final, 0, 255).astype(np.uint8)


def generate_images(n_each: int = 15) -> list[dict]:
    out_dir = EVAL_DATA_DIR / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []

    for i in range(n_each):
        arr = _base_image(640, 480, seed=1000 + i)
        quality = int(np.random.default_rng(i).uniform(78, 95))
        path = out_dir / f"real_{i:02d}.jpg"
        Image.fromarray(arr).save(path, "JPEG", quality=quality)
        records.append({"path": str(path), "label": "real"})

    for i in range(n_each):
        rng = np.random.default_rng(2000 + i)
        arr = _base_image(640, 480, seed=1000 + (i % n_each))  # same base distribution as 'real' set
        h, w = arr.shape[:2]
        sy0, sx0 = int(h * rng.uniform(0.2, 0.3)), int(w * rng.uniform(0.2, 0.3))
        sy1, sx1 = sy0 + int(h * 0.3), sx0 + int(w * 0.3)
        patch = arr[sy0:sy1, sx0:sx1].copy()
        ph, pw = patch.shape[:2]
        dy0 = int(h * rng.uniform(0.05, 0.15))
        dx0 = int(w * rng.uniform(0.55, 0.65))
        arr2 = arr.copy()
        arr2[dy0:dy0 + ph, dx0:dx0 + pw] = patch
        quality = int(rng.uniform(85, 95))
        path = out_dir / f"fake_{i:02d}.jpg"
        Image.fromarray(arr2).save(path, "JPEG", quality=quality)
        records.append({"path": str(path), "label": "fake"})

    return records


def generate_audio(n_each: int = 10) -> list[dict]:
    out_dir = EVAL_DATA_DIR / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    sr = 16000
    duration = 4.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    for i in range(n_each):
        rng = np.random.default_rng(3000 + i)
        f0 = rng.uniform(110, 220)
        natural_jitter = 1 + 0.02 * np.sin(2 * np.pi * rng.uniform(1.5, 3.0) * t) + rng.normal(0, 0.01, size=t.shape).cumsum() * 0.0005
        sig = np.zeros_like(t)
        for h_, amp in [(1, 1.0), (2, 0.5), (3, 0.22), (4, 0.1)]:
            sig += amp * np.sin(2 * np.pi * f0 * h_ * natural_jitter * t)
        envelope = 0.5 * (1 + np.sin(2 * np.pi * rng.uniform(1.8, 2.6) * t)) ** 2
        sig = sig * envelope
        sig = sig / (np.max(np.abs(sig)) + 1e-9) * 0.6
        sig = sig + rng.normal(0, 0.008, size=sig.shape)  # room noise
        path = out_dir / f"bonafide_{i:02d}.wav"
        sf.write(path, sig.astype(np.float32), sr)
        records.append({"path": str(path), "label": "bonafide"})

    for i in range(n_each):
        rng = np.random.default_rng(4000 + i)
        f0 = rng.uniform(110, 220)
        sig = np.zeros_like(t)
        for h_, amp in [(1, 1.0), (2, 0.5), (3, 0.22), (4, 0.1)]:
            sig += amp * np.sin(2 * np.pi * f0 * h_ * t)  # perfectly regular, no jitter
        envelope = 0.5 * (1 + np.sin(2 * np.pi * 2.2 * t)) ** 2
        sig = sig * envelope
        sig = sig / (np.max(np.abs(sig)) + 1e-9) * 0.6
        sig = sig + rng.normal(0, 0.0003, size=sig.shape)  # near-zero noise floor
        path = out_dir / f"spoof_proxy_{i:02d}.wav"
        sf.write(path, sig.astype(np.float32), sr)
        records.append({"path": str(path), "label": "spoof"})

    return records


HUMAN_TEXTS = [
    "Honestly I wasn't expecting the meeting to run that long, but we got through the backlog "
    "at least. Going to grab food before the next one starts, I'm starving.",
    "my sister's flight got delayed again lol. third time this month. she's just gonna drive next "
    "time i think, might actually be faster at this point",
    "The quarterly results show a modest improvement over the previous period, though supply "
    "chain disruptions continued to affect delivery timelines in several regions.",
    "I am writing to inform you that the shipment will be delayed by approximately two weeks due "
    "to custom clearance issues at the port. We apologize for any inconvenience this may cause.",
    "can u pick up milk on the way home? also we out of the good coffee again somehow",
    "In accordance with section 4.2 of the agreement, either party may terminate this contract "
    "upon thirty days written notice to the other party.",
    "Yesterday was rough, the car wouldn't start, then I missed the bus, then it started raining "
    "right as I got to the stop. Today has to be better right?",
    "This is to confirm that the applicant has successfully completed all required coursework and "
    "is eligible for graduation in the upcoming term, pending final review of transcripts.",
    "ok so basically what happened is the server crashed around 2am and nobody noticed until "
    "customers started emailing, we're doing a postmortem tomorrow",
    "Please find attached the revised proposal incorporating the feedback from our last "
    "discussion. Let me know if further adjustments are needed before the client review.",
    # Deliberately simple/non-native-English-style phrasing, included because
    # this exact style is where real AI-text detectors are documented to
    # produce unfair false positives.
    "I am very happy to inform that project is completed on time. We have tested all function and "
    "no error found. Please check and give feedback.",
    "Thank you for your email. I will send the document tomorrow because today I am busy with "
    "other work. Sorry for the delay, I hope this is okay for you.",
    "My opinion is that this plan is good but need more time. We should discuss again next week "
    "when all team member is available for meeting.",
]

AI_LIKE_TEMPLATES = [
    "In conclusion, it is important to note that this topic offers a variety of benefits and "
    "considerations that are worth exploring in further detail. ",
    "Overall, there are several key factors to consider when evaluating this subject, and each "
    "one plays an important role in the broader context. ",
    "To summarize, this approach provides numerous advantages while also presenting certain "
    "challenges that must be carefully addressed moving forward. ",
]


def generate_text(n_each: int = 13) -> list[dict]:
    out_dir = EVAL_DATA_DIR / "text"
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for i, txt in enumerate(HUMAN_TEXTS[:n_each]):
        path = out_dir / f"human_{i:02d}.txt"
        path.write_text(txt, encoding="utf-8")
        records.append({"path": str(path), "label": "human"})
    rng = np.random.default_rng(42)
    for i in range(n_each):
        template = AI_LIKE_TEMPLATES[i % len(AI_LIKE_TEMPLATES)]
        reps = int(rng.uniform(15, 30))
        path = out_dir / f"ai_like_{i:02d}.txt"
        path.write_text(template * reps, encoding="utf-8")
        records.append({"path": str(path), "label": "ai_like"})
    return records


def generate_all() -> dict:
    manifest = {
        "images": generate_images(),
        "audio": generate_audio(),
        "text": generate_text(),
    }
    EVAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DATA_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    m = generate_all()
    for k, v in m.items():
        print(f"{k}: {len(v)} files -> {EVAL_DATA_DIR / k}")
