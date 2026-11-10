# Deepfake & AI-Content Detector (personal, local-first)

A personal tool for getting a second opinion on a photo, voice note, video,
or piece of text you're unsure about. You upload a file, it runs a battery
of provenance checks and forensic signals locally, and gives you an evidence
report -- never a bare score.

> **This tool produces evidence to help you judge content. It is not proof.**
> Every signal has known failure modes, documented next to it. "Inconclusive"
> is a normal, common, and often correct result. Never use this tool as the
> sole basis for accusing someone of lying, cheating, or using AI -- verify
> through an independent channel (see each report's "Recommended human
> verification steps").

## What it does

Upload an image, audio clip, video, or text file and get back:

- **Provenance first**: C2PA Content Credentials validation (valid / invalid-
  tampered / absent, never treating absence as suspicious) and EXIF/XMP/
  container metadata consistency checks.
- **Forensic signals**, each shown separately with its own strength and
  documented limits: Error Level Analysis, noise-residual analysis,
  double-JPEG ("ghost") compression detection, copy-move detection, a
  lighting-consistency heuristic, per-frame video timelines, face-region
  temporal flicker, audio spectrograms, breathing/room-noise and codec-trace
  checks, text burstiness/repetition/style-consistency, and scam-language
  indicators.
- **Optional pretrained-model signals** (off by default, see Settings): a
  Hugging Face AI-image classifier and GPT-2-based text perplexity.
- **A transparent combined verdict** -- *Likely Authentic*, *Inconclusive*,
  or *Likely Manipulated or AI-Generated* -- with a visible breakdown of
  which signals drove it, never a hidden black-box score.
- **Recommended next steps**: reverse-image-search links, a voice-clone
  scam-call checklist with a safe-word idea, and channel-independent
  verification advice.

Everything runs on your machine. History, tags, and exports (JSON/PDF) are
stored in a local SQLite database. No accounts, no server, nothing leaves
your machine unless you deliberately click a reverse-image-search link
(which opens *your* browser -- this app never uploads your file anywhere).

## Quick start

Requires Python 3.11+ on Windows/macOS/Linux.

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8008
```

Open **http://127.0.0.1:8008/** -- the backend serves the frontend itself,
there's no separate build step or dev server. A few demo reports are seeded
from `backend/samples/` on first run so History isn't empty.

### Fully local mode (no model downloads, ever)

This is the default. Settings → "Fully local mode" stays on, and the
optional Hugging Face/GPT-2 signals simply report "not run" instead of
downloading anything. To enable them:

```bash
pip install -r backend/requirements-ml.txt   # torch + transformers (~GBs)
```

Then toggle "Use optional ML models" in Settings. Model weights download
from Hugging Face **only** the first time you use that signal, and only if
you enabled it -- never implicitly.

### Running the tests

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests/ -q
```

47 tests cover C2PA validation (valid/tampered/absent, using a locally
self-signed throwaway test certificate -- see
`backend/tests/fixtures/make_fixtures.py`), metadata parsing, the forensic
functions on known synthetic samples, the combination logic, quality
warnings, and file validation/sandboxing.

## Project layout

```
backend/app/            FastAPI backend + all analysis code
  forensics/             one module per domain (c2pa, metadata, image, audio, video, text)
  pipeline.py            orchestrates per-media-type analysis into one report
  combine.py             the transparent signal-combination method
  security.py            upload validation, sandboxing, path-traversal guards
  db.py                  SQLite storage (reports, tags, settings)
  main.py                API routes
backend/samples/         small, self-made, labeled sample files (seeds the demo)
backend/tests/           pytest suite + synthetic test-fixture generator
frontend/                vanilla HTML/CSS/JS UI (no build step, no CDN)
eval/                    evaluation harness (see eval/README.md)
```

## How the combined verdict works

See `backend/app/combine.py` for the full method (short version): every
signal casts a weighted vote in [-1, 1]; votes are averaged by strength and
weight; any active quality warning (low resolution, heavy compression, short
clip/text, etc.) dampens the result toward zero; and if strong signals
disagree with each other, the result is forced to *Inconclusive* rather than
averaging into a falsely confident middle ground. Thresholds are deliberately
wide -- *Inconclusive* is the default outcome unless evidence clearly clears
a bar in one direction. The report's "contributions" breakdown always shows
exactly which signals moved the needle and by how much.

The scam/fraud-language indicator (text) is **excluded** from this
combination on purpose: a scam message is almost always 100% human-typed, so
it's shown as its own separate signal rather than being allowed to flip the
AI/manipulation verdict. Likewise, voice speaker-comparison similarity is
shown but contributes zero weight to the authenticity verdict, because high
similarity to a reference voice is not evidence of authenticity -- cloning
tools are built to maximize exactly that similarity.

## Responsible-use notes (also shown in the app)

- **Text detection is the least reliable signal category here.** AI-text
  detectors have well-documented high false-positive rates, especially for
  non-native English writers and formal/technical writing. Every text report
  carries a mandatory warning banner and this tool must never be the sole
  basis for an academic-integrity or workplace accusation.
- **Speaker comparison** only ever compares a clip against a reference clip
  *you* supply and have the right to use (e.g. a relative or colleague, with
  consent). This app does not do open-ended voice or face identification of
  people from their biometrics, and never will.
- **Missing provenance (no C2PA, no EXIF) is never treated as suspicious.**
  It's the normal state of most real and fake media alike.
- Treat every "Likely Manipulated" or "Likely Authentic" result as a lean
  based on the visible evidence, not a percentage, not a verdict, and not
  something to act on without independent verification.

## Security model

- Binds to `127.0.0.1` by default -- not reachable from your network.
- No accounts, no multi-user support, by design.
- Uploads are validated by sniffing file content (magic bytes), not by
  trusting the extension; oversized files, decompression-bomb-shaped images,
  and mislabeled files are rejected before decoding.
- Filenames are never used to build filesystem paths (path-traversal-proof
  by construction -- see `backend/app/security.py`); all rendered metadata
  and text is HTML-escaped in the frontend to prevent XSS, since EXIF/C2PA/
  encoder fields and text content all originate from untrusted uploaded
  files.
- Analysis code makes zero outbound network calls by construction (verified
  by code review of every forensics module). **Honesty note**: this is a
  personal, single-user, localhost-bound Windows/macOS/Linux app, not a
  hardened multi-tenant service with OS-level network namespacing or a
  container sandbox -- if you need that level of isolation, run it inside
  your own container/VM.
- No API keys are used by default. If you ever add one (e.g. for a future
  optional online lookup), keep it in an environment variable, never in code.

## Evaluation

`eval/run_eval.py` runs the real pipeline against a labeled set and reports
accuracy/precision/recall/false-positive-rate (with explicit "Inconclusive"
abstention handling -- scoring an honest abstention as "wrong" would punish
the exact behavior this project is designed to prefer), calibration (ECE),
and robustness under recompression/resizing/noise/screenshot-simulation.

**By default it runs on a small, self-generated, synthetic demonstration
set** (15 real vs. 15 copy-move-faked images, 10 bonafide vs. 10
regularity-only synthetic-proxy "spoof" audio clips, 13 human-written vs. 13
templated "AI-like" texts) -- **not** FaceForensics++, DFDC, Celeb-DF,
ASVspoof, or any published AI dataset. See `eval/README.md` for exactly how
to point the same harness at those real datasets, which you'd need to do
under their own licenses before trusting any generalization claim.

Latest run (`eval/results/eval_report.md`, regenerate with
`python eval/run_eval.py`):

| Media | Decided/Total | Abstention rate | Accuracy (decided) | FPR (decided) |
|---|---|---|---|---|
| Image (real vs. copy-move fake) | 2/30 | 93% | 0.50 | 1.00 |
| Audio (bonafide vs. synthetic-proxy spoof) | 0/20 | 100% | n/a | n/a |
| Text (human vs. templated AI-like) | 13/26 | 50% | 1.00 | n/a |

**Human-written text false-positive rate: 0 / 13 (0%)** -- no genuinely
human-written sample, including the deliberately simplified/non-native-
English-style ones, was ever called "Likely Manipulated or AI-Generated."
This is the number the project cares most about getting right, and on this
small set it held at zero.

Robustness: after recompression, resizing, added noise, or simulated
screenshotting, the image pipeline's decision rate dropped to 0% (100%
abstention) rather than flipping to false confidence -- i.e. degraded input
makes the tool *more* cautious, not wrongly confident. An earlier version of
the Error Level Analysis signal had a numerical instability that caused the
opposite (false "Likely Manipulated" on resized real images); this is fixed
and covered by a regression test (`test_ela_does_not_false_positive_on_near_lossless_recompression`).

