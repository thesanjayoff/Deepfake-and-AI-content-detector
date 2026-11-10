"""
Text analysis -- handled with the most caution of any module here.

AI-text detectors have HIGH false positive rates, especially on non-native
English writing and formal/technical prose. Every function below returns
passage-level evidence (which sentences drove the signal), never a bare
"AI-written: NN%" number, and the API layer attaches a mandatory warning
banner to every text report.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ..signals import Signal

MANDATORY_TEXT_WARNING = (
    "AI-text detectors (including every signal below) have HIGH false-positive rates, "
    "especially for non-native English writers, formal/technical writing, and short texts. "
    "These signals must NEVER be used alone to accuse someone of cheating, lying, or using AI. "
    "Treat this as a prompt to ask the author directly or verify independently -- not as proof."
)

LIMITS_BURSTINESS = (
    "Burstiness (variation in sentence length/rhythm) is a weak, easily-confounded signal. Many "
    "careful human writers (and many legitimate styles -- technical docs, legal text, non-native "
    "speakers writing deliberately) produce low-burstiness text indistinguishable from AI output."
)
LIMITS_REPETITION = (
    "Repetition can indicate templated/AI-generated text, but is also completely normal in formal "
    "writing, instructions, legal documents, and non-native English (which often reuses safe "
    "phrasing). High repetition alone proves nothing about origin."
)
LIMITS_STYLE_CONSISTENCY = (
    "Style-consistency checks for abrupt shifts in vocabulary/sentence rhythm across a document "
    "(e.g. one paragraph pasted from elsewhere). It cannot distinguish 'AI-written' from 'human "
    "copy-pasted from another human source', and is unreliable on short documents."
)
LIMITS_PERPLEXITY = (
    "Perplexity measures how 'surprising' text is to a specific small local language model, NOT "
    "a ground truth about AI authorship. It is skewed by topic, formality, and especially by the "
    "writer's first language -- non-native English writers are frequently and unfairly flagged by "
    "this kind of signal in published research. Published critiques (e.g. of GPTZero/Binoculars-"
    "style tools) document this clearly."
)

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[A-Za-z']+")


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = _SENT_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def basic_stats(text: str) -> dict[str, Any]:
    words = _WORD_RE.findall(text)
    sentences = split_sentences(text)
    return {
        "num_chars": len(text),
        "num_words": len(words),
        "num_sentences": len(sentences),
        "words": words,
        "sentences": sentences,
    }


def burstiness_signal(text: str) -> Signal:
    sentences = split_sentences(text)
    if len(sentences) < 4:
        return Signal(
            key="text.burstiness", label="Sentence-Length Burstiness", category="forensic",
            direction=0.0, strength=0.0, summary="Too few sentences to assess burstiness.",
            limits=LIMITS_BURSTINESS, applicable=False,
        )
    lengths = [len(_WORD_RE.findall(s)) for s in sentences]
    mean_len = sum(lengths) / len(lengths)
    var = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
    std = var ** 0.5
    cv = std / mean_len if mean_len else 0.0

    uniform_sentences = [s for s, l in zip(sentences, lengths) if abs(l - mean_len) < 0.15 * mean_len]
    flagged_examples = uniform_sentences[:3]

    direction = 0.0
    strength = 0.3
    if cv < 0.25:
        direction = 0.4
        strength = 0.45
        summary = (
            f"Low sentence-length variation (coefficient of variation {cv:.2f}, mean length "
            f"{mean_len:.1f} words). Sentences are unusually uniform in rhythm, a pattern more "
            f"common in AI-generated text -- but also in careful, formal, or non-native writing."
        )
    elif cv > 0.6:
        direction = -0.25
        strength = 0.3
        summary = (
            f"High sentence-length variation (coefficient of variation {cv:.2f}). Natural, varied "
            f"rhythm typical of human writing, though AI text can also vary when prompted to."
        )
    else:
        summary = f"Moderate sentence-length variation (coefficient of variation {cv:.2f}), inconclusive on its own."

    return Signal(
        key="text.burstiness", label="Sentence-Length Burstiness", category="forensic",
        direction=direction, strength=strength, summary=summary, limits=LIMITS_BURSTINESS,
        details={"cv": cv, "mean_sentence_length": mean_len, "example_uniform_sentences": flagged_examples},
    )


def repetition_signal(text: str) -> Signal:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if len(words) < 30:
        return Signal(
            key="text.repetition", label="Phrase Repetition", category="forensic",
            direction=0.0, strength=0.0, summary="Too little text to assess repetition.",
            limits=LIMITS_REPETITION, applicable=False,
        )
    trigrams = [tuple(words[i:i + 3]) for i in range(len(words) - 2)]
    counts = Counter(trigrams)
    repeated = {k: v for k, v in counts.items() if v > 1}
    repeated_fraction = sum(repeated.values()) / len(trigrams) if trigrams else 0.0

    top_repeated = sorted(repeated.items(), key=lambda kv: kv[1], reverse=True)[:5]
    examples = [" ".join(k) for k, _ in top_repeated]

    direction = 0.0
    strength = 0.25
    if repeated_fraction > 0.15:
        direction = 0.35
        strength = 0.4
        summary = (
            f"{repeated_fraction*100:.0f}% of 3-word phrases repeat elsewhere in the text -- "
            f"notably templated/repetitive phrasing. Common in some AI outputs, but also in "
            f"formal writing, instructions, and legitimate stylistic repetition for emphasis."
        )
    else:
        summary = f"{repeated_fraction*100:.0f}% of 3-word phrases repeat -- within a normal range."

    return Signal(
        key="text.repetition", label="Phrase Repetition", category="forensic",
        direction=direction, strength=strength, summary=summary, limits=LIMITS_REPETITION,
        details={"repeated_fraction": repeated_fraction, "example_repeated_phrases": examples},
    )


def style_consistency_signal(text: str) -> Signal:
    sentences = split_sentences(text)
    if len(sentences) < 8:
        return Signal(
            key="text.style_consistency", label="Style Consistency Across Document", category="forensic",
            direction=0.0, strength=0.0, summary="Document too short to split into chunks for comparison.",
            limits=LIMITS_STYLE_CONSISTENCY, applicable=False,
        )
    chunk_size = max(3, len(sentences) // 4)
    chunks = [sentences[i:i + chunk_size] for i in range(0, len(sentences), chunk_size)]
    chunks = [c for c in chunks if c]

    def vocab_richness(chunk: list[str]) -> float:
        words = [w.lower() for s in chunk for w in _WORD_RE.findall(s)]
        return len(set(words)) / len(words) if words else 0.0

    def avg_word_len(chunk: list[str]) -> float:
        words = [w for s in chunk for w in _WORD_RE.findall(s)]
        return sum(len(w) for w in words) / len(words) if words else 0.0

    richness = [vocab_richness(c) for c in chunks]
    wordlens = [avg_word_len(c) for c in chunks]
    richness_spread = (max(richness) - min(richness)) if richness else 0.0
    wordlen_spread = (max(wordlens) - min(wordlens)) if wordlens else 0.0

    direction = 0.0
    strength = 0.25
    if richness_spread > 0.25 or wordlen_spread > 1.5:
        direction = 0.3
        strength = 0.35
        worst_idx = int(max(range(len(richness)), key=lambda i: abs(richness[i] - sum(richness) / len(richness))))
        summary = (
            f"Noticeable shift in vocabulary richness/word length between sections of the document "
            f"(richness spread {richness_spread:.2f}, word-length spread {wordlen_spread:.2f}). This can "
            f"indicate mixed authorship or pasted-in content from elsewhere -- section "
            f"{worst_idx + 1} of {len(chunks)} stands out most."
        )
    else:
        summary = "Vocabulary and sentence style look reasonably consistent across the document."

    return Signal(
        key="text.style_consistency", label="Style Consistency Across Document", category="forensic",
        direction=direction, strength=strength, summary=summary, limits=LIMITS_STYLE_CONSISTENCY,
        details={"richness_by_chunk": richness, "avg_word_len_by_chunk": wordlens},
    )


_PERPLEXITY_MODEL_CACHE: dict[str, Any] = {}


def perplexity_signal(text: str, enable_ml: bool) -> Signal:
    if not enable_ml:
        return Signal(
            key="text.perplexity", label="Language-Model Perplexity", category="model",
            direction=0.0, strength=0.0,
            summary="Not run: optional ML models are disabled in Settings (fully local, lightweight "
                    "mode). Enable 'Use optional ML models' to compute this with a local GPT-2 model.",
            limits=LIMITS_PERPLEXITY, applicable=False,
        )
    try:
        import torch
        from transformers import GPT2LMHeadModel, GPT2TokenizerFast
    except ImportError:
        return Signal(
            key="text.perplexity", label="Language-Model Perplexity", category="model",
            direction=0.0, strength=0.0,
            summary="Not available: optional ML dependencies (torch/transformers) are not installed. "
                    "See README for the optional extras install.",
            limits=LIMITS_PERPLEXITY, applicable=False,
        )

    if "gpt2" not in _PERPLEXITY_MODEL_CACHE:
        tok = GPT2TokenizerFast.from_pretrained("gpt2")
        model = GPT2LMHeadModel.from_pretrained("gpt2")
        model.eval()
        _PERPLEXITY_MODEL_CACHE["gpt2"] = (tok, model)
    tok, model = _PERPLEXITY_MODEL_CACHE["gpt2"]

    encodings = tok(text, return_tensors="pt", truncation=True, max_length=1024)
    input_ids = encodings["input_ids"]
    if input_ids.shape[1] < 8:
        return Signal(
            key="text.perplexity", label="Language-Model Perplexity", category="model",
            direction=0.0, strength=0.0, summary="Text too short for a meaningful perplexity estimate.",
            limits=LIMITS_PERPLEXITY, applicable=False,
        )

    import torch as _torch
    with _torch.no_grad():
        outputs = model(input_ids, labels=input_ids)
        neg_log_likelihood = outputs.loss.item()
    perplexity = float(_torch.exp(_torch.tensor(neg_log_likelihood)))

    # Rough, intentionally conservative bucketing -- GPT-2 perplexity varies
    # hugely by domain, so this contributes modestly and is capped in strength.
    direction = 0.0
    if perplexity < 25:
        direction = 0.35
        note = "quite low (text is very predictable to this small local model)"
    elif perplexity > 90:
        direction = -0.2
        note = "high (text is unpredictable to this small local model, more typical of varied human writing)"
    else:
        note = "in a common middle range"

    return Signal(
        key="text.perplexity", label="Language-Model Perplexity", category="model",
        direction=direction, strength=0.3, summary=f"GPT-2 perplexity: {perplexity:.1f} -- {note}.",
        limits=LIMITS_PERPLEXITY, details={"perplexity": perplexity, "model": "gpt2 (local, 124M params)"},
    )


SCAM_URGENCY_RE = re.compile(
    r"\b(urgent|immediately|right away|act now|don'?t tell|keep this (a )?secret|"
    r"as soon as possible|asap|before it'?s too late|limited time)\b", re.IGNORECASE)
SCAM_PAYMENT_RE = re.compile(
    r"\b(gift card|wire transfer|bitcoin|crypto|western union|moneygram|bank transfer|"
    r"routing number|send money|processing fee|advance fee|unlock(ing)? fee)\b", re.IGNORECASE)
SCAM_IMPERSONATION_RE = re.compile(
    r"\b(this is (your|the) (boss|ceo|manager)|it'?s me|from (the )?irs|from (the )?bank|"
    r"law enforcement|court order|final notice|your account (has been|is) (suspended|locked))\b",
    re.IGNORECASE)


def scam_text_indicators(text: str) -> Signal:
    urgency_hits = SCAM_URGENCY_RE.findall(text)
    payment_hits = SCAM_PAYMENT_RE.findall(text)
    impersonation_hits = SCAM_IMPERSONATION_RE.findall(text)
    total_hits = len(urgency_hits) + len(payment_hits) + len(impersonation_hits)

    categories = []
    if urgency_hits:
        categories.append(f"urgency language ({len(urgency_hits)} match(es))")
    if payment_hits:
        categories.append(f"payment/money-movement requests ({len(payment_hits)} match(es))")
    if impersonation_hits:
        categories.append(f"impersonation/authority framing ({len(impersonation_hits)} match(es))")

    if total_hits == 0:
        summary = "No common scam-text keywords detected."
        direction = 0.0
        strength = 0.2
    else:
        summary = "Scam-pattern indicators found: " + "; ".join(categories) + "."
        direction = min(0.9, 0.25 * total_hits)
        strength = min(0.8, 0.3 + 0.1 * total_hits)

    return Signal(
        key="text.scam_indicators", label="Scam/Fraud Language Indicators", category="scam",
        direction=direction, strength=strength, summary=summary,
        limits="Keyword-based -- legitimate urgent requests exist, and sophisticated scams avoid "
               "obvious keywords. This is a checklist aid, not a fraud detector.",
        details={"urgency_hits": urgency_hits, "payment_hits": payment_hits, "impersonation_hits": impersonation_hits},
    )
