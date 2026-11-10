"""
EXIF / XMP / container metadata extraction and consistency checks.

Mandatory honesty rule: missing metadata is the normal case for screenshots,
messaging-app re-encodes, and social media downloads. We only flag genuine
INTERNAL inconsistencies (e.g. modify time before create time, software tag
naming an AI generator, mismatched dimensions) -- never mere absence.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import exifread
from PIL import Image

from ..signals import Signal

AI_TOOL_HINTS = re.compile(
    r"midjourney|dall-?e|stable ?diffusion|dreamstudio|firefly|runway|sora|flux\.?1|"
    r"leonardo\.?ai|ideogram|playground ?ai|niji|comfyui|automatic1111|invokeai|"
    r"ai-?generated|generative",
    re.IGNORECASE,
)
EDIT_TOOL_HINTS = re.compile(
    r"photoshop|lightroom|gimp|affinity|snapseed|facetune|picsart|canva|capcut",
    re.IGNORECASE,
)

XMP_RE = re.compile(rb"<x:xmpmeta.*?</x:xmpmeta>", re.DOTALL)


def _parse_exif_datetime(value: str) -> datetime | None:
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def extract_image_metadata(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"exif": {}, "xmp_present": False, "gps": None, "software": None}

    with open(path, "rb") as f:
        raw = f.read()
        f.seek(0)
        tags = exifread.process_file(f, details=False)

    for tag, value in tags.items():
        if tag in ("JPEGThumbnail", "TIFFThumbnail"):
            continue
        info["exif"][tag] = str(value)

    if XMP_RE.search(raw):
        info["xmp_present"] = True

    software = info["exif"].get("Image Software")
    if software:
        info["software"] = software

    gps_lat = info["exif"].get("GPS GPSLatitude")
    gps_lon = info["exif"].get("GPS GPSLongitude")
    if gps_lat and gps_lon:
        info["gps"] = {"lat_raw": gps_lat, "lon_raw": gps_lon}

    try:
        with Image.open(path) as im:
            info["pil_format"] = im.format
            info["size"] = im.size
            info["mode"] = im.mode
    except Exception:
        pass

    return info


def analyze_image_metadata(path: Path) -> tuple[Signal, dict[str, Any]]:
    meta = extract_image_metadata(path)
    exif = meta["exif"]

    findings: list[str] = []
    direction = 0.0
    strength = 0.0

    software = meta.get("software") or ""
    if AI_TOOL_HINTS.search(software):
        findings.append(f"Software tag names a known AI image generator: '{software}'.")
        direction = max(direction, 0.75)
        strength = max(strength, 0.6)
    elif EDIT_TOOL_HINTS.search(software):
        findings.append(f"Software tag names a conventional editing tool: '{software}'. "
                         "Editing alone is not evidence of deception.")
        direction = max(direction, 0.1)
        strength = max(strength, 0.25)

    create_str = exif.get("EXIF DateTimeOriginal") or exif.get("Image DateTime")
    modify_str = exif.get("EXIF DateTimeDigitized") or exif.get("Image DateTime")
    create_dt = _parse_exif_datetime(create_str) if create_str else None
    modify_dt = _parse_exif_datetime(modify_str) if modify_str else None
    if create_dt and modify_dt and modify_dt < create_dt:
        findings.append(
            f"Modification timestamp ({modify_dt}) is earlier than the original capture "
            f"timestamp ({create_dt}) -- internally inconsistent metadata."
        )
        direction = max(direction, 0.5)
        strength = max(strength, 0.4)

    has_any_exif = len(exif) > 0
    if not has_any_exif:
        findings.append(
            "No EXIF metadata found at all. This is common and expected for screenshots, "
            "messaging-app re-uploads, and many social media downloads -- it is NOT evidence "
            "of manipulation or AI generation."
        )
    else:
        findings.append(f"EXIF metadata present ({len(exif)} tag(s)).")
        if meta.get("gps"):
            findings.append("GPS location data present in EXIF.")
        if meta.get("xmp_present"):
            findings.append("XMP metadata block present.")

    summary = " ".join(findings)
    limits = (
        "EXIF/XMP metadata is trivially stripped, edited, or fabricated by common tools "
        "(including the device's own gallery app) -- it is corroborating evidence at best, "
        "never conclusive on its own. Messaging apps routinely strip all metadata on send, "
        "so absence here says more about distribution method than authenticity."
    )

    signal = Signal(
        key="provenance.metadata",
        label="File Metadata (EXIF/XMP)",
        category="provenance",
        direction=direction,
        strength=max(strength, 0.15 if has_any_exif else 0.1),
        summary=summary,
        limits=limits,
        details={"exif_tag_count": len(exif), "has_gps": bool(meta.get("gps")), "software": software},
    )
    return signal, meta


def extract_audio_metadata(path: Path) -> dict[str, Any]:
    import mutagen
    info: dict[str, Any] = {"tags": {}, "encoder": None}
    try:
        f = mutagen.File(path)
        if f is not None:
            if getattr(f, "tags", None):
                for k, v in dict(f.tags).items():
                    info["tags"][str(k)] = str(v)
            if hasattr(f, "info"):
                info["bitrate"] = getattr(f.info, "bitrate", None)
                info["sample_rate"] = getattr(f.info, "sample_rate", None)
                info["channels"] = getattr(f.info, "channels", None)
                info["length_s"] = getattr(f.info, "length", None)
            encoder_keys = [k for k in info["tags"] if "encoder" in k.lower() or "tool" in k.lower()]
            if encoder_keys:
                info["encoder"] = info["tags"][encoder_keys[0]]
    except Exception as e:
        info["error"] = str(e)
    return info


def analyze_audio_metadata(path: Path) -> Signal:
    meta = extract_audio_metadata(path)
    tags = meta.get("tags", {})
    findings = []
    direction = 0.0
    strength = 0.1 if tags else 0.05

    encoder = (meta.get("encoder") or "")
    if AI_TOOL_HINTS.search(encoder) or any(AI_TOOL_HINTS.search(str(v)) for v in tags.values()):
        findings.append(f"Metadata references a known AI audio tool: '{encoder}'.")
        direction = 0.7
        strength = 0.55
    elif tags:
        findings.append(f"{len(tags)} metadata tag(s) present (e.g. encoder/title fields).")
    else:
        findings.append(
            "No container metadata tags found. Very common for voice notes and recompressed "
            "clips (e.g. WhatsApp opus/ogg) -- not evidence of manipulation."
        )

    return Signal(
        key="provenance.metadata",
        label="Audio Container Metadata",
        category="provenance",
        direction=direction,
        strength=strength,
        summary=" ".join(findings),
        limits="Container tags are easily stripped by messaging apps and re-encoders, and are "
               "trivial to fabricate. Absence is expected, not suspicious.",
        details={"tag_count": len(tags)},
    )


def extract_video_metadata(path: Path) -> dict[str, Any]:
    import av
    info: dict[str, Any] = {"streams": [], "metadata": {}}
    try:
        with av.open(str(path)) as container:
            info["metadata"] = dict(container.metadata)
            for stream in container.streams:
                s = {"type": stream.type, "codec": getattr(stream.codec_context, "name", None)}
                if stream.type == "video":
                    s["width"] = stream.width
                    s["height"] = stream.height
                    s["avg_rate"] = float(stream.average_rate) if stream.average_rate else None
                elif stream.type == "audio":
                    s["sample_rate"] = stream.sample_rate
                    s["channels"] = stream.channels
                info["streams"].append(s)
            info["duration_s"] = float(container.duration / 1_000_000) if container.duration else None
    except Exception as e:
        info["error"] = str(e)
    return info


def analyze_video_metadata(path: Path) -> Signal:
    meta = extract_video_metadata(path)
    container_meta = meta.get("metadata", {})
    findings = []
    direction = 0.0
    strength = 0.1

    encoder = container_meta.get("encoder", "") or container_meta.get("software", "")
    if AI_TOOL_HINTS.search(str(encoder)):
        findings.append(f"Container metadata references a known AI video tool: '{encoder}'.")
        direction = 0.7
        strength = 0.55
    elif container_meta:
        findings.append(f"Container metadata present ({len(container_meta)} field(s)): "
                         f"{', '.join(list(container_meta.keys())[:5])}.")
    else:
        findings.append("No container-level metadata tags found. Common after re-encoding, "
                         "downloading, or messaging-app transit -- not inherently suspicious.")

    video_streams = [s for s in meta.get("streams", []) if s.get("type") == "video"]
    if len(video_streams) > 1:
        findings.append(f"Unusual: {len(video_streams)} separate video streams in one container.")
        direction = max(direction, 0.3)
        strength = max(strength, 0.3)

    return Signal(
        key="provenance.metadata",
        label="Video Container Metadata",
        category="provenance",
        direction=direction,
        strength=strength,
        summary=" ".join(findings),
        limits="Container metadata is easily stripped or rewritten by re-encoding (including by "
               "messaging apps and social platforms) -- absence or generic tags are expected, "
               "not suspicious.",
        details={"streams": meta.get("streams", []), "duration_s": meta.get("duration_s")},
    )


def analyze_text_file_metadata(path: Path) -> Signal:
    """Text files carry essentially no forensically useful embedded metadata."""
    return Signal(
        key="provenance.metadata",
        label="File Metadata",
        category="provenance",
        direction=0.0,
        strength=0.0,
        summary="Plain text files carry no embedded provenance metadata to inspect.",
        limits="Not applicable to this file type.",
        applicable=False,
    )
