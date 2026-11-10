"""Robustness transforms: re-run the image eval set through common
real-world degradations (recompression, resizing, noise, a crude
'screenshot' simulation) and compare metrics before/after."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image


def recompress(path: Path, out_path: Path, quality: int = 45) -> Path:
    with Image.open(path) as im:
        im.convert("RGB").save(out_path, "JPEG", quality=quality)
    return out_path


def resize_down(path: Path, out_path: Path, scale: float = 0.5) -> Path:
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS).save(out_path, "JPEG", quality=90)
    return out_path


def add_noise(path: Path, out_path: Path, sigma: float = 8.0) -> Path:
    with Image.open(path) as im:
        arr = np.array(im.convert("RGB")).astype(np.float32)
        rng = np.random.default_rng(0)
        arr += rng.normal(0, sigma, size=arr.shape)
        Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(out_path, "JPEG", quality=90)
    return out_path


def simulate_screenshot(path: Path, out_path: Path) -> Path:
    """Downscale then upscale (as a screen capture / re-display would), then
    recompress -- a crude but real approximation of 'someone screenshotted
    this off their phone and sent it to you'."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        small = im.resize((max(1, w // 2), max(1, h // 2)), Image.BILINEAR)
        back = small.resize((w, h), Image.BILINEAR)
        back.save(out_path, "JPEG", quality=75)
    return out_path


TRANSFORMS = {
    "recompressed_q45": recompress,
    "resized_50pct": resize_down,
    "added_noise": add_noise,
    "screenshot_simulated": simulate_screenshot,
}
