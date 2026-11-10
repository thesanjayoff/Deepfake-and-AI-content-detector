# Sample files

These are small, **self-generated, synthetic** files used to seed the demo
history on first run and as safe examples for manual testing. None of them
are real photos, real voices, or real people -- everything here was produced
programmatically by `backend/tests/fixtures/make_fixtures.py`.

| File | What it is |
|---|---|
| `genuine_synthetic_photo.jpg` | A synthetic gradient+noise "photo-like" image with no edits applied. Used as a clean baseline. |
| `edited_copy_move_synthetic_photo.jpg` | The same base image with a region duplicated (copy-moved) elsewhere in the frame -- a labeled, simple forgery for testing copy-move detection. |
| `recompressed_synthetic_photo.jpg` | The same base image saved, reopened, and re-saved at low quality twice, to exercise double-compression detection without any real edit. |
| `genuine_human_text.txt` | Casually-written example text (written for this project, not AI-generated) with natural, varied sentence rhythm. |
| `labeled_ai_style_text.txt` | Deliberately templated/repetitive text, labeled here as a stand-in for "AI-style" output to exercise burstiness/repetition signals. **Not actually AI-generated** -- it's a repeated template sentence. |
| `labeled_scam_text.txt` | A deliberately written example of urgency/secrecy/payment scam phrasing, for testing the scam-indicator signal only. |
| `genuine_synthetic_voice.wav` | A synthesized harmonic tone shaped like speech (NOT a real voice recording, NOT a deepfake) for exercising the audio pipeline. |
| `genuine_synthetic_voice_phone_quality.wav` | The same synthesis at an 8kHz "phone call" sample rate with added noise, for exercising codec/quality heuristics. |

No real datasets (FaceForensics++, DFDC, Celeb-DF, ASVspoof, etc.) are
bundled here -- see the main README's "Evaluation" section for how to point
the evaluation scripts at those datasets yourself under their own licenses.
