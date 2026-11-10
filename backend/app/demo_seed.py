"""Seeds a handful of demo reports from the committed sample files on first
run, purely so the History page isn't empty the first time the app opens."""
from __future__ import annotations

import datetime
import uuid
from pathlib import Path

from . import config, db, pipeline

SAMPLES_DIR = (Path(__file__).resolve().parent.parent / "samples").resolve()

DEMO_FILES = [
    ("genuine_synthetic_photo.jpg", "image", ["demo", "genuine"]),
    ("edited_copy_move_synthetic_photo.jpg", "image", ["demo", "edited"]),
    ("genuine_human_text.txt", "text", ["demo", "genuine"]),
    ("labeled_ai_style_text.txt", "text", ["demo", "ai-style"]),
    ("labeled_scam_text.txt", "text", ["demo", "scam-example"]),
    ("genuine_synthetic_voice.wav", "audio", ["demo", "genuine"]),
]


def seed_demo_if_empty() -> None:
    with db.connect() as conn:
        existing = db.list_reports(conn, limit=1)
        if existing:
            return
        settings = db.get_settings(conn)

        for filename, kind, tags in DEMO_FILES:
            src = SAMPLES_DIR / filename
            if not src.exists():
                continue
            report_id = uuid.uuid4().hex
            try:
                if kind == "image":
                    report = pipeline.analyze_image(src, settings, report_id)
                elif kind == "audio":
                    report = pipeline.analyze_audio(src, settings, report_id)
                elif kind == "text":
                    report = pipeline.analyze_text(src, settings, report_id)
                else:
                    continue
            except Exception:
                continue

            combination = report["combination"]
            db.save_report(
                conn,
                report_id=report_id,
                created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                media_type=kind,
                original_name=filename,
                sha256=pipeline.sha256_of(src),
                size_bytes=src.stat().st_size,
                verdict=combination["verdict"],
                confidence_band=combination["confidence_band"],
                report=report,
                evidence_dir=str(config.EVIDENCE_DIR / report_id),
                tags=tags,
            )
