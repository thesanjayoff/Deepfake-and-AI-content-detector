"""
Generates small, self-made sample/test fixtures used by the test suite and
seeded demo. Nothing here is a real photo of a real person, and no real
dataset content is bundled -- everything is synthesized locally.

Run manually with: python -m tests.fixtures.make_fixtures
(also invoked automatically by the pytest fixture in conftest.py if files
are missing)
"""
from __future__ import annotations

import datetime
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

FIXTURES_DIR = Path(__file__).resolve().parent


def _gradient_photo_like(w=800, h=600, seed=0) -> Image.Image:
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 1, w)
    y = np.linspace(0, 1, h)
    xx, yy = np.meshgrid(x, y)
    base = (
        80 + 120 * xx + 60 * np.sin(4 * yy * np.pi) + rng.normal(0, 6, size=(h, w))
    )
    arr = np.stack([
        np.clip(base + 20, 0, 255),
        np.clip(base, 0, 255),
        np.clip(base - 15, 0, 255),
    ], axis=-1).astype(np.uint8)
    im = Image.fromarray(arr, mode="RGB")
    draw = ImageDraw.Draw(im)
    draw.ellipse((w * 0.3, h * 0.3, w * 0.5, h * 0.55), fill=(200, 160, 130))
    draw.rectangle((w * 0.1, h * 0.7, w * 0.4, h * 0.9), fill=(40, 60, 90))
    # Re-apply matching sensor-like noise over the WHOLE image (including the
    # flat shapes just drawn) so this fixture is a clean true-negative control
    # -- a real photo doesn't have perfectly flat, noise-free regions.
    final = np.array(im).astype(np.float32)
    final += rng.normal(0, 4.0, size=final.shape)
    im = Image.fromarray(np.clip(final, 0, 255).astype(np.uint8), mode="RGB")
    return im


def make_plain_jpeg() -> Path:
    path = FIXTURES_DIR / "plain_photo.jpg"
    im = _gradient_photo_like(seed=1)
    im.save(path, "JPEG", quality=92)
    return path


def make_spliced_jpeg() -> Path:
    """A plain photo with a copy-pasted (duplicated) region -- simulates a
    naive copy-move splice for testing copy-move detection. The duplicated
    patch is taken from around the ellipse's edge so it contains enough
    corner-like structure for keypoint matching to actually find it."""
    path = FIXTURES_DIR / "spliced_photo.jpg"
    im = _gradient_photo_like(seed=1)
    arr = np.array(im)
    w, h = im.size
    sy0, sy1 = int(h * 0.25), int(h * 0.60)
    sx0, sx1 = int(w * 0.22), int(w * 0.55)
    src = arr[sy0:sy1, sx0:sx1].copy()
    ph, pw = src.shape[:2]
    dy0, dx0 = int(h * 0.05), int(w * 0.55)
    arr[dy0:dy0 + ph, dx0:dx0 + pw] = src
    Image.fromarray(arr).save(path, "JPEG", quality=92)
    return path


def make_recompressed_jpeg() -> Path:
    """Same base image saved at high quality then re-saved at low quality
    twice -- simulates double-JPEG-compression artifacts."""
    path = FIXTURES_DIR / "recompressed_photo.jpg"
    im = _gradient_photo_like(seed=1)
    buf1 = io.BytesIO()
    im.save(buf1, "JPEG", quality=90)
    buf1.seek(0)
    im2 = Image.open(buf1)
    buf2 = io.BytesIO()
    im2.save(buf2, "JPEG", quality=40)
    buf2.seek(0)
    im3 = Image.open(buf2)
    im3.save(path, "JPEG", quality=40)
    return path


def make_tiny_jpeg() -> Path:
    path = FIXTURES_DIR / "tiny_photo.jpg"
    im = _gradient_photo_like(w=120, h=90, seed=2)
    im.save(path, "JPEG", quality=70)
    return path


def make_c2pa_signed_valid() -> Path:
    """A JPEG signed with a locally generated, throwaway self-signed test
    certificate -- NOT a trusted real-world credential, just enough to
    exercise the 'valid manifest' code path end-to-end."""
    import c2pa
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    # C2PA rejects a self-signed leaf, so build a minimal 2-level chain:
    # a throwaway root CA signs a throwaway leaf signing cert.
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "DAICD Local Test Root"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Local Test Only - Not Trusted"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    root_cert = (
        x509.CertificateBuilder()
        .subject_name(root_subject)
        .issuer_name(root_subject)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )
    root_ski = x509.SubjectKeyIdentifier.from_public_key(root_key.public_key())

    key = ec.generate_private_key(ec.SECP256R1())
    leaf_subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "DAICD Local Test Signer"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Local Test Only - Not Trusted"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(leaf_subject)
        .issuer_name(root_subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=True, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.EMAIL_PROTECTION]),
            critical=False,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(root_ski), critical=False)
        .sign(root_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM) + root_cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    source_path = make_plain_jpeg()
    out_path = FIXTURES_DIR / "c2pa_signed_valid.jpg"

    signer_info = c2pa.C2paSignerInfo(
        alg=b"es256",
        sign_cert=cert_pem,
        private_key=key_pem,
        ta_url=None,
    )
    signer = c2pa.Signer.from_info(signer_info)

    manifest = {
        "claim_generator_info": [{"name": "DAICD local test fixture generator", "version": "0.1.0"}],
        "title": "DAICD test fixture (valid signature)",
        "format": "image/jpeg",
        "assertions": [
            {
                "label": "c2pa.actions",
                "data": {
                    "actions": [
                        {
                            "action": "c2pa.created",
                            "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/digitalCapture",
                        }
                    ]
                },
            }
        ],
    }
    builder = c2pa.Builder(json.dumps(manifest))
    with open(source_path, "rb") as src, open(out_path, "wb") as dst:
        builder.sign(signer, "image/jpeg", src, dst)
    return out_path


