# Evaluation report (self-generated synthetic demonstration set)

> This evaluation runs on a small, self-generated, synthetic demonstration set (see eval/README.md), NOT on FaceForensics++/DFDC/Celeb-DF/ASVspoof/real AI-image or AI-text datasets. These numbers show the harness works and give a rough internal sanity check -- they are NOT a claim of real-world accuracy and must not be read as one.

## Summary

| Media | Decided/Total | Abstention rate | Accuracy | Precision | Recall | FPR |
|---|---|---|---|---|---|---|
| Image (real vs. copy-move fake) | 2/30 | 0.9333 | 0.5 | 0.5 | 1.0 | 1.0 |
| Audio (bonafide vs. synthetic-proxy spoof) | 0/20 | 1.0 | None | None | None | None |
| Text (human vs. templated AI-like) | 13/26 | 0.5 | 1.0 | 1.0 | 1.0 | None |

**Human-written text false-positive rate: 0.0 (0/13 human texts incorrectly called 'Likely Manipulated or AI-Generated')**

## Calibration (internal diagnostic only -- never shown in the app UI as a percentage)

Image ECE: 0.0726  
Audio ECE: 0.3758

## Robustness under common degradations (image set)

| Transform | Decided/Total | Abstention rate | Accuracy | Precision | Recall | FPR |
|---|---|---|---|---|---|---|
| recompressed_q45 | 0/30 | 1.0 | None | None | None | None |
| resized_50pct | 0/30 | 1.0 | None | None | None | None |
| added_noise | 0/30 | 1.0 | None | None | None | None |
| screenshot_simulated | 0/30 | 1.0 | None | None | None | None |

Baseline (no transform) accuracy for comparison: 0.5