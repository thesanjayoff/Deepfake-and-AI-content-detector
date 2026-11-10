"""Static, media-type-specific human verification guidance appended to every report."""
from __future__ import annotations


COMMON_STEPS = [
    "This report is evidence to help YOU judge the content -- it is not proof, and 'Inconclusive' "
    "is a normal, expected result for a lot of real media.",
    "If this matters (money, a relationship, a legal/work decision), verify through a channel the "
    "sender doesn't control: call a known phone number, message on a separate known account, or "
    "ask in person.",
]

IMAGE_STEPS = [
    "Reverse image search the original file (Google Lens, TinEye) to check if it appears earlier, "
    "elsewhere, or in a different context.",
    "Ask the sender for the original, unedited, full-resolution file and any related photos from "
    "the same moment.",
    "Look for the original posting source (news outlet, verified account, original photographer) "
    "rather than trusting a re-shared copy.",
]

AUDIO_STEPS = [
    "If this is a call or voice message asking for money, urgency, or secrecy: hang up and call "
    "the person back on a number YOU already have saved, not one they just gave you.",
    "Ask a question only the real person would know the answer to, ideally using a pre-agreed "
    "safe word/phrase (see the scam-call checklist in this report).",
    "Request a live video call -- real-time back-and-forth video is currently much harder to fake "
    "convincingly than a pre-recorded voice clip.",
]

VIDEO_STEPS = AUDIO_STEPS + IMAGE_STEPS

TEXT_STEPS = [
    "Do not accuse anyone of using AI based on this report alone -- ask them directly and listen "
    "to their explanation.",
    "Check whether similar phrasing exists elsewhere (the person's own past writing, a template, "
    "or a cited source) before assuming AI origin.",
    "For academic/work concerns, use your institution's/organization's formal process, which "
    "should never rely on a single automated score.",
]

SCAM_CALL_SAFE_WORD_TIP = (
    "Family/team safe word idea: pick an unusual word unrelated to money or emergencies, never "
    "say it over email/text/social media, and agree that any urgent money/secrecy request must "
    "include it when asked for -- refusal or hesitation to provide it is itself a red flag."
)


def steps_for(media_type: str) -> list[str]:
    base = list(COMMON_STEPS)
    if media_type == "image":
        return base + IMAGE_STEPS
    if media_type == "audio":
        return base + AUDIO_STEPS
    if media_type == "video":
        return base + VIDEO_STEPS
    if media_type == "text":
        return base + TEXT_STEPS
    return base