def make_c2pa_tampered() -> Path:
    """Takes the validly-signed fixture and flips pixel bytes AFTER signing,
    so the embedded manifest's content hash no longer matches -- this is
    what a real tampered/invalid-signature file looks like."""
    valid_path = make_c2pa_signed_valid()
    data = bytearray(valid_path.read_bytes())
    # Flip some bytes well past the JPEG header/APP segments, inside scan data,
    # without corrupting the JUMBF manifest box itself.
    start = len(data) - 2000
    for i in range(start, start + 40):
        data[i] ^= 0xFF
    out_path = FIXTURES_DIR / "c2pa_tampered.jpg"
    out_path.write_bytes(bytes(data))
    return out_path


def make_sample_human_text() -> Path:
    path = FIXTURES_DIR / "sample_human_text.txt"
    path.write_text(
        "So I finally got around to fixing the leaky faucet in the upstairs bathroom this "
        "weekend -- took way longer than I expected honestly. Turns out the cartridge was "
        "just worn out, nothing fancy, but of course the hardware store didn't have the exact "
        "part so I had to drive to the other one across town. Anyway it's fixed now, dripping "
        "finally stopped, and I didn't flood the place which feels like a personal win. Might "
        "tackle the garage door opener next, it's been making this awful grinding noise for "
        "weeks and my partner is losing patience with it. We'll see.",
        encoding="utf-8",
    )
    return path


def make_sample_ai_like_text() -> Path:
    path = FIXTURES_DIR / "sample_ai_like_text.txt"
    sentence = (
        "In conclusion, it is important to note that this topic offers a variety of benefits "
        "and considerations that are worth exploring in further detail. "
    )
    path.write_text((sentence * 25), encoding="utf-8")
    return path


def make_sample_scam_text() -> Path:
    path = FIXTURES_DIR / "sample_scam_text.txt"
    path.write_text(
        "Hi it's me, I'm in trouble and I need you to help me right now. Please don't tell "
        "anyone about this, keep it between us. I need you to send gift cards as soon as "
        "possible, it's urgent, I'll explain everything later but I need this done today. "
        "Use my new number from now on, don't call the old one.",
        encoding="utf-8",
    )
    return path


def make_synthetic_voice_wav(path_name: str, *, noisy: bool, telephony: bool, seed: int) -> Path:
    """A synthetic sine/harmonic-based 'voice-like' tone, NOT a real voice
    recording and NOT a real deepfake -- purely for exercising the audio
    pipeline's code paths in tests (duration, spectrogram, codec-rate checks)."""
    import soundfile as sf

    sr = 8000 if telephony else 16000
    duration = 4.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    rng = np.random.default_rng(seed)
    f0 = 140.0
    sig = np.zeros_like(t)
    for harmonic, amp in [(1, 1.0), (2, 0.5), (3, 0.25), (4, 0.12)]:
        wobble = 1 + 0.01 * np.sin(2 * np.pi * 2.0 * t)
        sig += amp * np.sin(2 * np.pi * f0 * harmonic * wobble * t)
    envelope = 0.5 * (1 + np.sin(2 * np.pi * 2.2 * t)) ** 2
    sig = sig * envelope
    sig = sig / np.max(np.abs(sig) + 1e-9) * 0.6
    if noisy:
        sig = sig + rng.normal(0, 0.05, size=sig.shape)
    else:
        sig = sig + rng.normal(0, 0.002, size=sig.shape)  # tiny room-noise floor
    path = FIXTURES_DIR / path_name
    sf.write(path, sig.astype(np.float32), sr)
    return path


def make_all() -> dict[str, Path]:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    out["plain_jpeg"] = make_plain_jpeg()
    out["spliced_jpeg"] = make_spliced_jpeg()
    out["recompressed_jpeg"] = make_recompressed_jpeg()
    out["tiny_jpeg"] = make_tiny_jpeg()
    try:
        out["c2pa_valid"] = make_c2pa_signed_valid()
        out["c2pa_tampered"] = make_c2pa_tampered()
    except Exception as e:  # pragma: no cover
        print(f"Skipping C2PA fixtures (c2pa-python unavailable in this env): {e}")
    out["human_text"] = make_sample_human_text()
    out["ai_like_text"] = make_sample_ai_like_text()
    out["scam_text"] = make_sample_scam_text()
    out["voice_clean"] = make_synthetic_voice_wav("voice_clean.wav", noisy=False, telephony=False, seed=10)
    out["voice_reference"] = make_synthetic_voice_wav("voice_reference.wav", noisy=False, telephony=False, seed=10)
    out["voice_different_speaker"] = make_synthetic_voice_wav("voice_different_speaker.wav", noisy=False, telephony=False, seed=99)
    out["voice_phone_noisy"] = make_synthetic_voice_wav("voice_phone_noisy.wav", noisy=True, telephony=True, seed=11)
    return out


if __name__ == "__main__":
    for name, p in make_all().items():
        print(f"{name}: {p}")
