"""
Untrusted-input handling.

Every uploaded file is attacker-controlled data until proven otherwise. This
module enforces: size limits, content-sniffed (not extension-trusted) typing,
decompression-bomb guards, filename sanitization, and path-traversal safety.

Honesty note (see README "Security model"): this is a personal, single-user,
localhost-bound app, not a hardened multi-tenant service. Analysis code is
written to make zero outbound network calls (verified by code review, not by
an OS-level network namespace), and nothing here claims OS-level sandboxing
that isn't actually implemented.
"""
from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import filetype
from PIL import Image

from . import config

# Disable PIL's own pixel-count bomb guard default and apply our own explicit cap
Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS


class FileValidationError(ValueError):
    pass


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

# kind -> set of sniffed MIME prefixes/types we accept
ACCEPTED_KINDS = {
    "image": {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff", "image/gif"},
    "audio": {
        "audio/wav", "audio/x-wav", "audio/flac", "audio/ogg", "audio/opus",
        "audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/aac", "audio/3gpp",
    },
    "video": {
        "video/mp4", "video/quicktime", "video/webm", "video/x-matroska",
        "video/3gpp", "video/x-msvideo",
    },
    "text": {"text/plain"},
}

EXTENSION_HINTS = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"},
    "audio": {".wav", ".flac", ".ogg", ".opus", ".mp3", ".m4a", ".aac", ".3gp", ".amr"},
    "video": {".mp4", ".mov", ".webm", ".mkv", ".3gp", ".avi"},
    "text": {".txt", ".md"},
}


def sanitize_display_name(name: str) -> str:
    """Strip anything that could enable path traversal or render as HTML/JS.
    This is for DISPLAY/storage-key purposes only -- never used to build a
    filesystem path directly."""
    name = os.path.basename(name or "upload")
    name = name.replace("\x00", "")
    name = _SAFE_NAME_RE.sub("_", name)
    if not name or name in {".", ".."}:
        name = "upload"
    return name[:200]


def new_storage_path(original_name: str, directory: Path) -> tuple[Path, str]:
    """Generate a collision-proof, traversal-proof storage path.
    The original filename is NEVER used to build the path -- only a fresh
    UUID is. The sanitized original name is kept purely as metadata."""
    safe_display = sanitize_display_name(original_name)
    ext = Path(safe_display).suffix.lower()
    ext = _SAFE_NAME_RE.sub("", ext)[:10]
    token = uuid.uuid4().hex
    path = (directory / f"{token}{ext}").resolve()
    directory_resolved = directory.resolve()
    if directory_resolved not in path.parents:
        # Should be unreachable given construction above, but never trust it.
        raise FileValidationError("Resolved storage path escaped the uploads directory")
    return path, safe_display


@dataclass
class SniffResult:
    kind: str  # image | audio | video | text
    mime: str


def sniff_and_validate(data: bytes, declared_name: str) -> SniffResult:
    if not data:
        raise FileValidationError("Empty file")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise FileValidationError(
            f"File too large ({len(data)} bytes > limit {config.MAX_UPLOAD_BYTES})"
        )

    kind_hint = None
    low = declared_name.lower()
    for kind, exts in EXTENSION_HINTS.items():
        if any(low.endswith(e) for e in exts):
            kind_hint = kind
            break

    kind_detected = filetype.guess(data)
    if kind_detected is not None:
        mime = kind_detected.mime
        for kind, mimes in ACCEPTED_KINDS.items():
            if mime in mimes:
                return SniffResult(kind=kind, mime=mime)
        raise FileValidationError(f"Unsupported content type detected: {mime}")

    # filetype.guess() returns None for plain text and some containers it
    # doesn't recognize by magic bytes (e.g. plain .txt). Fall back to a
    # strict text-content check -- never trust the extension alone.
    if kind_hint == "text":
        try:
            sample = data[:65536]
            sample.decode("utf-8")
        except UnicodeDecodeError:
            raise FileValidationError("File claims to be text but is not valid UTF-8")
        if b"\x00" in sample:
            raise FileValidationError("Binary content in a text upload")
        return SniffResult(kind="text", mime="text/plain")

    raise FileValidationError("Could not verify file content type from its bytes")


def guard_image_bomb(path: Path) -> tuple[int, int]:
    """Open with PIL to get dimensions under our explicit pixel-count cap.
    Raises FileValidationError for decompression-bomb-shaped files."""
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            w, h = im.size
            if w * h > config.MAX_IMAGE_PIXELS:
                raise FileValidationError(
                    f"Image pixel count {w*h} exceeds safety cap {config.MAX_IMAGE_PIXELS}"
                )
            return w, h
    except FileValidationError:
        raise
    except Exception as e:  # PIL raises many exception types for malformed files
        raise FileValidationError(f"Image failed to decode safely: {e}") from e