### Honest limitations this evaluation surfaces

- **High abstention rate on the hand-engineered image/audio heuristics.**
  These are not trained classifiers; on a varied synthetic set they
  correctly decline to guess far more often than they commit to a verdict.
  That matches the project's "prefer Inconclusive" philosophy, but also
  means many real forgeries will likely also land on "Inconclusive" rather
  than a confident flag -- treat a quiet report as "not enough evidence
  either way," never as "confirmed authentic."
- **The non-ML audio spoofing heuristic did not discriminate at all** on the
  synthetic bonafide-vs-regularity-proxy set here (100% abstention both
  ways). Its own documented limits already say it's a rough heuristic, not
  a trained ASVspoof-style model -- this evaluation confirms that weakness
  numerically rather than just asserting it in prose.
- **None of this generalizes to real generators, real cloned voices, or
  real AI text** until re-run against real datasets per `eval/README.md`.
  Treat every number above as "the harness works," not "the detector works."

## Known gaps / not implemented

Documented here rather than silently faked:

- **Blink-rate and lip-sync mismatch detection** (video) require a facial-
  landmark model this local-first build does not bundle; the report shows
  these as explicitly unavailable, not a weak proxy standing in for them.
- **Eye-reflection/pupil-geometry consistency** (image) is not implemented
  for the same reason -- it needs reliable eye landmarks.
- The **lighting-consistency** signal (image) is a coarse global heuristic,
  not real 3D shadow/reflection geometry analysis -- its strength is
  deliberately capped low.

## License and dataset terms

This project contains only original code and small, self-generated synthetic
sample files (see `backend/samples/README.md`). It does not bundle
FaceForensics++, DFDC, Celeb-DF, ASVspoof, or any third-party dataset --
obtain and use those yourself under their own licenses if you extend the
evaluation harness. The optional ML extras use publicly available
pretrained models (GPT-2, a Hugging Face community AI-image classifier)
under their own respective licenses.
