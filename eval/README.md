# Evaluation harness

`python eval/run_eval.py` (with the backend venv active) runs the detector's
own pipeline over a labeled dataset and reports accuracy, precision, recall,
false-positive rate, abstention rate, and calibration (ECE), plus a
robustness check under recompression/resizing/noise/screenshot-simulation.

## What it runs on by default

By default this generates a **small, self-made, entirely synthetic**
demonstration set (`eval/generate_eval_set.py`, written into `eval/data/`,
not committed to git):

- **Images**: 15 "real" synthetic photos vs. 15 copy-move-spliced versions.
- **Audio**: 10 "bonafide" synthetic voice-like tones (with natural pitch
  jitter) vs. 10 "spoof-proxy" tones (perfectly regular, no jitter -- a stand-
  in for a TTS-style regularity artifact, **not a real voice clone**).
- **Text**: 13 human-written short texts (including simplified,
  non-native-English-style phrasing) vs. 13 templated/repetitive "AI-like"
  texts.

**This is not FaceForensics++, DFDC, Celeb-DF, ASVspoof, or any published
AI-image/AI-text dataset.** The numbers in `eval/results/eval_report.md` are
a sanity check that the pipeline and metrics work end-to-end, not a claim
about real-world accuracy. Report generalization only ever as measured on a
real held-out dataset you ran yourself, see below.

## Plugging in real datasets

The evaluator just needs a list of `{"path": ..., "label": ...}` records --
swap `generate_eval_set.generate_all()` for your own loader pointed at:

- **Video deepfakes**: [FaceForensics++](https://github.com/ondyari/FaceForensics),
  [DFDC](https://ai.meta.com/datasets/dfdc/), [Celeb-DF](https://github.com/yuezunli/celeb-deepfakeforensics).
  Extract frames with `backend/app/forensics/video_forensics.extract_sampled_frames`
  or run `pipeline.analyze_video` directly on clips; label `real`/`fake` from
  each dataset's manifest.
- **Audio spoofing**: [ASVspoof](https://www.asvspoof.org/) (2019/2021) --
  label `bonafide`/`spoof` from the official protocol files, run
  `pipeline.analyze_audio`.
- **AI images**: any dataset pairing real photos with outputs from
  Midjourney/SDXL/DALL-E/etc (several are on Hugging Face Datasets).
- **AI text**: public AI-text-detection benchmark sets, and critically,
  **non-native-English human writing corpora** (e.g. learner-corpus
  datasets) to stress-test the false-positive concern this project takes
  most seriously.

You must download and use all of the above under their own licenses/terms --
nothing from them is bundled here.

## Generalization testing

"Generalization" means evaluating on fakes from a generator/source NOT used
to build or tune this app's heuristics (which were hand-written against the
small synthetic set here, not trained on any dataset). To test it
meaningfully: point the harness at a real dataset as above, and separately
report results broken out by source/generator (most published datasets'
manifests already group by generator). This repo does not fabricate such a
result -- run it yourself and the report will reflect real numbers.

## Robustness testing

`eval/robustness.py` re-runs the image set through: JPEG recompression
(quality 45), 50% downscaling, additive Gaussian noise, and a crude
"screenshot" simulation (downscale + upscale + recompress). The report shows
accuracy/FPR before and after each transform so you can see how much
reliability actually degrades -- this matches the "robustness note" shown in
the app's own image reports.
