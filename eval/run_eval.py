"""
Runs the evaluation harness end-to-end and writes eval/results/eval_report.{json,md}.

Usage (from repo root, with the backend venv active):
    python eval/run_eval.py

See eval/README.md for how to point this at real datasets (FaceForensics++,
DFDC, Celeb-DF, ASVspoof, AI-image/AI-text sets) instead of the small
self-generated demonstration set this script uses by default.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVAL_DIR.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(EVAL_DIR))

from app import config  # noqa: E402
from generate_eval_set import EVAL_DATA_DIR, generate_all  # noqa: E402
from metrics import evaluate_binary, expected_calibration_error, lean_score_to_probability  # noqa: E402
from robustness import TRANSFORMS  # noqa: E402

RESULTS_DIR = EVAL_DIR / "results"


def _verdict_to_pred(verdict: str) -> bool | None:
    if verdict == "likely_manipulated":
        return True
    if verdict == "likely_authentic":
        return False
    return None


def eval_images(manifest: list[dict]) -> dict:
    from app import pipeline
    y_true, y_pred, probs = [], [], []
    for i, rec in enumerate(manifest):
        report = pipeline.analyze_image(Path(rec["path"]), config.DEFAULT_SETTINGS, f"eval_img_{i}")
        combo = report["combination"]
        y_true.append(rec["label"] == "fake")
        y_pred.append(_verdict_to_pred(combo["verdict"]))
        probs.append(lean_score_to_probability(combo["lean_score"]))
    result = evaluate_binary(y_true, y_pred).to_dict()
    result["calibration"] = expected_calibration_error(probs, y_true)
    return result


def eval_images_with_transform(manifest: list[dict], transform_name: str, transform_fn) -> dict:
    from app import pipeline
    out_dir = EVAL_DATA_DIR / "images_robust" / transform_name
    out_dir.mkdir(parents=True, exist_ok=True)
    y_true, y_pred = [], []
    for i, rec in enumerate(manifest):
        src = Path(rec["path"])
        dst = out_dir / src.name
        transform_fn(src, dst)
        report = pipeline.analyze_image(dst, config.DEFAULT_SETTINGS, f"eval_img_{transform_name}_{i}")
        y_true.append(rec["label"] == "fake")
        y_pred.append(_verdict_to_pred(report["combination"]["verdict"]))
    return evaluate_binary(y_true, y_pred).to_dict()


def eval_audio(manifest: list[dict]) -> dict:
    from app import pipeline
    y_true, y_pred, probs = [], [], []
    for i, rec in enumerate(manifest):
        report = pipeline.analyze_audio(Path(rec["path"]), config.DEFAULT_SETTINGS, f"eval_audio_{i}")
        combo = report["combination"]
        y_true.append(rec["label"] == "spoof")
        y_pred.append(_verdict_to_pred(combo["verdict"]))
        probs.append(lean_score_to_probability(combo["lean_score"]))
    result = evaluate_binary(y_true, y_pred).to_dict()
    result["calibration"] = expected_calibration_error(probs, y_true)
    return result


def eval_text(manifest: list[dict]) -> dict:
    from app import pipeline
    y_true, y_pred = [], []
    human_false_positives = 0
    human_total = 0
    for i, rec in enumerate(manifest):
        report = pipeline.analyze_text(Path(rec["path"]), config.DEFAULT_SETTINGS, f"eval_text_{i}")
        combo = report["combination"]
        is_ai_like = rec["label"] == "ai_like"
        y_true.append(is_ai_like)
        pred = _verdict_to_pred(combo["verdict"])
        y_pred.append(pred)
        if not is_ai_like:
            human_total += 1
            if pred is True:
                human_false_positives += 1
    result = evaluate_binary(y_true, y_pred).to_dict()
    result["human_text_false_positive_rate"] = round(human_false_positives / human_total, 4) if human_total else None
    result["human_text_false_positives"] = human_false_positives
    result["human_text_total"] = human_total
    return result


def main():
    print("Generating self-made synthetic evaluation set (see eval/README.md)...")
    manifest = generate_all()

    print("Evaluating images...")
    image_results = eval_images(manifest["images"])

    print("Evaluating audio...")
    audio_results = eval_audio(manifest["audio"])

    print("Evaluating text (including human-text false-positive rate)...")
    text_results = eval_text(manifest["text"])

    print("Evaluating image robustness under common degradations...")
    robustness_results = {}
    for name, fn in TRANSFORMS.items():
        print(f"  -> {name}")
        robustness_results[name] = eval_images_with_transform(manifest["images"], name, fn)

    report = {
        "disclaimer": (
            "This evaluation runs on a small, self-generated, synthetic demonstration set "
            "(see eval/README.md), NOT on FaceForensics++/DFDC/Celeb-DF/ASVspoof/real AI-image or "
            "AI-text datasets. These numbers show the harness works and give a rough internal "
            "sanity check -- they are NOT a claim of real-world accuracy and must not be read as one."
        ),
        "images": image_results,
        "audio": audio_results,
        "text": text_results,
        "image_robustness": robustness_results,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "eval_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (RESULTS_DIR / "eval_report.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"\nWrote {RESULTS_DIR / 'eval_report.json'} and eval_report.md")
    print(render_markdown(report))


def render_markdown(report: dict) -> str:
    def row(label, r):
        return (f"| {label} | {r.get('n_decided')}/{r.get('n_total')} | "
                f"{r.get('abstention_rate')} | {r.get('accuracy')} | {r.get('precision')} | "
                f"{r.get('recall')} | {r.get('false_positive_rate')} |")

    lines = [
        "# Evaluation report (self-generated synthetic demonstration set)",
        "",
        f"> {report['disclaimer']}",
        "",
        "## Summary",
        "",
        "| Media | Decided/Total | Abstention rate | Accuracy | Precision | Recall | FPR |",
        "|---|---|---|---|---|---|---|",
        row("Image (real vs. copy-move fake)", report["images"]),
        row("Audio (bonafide vs. synthetic-proxy spoof)", report["audio"]),
        row("Text (human vs. templated AI-like)", report["text"]),
        "",
        f"**Human-written text false-positive rate: "
        f"{report['text']['human_text_false_positive_rate']} "
        f"({report['text']['human_text_false_positives']}/{report['text']['human_text_total']} "
        f"human texts incorrectly called 'Likely Manipulated or AI-Generated')**",
        "",
        "## Calibration (internal diagnostic only -- never shown in the app UI as a percentage)",
        "",
        f"Image ECE: {report['images']['calibration']['ece']}  ",
        f"Audio ECE: {report['audio']['calibration']['ece']}",
        "",
        "## Robustness under common degradations (image set)",
        "",
        "| Transform | Decided/Total | Abstention rate | Accuracy | Precision | Recall | FPR |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, r in report["image_robustness"].items():
        lines.append(row(name, r))
    lines.append("")
    lines.append(f"Baseline (no transform) accuracy for comparison: {report['images']['accuracy']}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
