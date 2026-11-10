"""
Pixel-level image forensics: Error Level Analysis, noise residual, double-JPEG
("JPEG ghost") detection, and ORB-based copy-move detection. Each function
returns a Signal plus an optional heatmap PNG (as raw bytes) for the UI.

All of these are classic, well-documented forensic heuristics (Farid et al.
and similar literature) re-implemented here from scratch with numpy/PIL/
OpenCV -- not copied from any dataset or proprietary tool.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from ..signals import Signal

LIMITS_ELA = (
    "Error Level Analysis highlights regions that respond differently to JPEG re-compression, "
    "which often (not always) correlates with edited/pasted regions. It produces false positives "
    "on text, logos, sharp edges, and any image saved at very high or very low quality, and is "
    "unreliable after resizing, screenshotting, or multiple re-saves."
)
LIMITS_NOISE = (
    "Noise residual analysis flags regions whose sensor-noise pattern differs from the rest of "
    "the image, which can indicate splicing -- but denoising filters, resizing, heavy compression, "
    "and even uniform smooth surfaces (sky, walls) can all mimic or hide this pattern."
)
LIMITS_GHOST = (
    "Double/'ghost' JPEG compression analysis looks for regions whose compression history differs "
    "from the rest of the image, a common splicing fingerprint -- but a single uniform re-save, "
    "screenshotting, or messaging-app recompression can produce similar effects with no splicing "
    "involved at all."
)
LIMITS_COPYMOVE = (
    "Copy-move detection looks for duplicated regions using keypoint matching, which catches "
    "naive clone-stamp edits but misses well-blended or heavily-transformed copies, and can "
    "false-positive on images with large repetitive textures (brick walls, carpets, grass)."
)
LIMITS_LIGHTING = (
    "This is a coarse global heuristic comparing brightness-gradient direction across image "
    "quadrants, not real 3D lighting/shadow geometry analysis. It can miss subtle inconsistencies "
    "and can false-positive on images with multiple real light sources (indoor scenes, flash photos)."
)


def _to_png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _heatmap_overlay(base_gray: np.ndarray, heat: np.ndarray, base_rgb: np.ndarray) -> Image.Image:
    heat_norm = heat - heat.min()
    if heat_norm.max() > 0:
        heat_norm = heat_norm / heat_norm.max()
    heat_u8 = (heat_norm * 255).astype(np.uint8)
    colored = cv2.applyColorMap(heat_u8, cv2.COLORMAP_INFERNO)
    colored = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
    overlay = (0.55 * base_rgb + 0.45 * colored).astype(np.uint8)
    return Image.fromarray(overlay)


def estimate_jpeg_quality(path: Path) -> float | None:
    try:
        with Image.open(path) as im:
            if im.format != "JPEG":
                return None
            quant = getattr(im, "quantization", None)
            if not quant:
                return None
            table = quant.get(0) or next(iter(quant.values()))
            table = np.array(table, dtype=np.float64)
            avg = float(np.mean(table))
            if avg <= 0:
                return None
            # Approximate inverse of the standard IJG scaling formula.
            if avg <= 1:
                q = 100.0
            elif avg < 50:
                q = 100.0 - avg / 2.0
            else:
                q = 5000.0 / avg
            return float(np.clip(q, 1, 100))
    except Exception:
        return None


def error_level_analysis(path: Path, quality: int = 90) -> tuple[Signal, bytes | None]:
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            original = np.array(im, dtype=np.float32)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality)
            buf.seek(0)
            with Image.open(buf) as recompressed:
                recompressed_arr = np.array(recompressed, dtype=np.float32)
    except Exception as e:
        return Signal(
            key="image.ela", label="Error Level Analysis", category="forensic",
            direction=0.0, strength=0.0, summary=f"ELA could not run: {e}",
            limits=LIMITS_ELA, applicable=False,
        ), None

    diff = np.abs(original - recompressed_arr)
    diff_gray = diff.mean(axis=2)

    h, w = diff_gray.shape
    block = 16
    block_means = []
    for y in range(0, h - block, block):
        for x in range(0, w - block, block):
            block_means.append(diff_gray[y:y + block, x:x + block].mean())
    block_means = np.array(block_means) if block_means else np.array([0.0])

    global_mean = float(diff_gray.mean())
    global_std = float(diff_gray.std())
    block_std = float(block_means.std())
    # High block-to-block variance (some regions much "hotter" than others)
    # is the actual splicing signal -- uniform ELA brightness is normal.
    heterogeneity = block_std / (block_means.mean() + 1e-6)

    strength = float(np.clip((heterogeneity - 0.5) / 2.0, 0.0, 1.0))
    direction = float(np.clip((heterogeneity - 0.8) / 1.5, -0.2, 1.0)) if heterogeneity > 0.8 else -0.1

    summary = (
        f"Mean ELA response {global_mean:.2f} (std {global_std:.2f}), block-level heterogeneity "
        f"{heterogeneity:.2f}. "
        + ("Some regions show notably higher recompression error than the rest, consistent with "
           "localized editing." if heterogeneity > 0.8 else
           "Recompression error looks fairly uniform across the image, with no strongly isolated "
           "high-error regions.")
    )

    original_u8 = original.astype(np.uint8)
    heatmap_png = None
    try:
        heatmap_img = _heatmap_overlay(diff_gray, diff_gray, original_u8)
        heatmap_png = _to_png_bytes(heatmap_img)
    except Exception:
        pass

    signal = Signal(
        key="image.ela", label="Error Level Analysis", category="forensic",
        direction=direction, strength=strength, summary=summary, limits=LIMITS_ELA,
        details={"global_mean_error": global_mean, "heterogeneity": heterogeneity},
    )
    return signal, heatmap_png


def noise_residual_analysis(path: Path) -> tuple[Signal, bytes | None]:
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            arr = np.array(im)
    except Exception as e:
        return Signal(
            key="image.noise_residual", label="Noise Residual Analysis", category="forensic",
            direction=0.0, strength=0.0, summary=f"Could not run: {e}",
            limits=LIMITS_NOISE, applicable=False,
        ), None

    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY).astype(np.float32)
    denoised = cv2.GaussianBlur(gray, (5, 5), 0)
    residual = gray - denoised
    edges = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)

    block = 24
    h, w = residual.shape
    local_vars = []
    edge_energy = []
    var_map = np.zeros_like(residual)
    for y in range(0, h - block, block):
        for x in range(0, w - block, block):
            patch = residual[y:y + block, x:x + block]
            v = float(patch.var())
            local_vars.append(v)
            edge_energy.append(float(np.abs(edges[y:y + block, x:x + block]).mean()))
            var_map[y:y + block, x:x + block] = v

    local_vars = np.array(local_vars) if local_vars else np.array([0.0])
    edge_energy = np.array(edge_energy) if edge_energy else np.array([0.0])

    # Strong edges (object boundaries, text, high-contrast lines) naturally
    # produce high-pass residual energy that has nothing to do with sensor
    # noise. Comparing noise statistics only across the flatter (low-edge)
    # blocks avoids flagging ordinary edge-heavy photos as "spliced."
    edge_threshold = float(np.percentile(edge_energy, 70)) if len(edge_energy) > 5 else np.inf
    flat_mask = edge_energy <= edge_threshold
    flat_vars = local_vars[flat_mask] if flat_mask.any() else local_vars

    median_var = float(np.median(flat_vars))
    mad = float(np.median(np.abs(flat_vars - median_var))) + 1e-6
    outlier_fraction = float(np.mean(np.abs(flat_vars - median_var) > 6 * mad))

    # Baseline calibration note: even genuinely unedited photos typically show
    # an outlier fraction in the 0.10-0.20 range here, because JPEG
    # compression's own block artifacts vary with local image complexity --
    # this is NOT pure sensor noise. Thresholds below are set above that
    # observed baseline so this signal only activates meaningfully once the
    # heterogeneity clearly exceeds ordinary compression variation.
    strength = float(np.clip((outlier_fraction - 0.15) * 4, 0.0, 0.7))
    direction = float(np.clip((outlier_fraction - 0.18) * 5, -0.15, 0.6))

    summary = (
        f"Noise variance outlier fraction across {len(flat_vars)} low-edge blocks (of {len(local_vars)} total): "
        f"{outlier_fraction:.3f}. "
        + ("A meaningful fraction of blocks have a noise pattern that stands out sharply from the "
           "rest of the image, beyond what ordinary compression variation explains -- this can "
           "indicate a spliced-in region from a different source."
           if outlier_fraction > 0.18 else
           "Noise pattern looks consistent with ordinary compression variation across the image.")
    )

    heatmap_png = None
    try:
        heatmap_img = _heatmap_overlay(gray, var_map, arr)
        heatmap_png = _to_png_bytes(heatmap_img)
    except Exception:
        pass

    signal = Signal(
        key="image.noise_residual", label="Noise Residual Analysis", category="forensic",
        direction=direction, strength=strength, summary=summary, limits=LIMITS_NOISE,
        details={"outlier_fraction": outlier_fraction, "median_block_variance": median_var},
    )
    return signal, heatmap_png


def double_compression_ghost(path: Path) -> tuple[Signal, bytes | None]:
    """Simplified 'JPEG ghost' method (Farid): recompress the whole image at a
    range of qualities and, per block, find which recompression quality
    minimizes the difference. A single uniform history gives one dominant
    quality everywhere; a spliced region often shows a different one."""
    try:
        with Image.open(path) as im:
            if im.format != "JPEG":
                return Signal(
                    key="image.double_compression", label="Double JPEG Compression ('Ghost') Detection",
                    category="forensic", direction=0.0, strength=0.0,
                    summary="Not applicable: source file is not a JPEG.",
                    limits=LIMITS_GHOST, applicable=False,
                ), None
            im = im.convert("RGB")
            arr = np.array(im, dtype=np.float32)
    except Exception as e:
        return Signal(
            key="image.double_compression", label="Double JPEG Compression ('Ghost') Detection",
            category="forensic", direction=0.0, strength=0.0, summary=f"Could not run: {e}",
            limits=LIMITS_GHOST, applicable=False,
        ), None

    qualities = list(range(35, 96, 10))
    h, w, _ = arr.shape
    block = 16
    diffs_per_q = []
    for q in qualities:
        buf = io.BytesIO()
        Image.fromarray(arr.astype(np.uint8)).save(buf, "JPEG", quality=q)
        buf.seek(0)
        with Image.open(buf) as rc:
            rc_arr = np.array(rc, dtype=np.float32)
        d = np.abs(arr - rc_arr).mean(axis=2)
        diffs_per_q.append(d)

    stack = np.stack(diffs_per_q, axis=0)  # (Q, H, W)
    best_q_map = np.zeros((h // block, w // block), dtype=np.int32)
    for by, y in enumerate(range(0, h - block, block)):
        for bx, x in enumerate(range(0, w - block, block)):
            block_scores = stack[:, y:y + block, x:x + block].mean(axis=(1, 2))
            best_q_map[by, bx] = int(np.argmin(block_scores))

    values, counts = np.unique(best_q_map, return_counts=True)
    dominant_count = counts.max() if len(counts) else 0
    total = best_q_map.size or 1
    dominant_fraction = dominant_count / total
    minority_fraction = 1 - dominant_fraction

    strength = float(np.clip((minority_fraction - 0.08) * 4, 0.0, 1.0))
    direction = float(np.clip((minority_fraction - 0.12) * 4, -0.1, 1.0))

    summary = (
        f"Across {total} blocks, {dominant_fraction*100:.0f}% share the same best-matching "
        f"recompression quality bucket. "
        + ("A notable minority of blocks have a distinctly different compression-history fit, "
           "consistent with a region that was saved/edited separately before being combined "
           "into this image." if minority_fraction > 0.12 else
           "Compression history looks fairly uniform across the image.")
    )

    heatmap_png = None
    try:
        full_map = cv2.resize(best_q_map.astype(np.float32), (w, h), interpolation=cv2.INTER_NEAREST)
        gray = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2GRAY)
        heatmap_img = _heatmap_overlay(gray, full_map, arr.astype(np.uint8))
        heatmap_png = _to_png_bytes(heatmap_img)
    except Exception:
        pass

    signal = Signal(
        key="image.double_compression", label="Double JPEG Compression ('Ghost') Detection",
        category="forensic", direction=direction, strength=strength, summary=summary,
        limits=LIMITS_GHOST, details={"dominant_fraction": dominant_fraction, "qualities_tested": qualities},
    )
    return signal, heatmap_png


def copy_move_detection(path: Path) -> tuple[Signal, bytes | None]:
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            arr = np.array(im)
    except Exception as e:
        return Signal(
            key="image.copy_move", label="Copy-Move Detection", category="forensic",
            direction=0.0, strength=0.0, summary=f"Could not run: {e}",
            limits=LIMITS_COPYMOVE, applicable=False,
        ), None

    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(nfeatures=2000)
    keypoints, descriptors = orb.detectAndCompute(gray, None)

    if descriptors is None or len(keypoints) < 20:
        return Signal(
            key="image.copy_move", label="Copy-Move Detection", category="forensic",
            direction=0.0, strength=0.15,
            summary="Too few distinctive keypoints found to reliably test for copy-move regions "
                    "(common for very smooth, low-detail, or very small images).",
            limits=LIMITS_COPYMOVE,
        ), None

    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = bf.knnMatch(descriptors, descriptors, k=3)

    min_distance_px = max(gray.shape) * 0.06
    good_pairs = []
    for m_list in matches:
        for m in m_list[1:]:  # skip self-match (distance 0 to itself)
            if m.distance > 40:
                continue
            p1 = np.array(keypoints[m.queryIdx].pt)
            p2 = np.array(keypoints[m.trainIdx].pt)
            if np.linalg.norm(p1 - p2) > min_distance_px:
                good_pairs.append((m.queryIdx, m.trainIdx, p1, p2))

    unique_pairs = {}
    for qi, ti, p1, p2 in good_pairs:
        key = tuple(sorted((qi, ti)))
        unique_pairs[key] = (p1, p2)

    # The real copy-move fingerprint is not just "some far-apart keypoints
    # match" (small texture patches do that by chance) -- it's that MANY
    # matches share nearly the same displacement vector, meaning one whole
    # region was translated and pasted elsewhere. Cluster by displacement.
    displacement_buckets: dict[tuple[int, int], list[tuple[np.ndarray, np.ndarray]]] = {}
    for p1, p2 in unique_pairs.values():
        disp = p2 - p1
        bucket = (round(disp[0] / 8) * 8, round(disp[1] / 8) * 8)
        displacement_buckets.setdefault(bucket, []).append((p1, p2))
        neg_bucket = (round(-disp[0] / 8) * 8, round(-disp[1] / 8) * 8)
        displacement_buckets.setdefault(neg_bucket, []).append((p1, p2))

    match_count = len(unique_pairs)
    largest_cluster = max((len(v) for v in displacement_buckets.values()), default=0)

    strength = float(np.clip((largest_cluster - 3) / 12, 0.0, 1.0)) if largest_cluster > 3 else 0.15
    direction = float(np.clip((largest_cluster - 5) / 10, -0.1, 1.0))

    heatmap_png = None
    if unique_pairs:
        overlay = arr.copy()
        for p1, p2 in unique_pairs.values():
            cv2.circle(overlay, tuple(p1.astype(int)), 6, (255, 40, 40), 2)
            cv2.circle(overlay, tuple(p2.astype(int)), 6, (255, 40, 40), 2)
            cv2.line(overlay, tuple(p1.astype(int)), tuple(p2.astype(int)), (255, 180, 0), 1)
        try:
            heatmap_png = _to_png_bytes(Image.fromarray(overlay))
        except Exception:
            pass

    summary = (
        f"Found {match_count} distant keypoint match(es) out of {len(keypoints)} detected; the "
        f"largest group sharing a consistent displacement (same shift applied to a whole region) "
        f"is {largest_cluster} point(s). "
        + ("A large, consistent displacement cluster is strong evidence of a duplicated "
           "(copy-moved) region." if largest_cluster > 5
           else "No strong evidence of a duplicated region -- scattered matches like this are "
                "common in images with repetitive texture.")
    )

    signal = Signal(
        key="image.copy_move", label="Copy-Move Detection", category="forensic",
        direction=direction, strength=strength, summary=summary, limits=LIMITS_COPYMOVE,
        details={"matched_pairs": match_count, "largest_displacement_cluster": largest_cluster, "keypoints": len(keypoints)},
    )
    return signal, heatmap_png


def lighting_consistency_heuristic(path: Path) -> Signal:
    try:
        with Image.open(path) as im:
            im = im.convert("L")
            arr = np.array(im, dtype=np.float32)
    except Exception as e:
        return Signal(
            key="image.lighting", label="Lighting Consistency (heuristic)", category="forensic",
            direction=0.0, strength=0.0, summary=f"Could not run: {e}",
            limits=LIMITS_LIGHTING, applicable=False,
        )

    gy, gx = np.gradient(arr)
    h, w = arr.shape
    quadrants = [
        gx[:h // 2, :w // 2], gx[:h // 2, w // 2:], gx[h // 2:, :w // 2], gx[h // 2:, w // 2:],
    ]
    mean_dirs = [float(np.mean(q)) for q in quadrants]
    spread = float(np.std(mean_dirs))
    overall_scale = float(np.std(gx)) + 1e-6
    normalized_spread = spread / overall_scale

    strength = float(np.clip((normalized_spread - 0.3) * 1.5, 0.0, 0.5))  # capped: this is a weak heuristic
    direction = float(np.clip((normalized_spread - 0.5) * 1.2, -0.1, 0.6))

    summary = (
        f"Quadrant brightness-gradient spread (normalized): {normalized_spread:.2f}. "
        + ("Noticeably inconsistent lighting direction across regions of the image." if normalized_spread > 0.5
           else "No strong global lighting-direction inconsistency detected.")
    )

    return Signal(
        key="image.lighting", label="Lighting Consistency (heuristic)", category="forensic",
        direction=direction, strength=strength, summary=summary, limits=LIMITS_LIGHTING,
        details={"normalized_spread": normalized_spread},
    )


def robustness_note(estimated_quality: float | None, width: int, height: int) -> dict[str, Any]:
    """Not a Signal -- just structured info for the report explaining how
    resizing/recompression/screenshotting would be expected to degrade the
    forensic signals above."""
    notes = []
    if estimated_quality is not None and estimated_quality < 75:
        notes.append(
            "This image has already been compressed enough that ELA and double-compression "
            "signals are partially degraded -- a genuinely manipulated copy and an innocently "
            "re-saved copy can look similar at this quality level."
        )
    if min(width, height) < 500:
        notes.append(
            "At this resolution, resizing or screenshotting would likely erase most fine-grained "
            "forensic traces (noise residual, copy-move keypoints) entirely."
        )
    if not notes:
        notes.append(
            "At this resolution/quality, one additional round of resizing, screenshotting, or "
            "recompression would still be expected to measurably weaken most signals above -- "
            "always prefer analyzing the most original file you can obtain."
        )
    return {"notes": notes}
