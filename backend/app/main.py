from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, db, pipeline
from .export import to_json_bytes, to_pdf_bytes
from .json_safe import sanitize as json_sanitize
from .security import FileValidationError, guard_image_bomb, new_storage_path, sniff_and_validate

app = FastAPI(title="Deepfake & AI-Content Detector", docs_url="/api/docs")

FRONTEND_DIR = (Path(__file__).resolve().parent.parent.parent / "frontend").resolve()


def get_db():
    return db.connect()


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@app.get("/api/health")
def health():
    return {"status": "ok", "local_only": True}


@app.get("/api/settings")
def get_settings():
    with get_db() as conn:
        return db.get_settings(conn)


@app.post("/api/settings")
def update_settings(payload: dict):
    allowed = set(config.DEFAULT_SETTINGS.keys())
    with get_db() as conn:
        for k, v in payload.items():
            if k not in allowed:
                continue
            db.set_setting(conn, k, str(v).lower() if isinstance(v, bool) else str(v))
        return db.get_settings(conn)


def _save_upload(data: bytes, filename: str) -> tuple[Path, str]:
    try:
        sniff = sniff_and_validate(data, filename)
    except FileValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    storage_path, display_name = new_storage_path(filename, config.UPLOADS_DIR)
    storage_path.write_bytes(data)
    return storage_path, display_name, sniff.kind


def _check_media_limits(path: Path, kind: str):
    if kind == "image":
        try:
            guard_image_bomb(path)
        except FileValidationError as e:
            path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(e))
    elif kind == "audio":
        from .forensics.audio_forensics import basic_audio_properties
        try:
            props = basic_audio_properties(path)
        except Exception as e:
            path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Could not decode audio: {e}")
        if props["duration_s"] > config.MAX_AUDIO_SECONDS:
            path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Audio exceeds the configured duration limit.")
    elif kind == "video":
        from .forensics.video_forensics import probe_video
        try:
            info = probe_video(path)
        except Exception as e:
            path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Could not decode video: {e}")
        if info["duration_s"] > config.MAX_VIDEO_SECONDS:
            path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Video exceeds the configured duration limit.")
    elif kind == "text":
        if len(path.read_text(encoding="utf-8", errors="replace")) > config.MAX_TEXT_CHARS:
            path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Text exceeds the configured character limit.")


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    reference: Optional[UploadFile] = File(None),
    tags: str = Form(""),
):
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File too large.")

    storage_path, display_name, kind = _save_upload(data, file.filename or "upload")
    _check_media_limits(storage_path, kind)

    report_id = uuid.uuid4().hex

    reference_path = None
    if reference is not None and kind == "audio":
        ref_data = await reference.read()
        reference_path, _ref_display, ref_kind = _save_upload(ref_data, reference.filename or "reference")
        if ref_kind != "audio":
            reference_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Reference file must be audio.")

    with get_db() as conn:
        settings = db.get_settings(conn)

    try:
        if kind == "image":
            report = pipeline.analyze_image(storage_path, settings, report_id)
        elif kind == "audio":
            report = pipeline.analyze_audio(storage_path, settings, report_id, reference_path)
        elif kind == "video":
            report = pipeline.analyze_video(storage_path, settings, report_id)
        elif kind == "text":
            report = pipeline.analyze_text(storage_path, settings, report_id)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported kind: {kind}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    sha256 = pipeline.sha256_of(storage_path)
    size_bytes = storage_path.stat().st_size
    combination = report["combination"]
    created_at = _now_iso()

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    delete_after = settings.get("delete_uploads_after_analysis") == "true"
    if delete_after:
        storage_path.unlink(missing_ok=True)
        if reference_path:
            reference_path.unlink(missing_ok=True)

    record = {
        "id": report_id,
        "created_at": created_at,
        "media_type": kind,
        "original_name": display_name,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "verdict": combination["verdict"],
        "confidence_band": combination["confidence_band"],
        "report": report,
        "tags": tag_list,
    }

    with get_db() as conn:
        db.save_report(
            conn, report_id=report_id, created_at=created_at, media_type=kind,
            original_name=display_name, sha256=sha256, size_bytes=size_bytes,
            verdict=combination["verdict"], confidence_band=combination["confidence_band"],
            report=report, evidence_dir=str(config.EVIDENCE_DIR / report_id), tags=tag_list,
        )

    return json_sanitize(record)


@app.get("/api/reports")
def list_reports(q: Optional[str] = None, tag: Optional[str] = None, media_type: Optional[str] = None,
                  limit: int = 100, offset: int = 0):
    with get_db() as conn:
        rows = db.list_reports(conn, query=q, tag=tag, media_type=media_type, limit=limit, offset=offset)
        return rows


@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    with get_db() as conn:
        row = db.get_report(conn, report_id)
        if not row:
            raise HTTPException(status_code=404, detail="Report not found")
        return row


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: str):
    with get_db() as conn:
        ok = db.delete_report(conn, report_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Report not found")
    import shutil
    evidence_dir = config.EVIDENCE_DIR / report_id
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir, ignore_errors=True)
    return {"deleted": True}


@app.get("/api/reports/{report_id}/export.json")
def export_json(report_id: str):
    with get_db() as conn:
        row = db.get_report(conn, report_id)
        if not row:
            raise HTTPException(status_code=404, detail="Report not found")
    data = to_json_bytes(row)
    return Response(content=data, media_type="application/json",
                     headers={"Content-Disposition": f'attachment; filename="report-{report_id}.json"'})


@app.get("/api/reports/{report_id}/export.pdf")
def export_pdf(report_id: str):
    with get_db() as conn:
        row = db.get_report(conn, report_id)
        if not row:
            raise HTTPException(status_code=404, detail="Report not found")
    data = to_pdf_bytes(row)
    return Response(content=data, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="report-{report_id}.pdf"'})


_SAFE_COMPONENT = set("abcdef0123456789")


@app.get("/api/evidence/{report_id}/{filename}")
def get_evidence(report_id: str, filename: str):
    if not report_id or any(c not in _SAFE_COMPONENT for c in report_id):
        raise HTTPException(status_code=400, detail="Invalid report id")
    safe_name = Path(filename).name  # strips any path components
    if safe_name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = (config.EVIDENCE_DIR / report_id / safe_name).resolve()
    if config.EVIDENCE_DIR.resolve() not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Evidence file not found")
    return FileResponse(path)


@app.on_event("startup")
def on_startup():
    from .demo_seed import seed_demo_if_empty
    seed_demo_if_empty()


# Serve the frontend last so /api/* routes above take priority.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT)
