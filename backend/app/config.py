"""Central configuration. Everything defaults to local-only, no network calls."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
EVIDENCE_DIR = DATA_DIR / "evidence"
DB_PATH = DATA_DIR / "app.db"

for d in (DATA_DIR, UPLOADS_DIR, EVIDENCE_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Hard limits to defend against decompression bombs / resource exhaustion.
MAX_UPLOAD_BYTES = int(os.environ.get("DAICD_MAX_UPLOAD_BYTES", 300 * 1024 * 1024))  # 300 MB
MAX_IMAGE_PIXELS = int(os.environ.get("DAICD_MAX_IMAGE_PIXELS", 60_000_000))  # ~60MP decoded
MAX_AUDIO_SECONDS = int(os.environ.get("DAICD_MAX_AUDIO_SECONDS", 60 * 20))  # 20 min
MAX_VIDEO_SECONDS = int(os.environ.get("DAICD_MAX_VIDEO_SECONDS", 60 * 20))  # 20 min
MAX_TEXT_CHARS = int(os.environ.get("DAICD_MAX_TEXT_CHARS", 300_000))
MAX_VIDEO_SAMPLED_FRAMES = int(os.environ.get("DAICD_MAX_VIDEO_FRAMES", 40))

HOST = os.environ.get("DAICD_HOST", "127.0.0.1")
PORT = int(os.environ.get("DAICD_PORT", 8008))

# App-wide settings persisted in the DB `settings` table; these are just defaults
# used the very first time the app runs.
DEFAULT_SETTINGS = {
    "fully_local_mode": "true",     # if true, never suggest/allow any network lookups
    "use_optional_ml_models": "false",  # optional HF/torch-based detectors (heavy, off by default)
    "delete_uploads_after_analysis": "false",
    "theme": "dark",
}
