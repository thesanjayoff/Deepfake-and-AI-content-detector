"""
C2PA Content Credentials validation using the official c2pa-python bindings.

Reports one of: valid, invalid/tampered, or absent. Absence is explicitly
never treated as evidence of fakery -- most real cameras and editors still
don't attach Content Credentials.
"""
from __future__ import annotations

from pathlib import Path

from ..signals import Signal

try:
    import c2pa  # type: ignore
    _C2PA_AVAILABLE = True
except Exception:  # pragma: no cover - environment without the native lib
    _C2PA_AVAILABLE = False


LIMITS_VALID = (
    "A valid signature only proves the manifest wasn't altered after signing and that it chains "
    "to some certificate -- it does NOT prove the certificate belongs to who you think, and does "
    "not guarantee the recorded edit history is complete (tools that don't support C2PA can edit "
    "content without leaving a trace in the manifest)."
)
LIMITS_ABSENT = (
    "Most cameras, phones, screenshots, and editors do not attach Content Credentials today. "
    "Absence of C2PA data is NOT evidence of manipulation -- it is the normal case for the vast "
    "majority of real and fake media alike."
)
LIMITS_INVALID = (
    "A broken/invalid signature means the file's bytes changed after signing (e.g. re-saving, "
    "re-compressing, stripping metadata, or genuine tampering) -- it does not by itself identify "
    "WHAT changed or whether the change was malicious."
)


def check_c2pa(path: Path) -> Signal:
    if not _C2PA_AVAILABLE:
        return Signal(
            key="provenance.c2pa",
            label="C2PA Content Credentials",
            category="provenance",
            direction=0.0,
            strength=0.0,
            summary="C2PA tooling is not available in this environment.",
            limits="This check did not run. " + LIMITS_ABSENT,
            applicable=False,
        )

    try:
        reader = c2pa.Reader(str(path))
        manifest_json = reader.json()
        import json as _json
        manifest = _json.loads(manifest_json)
    except Exception as e:
        msg = str(e).lower()
        not_found = (
            type(e).__name__ == "_C2paManifestNotFound"
            or "manifestnotfound" in msg
            or "no jumbf" in msg
            or "no claim" in msg
        )
        if not_found:
            return Signal(
                key="provenance.c2pa",
                label="C2PA Content Credentials",
                category="provenance",
                direction=0.0,
                strength=0.15,
                summary="No C2PA Content Credentials manifest found in this file.",
                limits=LIMITS_ABSENT,
            )
        # Any other error while parsing a manifest that IS present is itself
        # a signal: something is structurally wrong with the claimed credentials.
        return Signal(
            key="provenance.c2pa",
            label="C2PA Content Credentials",
            category="provenance",
            direction=0.6,
            strength=0.55,
            summary=f"A C2PA manifest appears to be present but failed validation ({e}).",
            limits=LIMITS_INVALID,
        )

    active = manifest.get("active_manifest")
    manifests = manifest.get("manifests", {})
    validation_statuses = manifest.get("validation_status", []) or []

    # C2PA distinguishes INTEGRITY failures (hash/signature mismatch -- the
    # content or manifest was altered after signing) from TRUST failures
    # (signature is cryptographically sound, but the certificate doesn't
    # chain to a root this installation recognizes as trusted). Only the
    # former is real evidence of tampering; the latter just means "can't
    # vouch for who signed this," which is common even for legitimate new
    # signers not yet in a trust list.
    trust_codes = {"signingCredential.untrusted", "signingCredential.expired"}
    integrity_errors = [
        v for v in validation_statuses
        if not str(v.get("code", "")).endswith(".OK") and v.get("code") not in trust_codes
    ]
    trust_warnings = [v for v in validation_statuses if v.get("code") in trust_codes]
    errors = integrity_errors

    active_manifest = manifests.get(active, {}) if active else {}
    claim_generator = active_manifest.get("claim_generator", "unknown tool")
    assertions = active_manifest.get("assertions", [])
    actions = []
    for a in assertions:
        if a.get("label", "").startswith("c2pa.actions"):
            for act in a.get("data", {}).get("actions", []):
                actions.append(act.get("action", "unknown"))

    signers = []
    for m in manifests.values():
        sig = m.get("signature_info") or {}
        if sig.get("issuer"):
            signers.append(sig.get("issuer"))

    details = {
        "claim_generator": claim_generator,
        "edit_actions": actions,
        "signers": signers,
        "manifest_count": len(manifests),
        "validation_errors": errors,
        "trust_warnings": trust_warnings,
    }

    if errors:
        return Signal(
            key="provenance.c2pa",
            label="C2PA Content Credentials",
            category="provenance",
            direction=0.7,
            strength=0.65,
            summary=f"C2PA manifest present but INVALID/tampered ({len(errors)} integrity error(s)): "
                    f"{errors[0].get('explanation', errors[0].get('code'))}",
            limits=LIMITS_INVALID,
            details=details,
        )

    if trust_warnings:
        return Signal(
            key="provenance.c2pa",
            label="C2PA Content Credentials",
            category="provenance",
            direction=-0.3,
            strength=0.4,
            summary=(
                f"C2PA manifest present with a cryptographically intact signature, but the signing "
                f"certificate is not in this app's trusted-issuer list (signer: "
                f"{', '.join(signers) or 'unknown'}). The content itself was not altered after "
                f"signing, but the signer's identity could not be vouched for."
            ),
            limits=LIMITS_VALID + " Additionally: an untrusted signing certificate means this app "
                    "cannot confirm WHO signed it, only that the content matches what was signed.",
            details=details,
        )

    return Signal(
        key="provenance.c2pa",
        label="C2PA Content Credentials",
        category="provenance",
        direction=-0.55,
        strength=0.6,
        summary=(
            f"C2PA manifest present and VALID. Signed by: {', '.join(signers) or 'unknown issuer'}. "
            f"Tool: {claim_generator}. Recorded actions: {', '.join(actions) or 'none listed'}."
        ),
        limits=LIMITS_VALID,
        details=details,
    )
