"""cTAKES-style medication sidecar (no Java binary, no new training).

S1 — dictionary NER of ASM names (Savova et al. 2010: lookup + span), not MedCAT
and not ``rules.fields.medication`` extraction.
S2 — i2b2/n2c2 medication attributes on those spans (Uzuner et al. 2010):
current vs discontinued vs suggested; PRN → rescue; one-off → acute.
Negation: Chapman 2001 NegEx pre-negation in the same sentence.

Detector name on every item: ``ctakes``. Overlapping LEO paths only.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from rules.asm_lexicon import ASM_LEXICON
from rules.asm_us_brand_aliases import US_ASM_BRAND_ALIASES
from services.chain_llm import FieldItem
from services.med_context import drug_role

DETECTOR = "ctakes"

_SENT_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])|\n+")
_DOSE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|ml|units?)\b"
    r"(?:\s*(?:bid|tid|qid|qd|od|bd|prn|daily|twice daily|twice a day))?",
    re.I,
)

# Chapman 2001 NegEx pre-negation (sentence-scope, before the mention).
_NEG_PRE = re.compile(
    r"\b(?:no evidence of|not on|is not on|isn't on|denies|denied|deny|"
    r"without|never|neither|nor|no|not)\b",
    re.I,
)
_NEG_PSEUDO = re.compile(
    r"\b(?:not only|no increase|no change|not necessarily|not certain)\b", re.I,
)
_FAMILY = re.compile(
    r"\b(?:mother|father|sister|brother|parent|mom|dad|family history|"
    r"family hx|maternal|paternal)\b",
    re.I,
)
# Uzuner 2010: discontinued / historical (not current).
_PRIOR = re.compile(
    r"\b(?:d/c'?d|dc'?d|d/ced|discontinued|withdrawn|weaned\s+off|tapered\s+off|"
    r"stopped|used to take|used to be on|previously (?:on|tried|took)|"
    r"was (?:on|taking|prescribed)|history of taking|no longer on|prior)\b",
    re.I,
)
# Suggested / planned — drop (not a current or prior fact).
_PLANNED = re.compile(
    r"\b(?:will start|will begin|going to start|plan(?:s|ned)? to start|"
    r"consider(?:ing)?(?: starting)?|recommend(?:ed)?(?: starting)?|"
    r"may start|might start|could start)\b",
    re.I,
)
_FAILED = re.compile(
    r"\b(?:failed|failure of|ineffective|not tolerated|lack of effect|"
    r"did not respond|no (?:benefit|response)|due to side effects|"
    r"because of (?:a )?rash|allergic to)\b",
    re.I,
)


def _is_eeg_study_token(name: str) -> bool:
    from rules.fields.medication import is_eeg_study_token
    return is_eeg_study_token(name)


def _canon(name: str) -> str:
    from rules.fields.medication import canonicalize_drug_name
    return canonicalize_drug_name(name)


@lru_cache(maxsize=1)
def _name_regex() -> re.Pattern:
    terms: list[str] = []
    seen: set[str] = set()
    blobs: list[str] = []
    for key, e in ASM_LEXICON.items():
        blobs.extend([key, e.get("label") or ""])
        blobs.extend(e.get("salts") or [])
        blobs.extend(e.get("brands") or [])
        blobs.extend(e.get("other_names") or [])
    blobs.extend(US_ASM_BRAND_ALIASES.keys())
    for raw in blobs:
        t = (raw or "").strip()
        if len(t) < 4:
            continue
        k = t.lower()
        if k in seen or _is_eeg_study_token(t):
            continue
        seen.add(k)
        terms.append(t)
    terms.sort(key=len, reverse=True)
    alt = "|".join(
        re.escape(t).replace(r"\ ", r"[\s\-]+") for t in terms
    )
    return re.compile(rf"(?i)\b(?:{alt})\b")


def _sentence(text: str, start: int, end: int) -> tuple[str, int, int]:
    lo = max(0, start - 240)
    hi = min(len(text), end + 240)
    left, right = text[lo:start], text[end:hi]
    cuts = [m.end() for m in _SENT_BREAK.finditer(left)]
    if cuts:
        left = left[cuts[-1]:]
    m = _SENT_BREAK.search(right)
    if m:
        right = right[:m.start()]
    return left + text[start:end] + right, len(left), len(left) + (end - start)


def _dose(text: str, start: int, end: int) -> Optional[str]:
    ctx = text[max(0, start - 15): min(len(text), end + 60)]
    m = _DOSE_RE.search(ctx)
    return re.sub(r"\s+", " ", m.group(0).strip()) if m else None


def _status(sentence: str, a: int, b: int) -> Optional[str]:
    """Return current | prior | failed, or None to drop (negated / planned / family)."""
    pre = sentence[:a]
    near = sentence[max(0, a - 80): min(len(sentence), b + 80)]
    if _NEG_PSEUDO.search(pre):
        pass
    elif _NEG_PRE.search(pre):
        return None
    if _FAMILY.search(pre) and not re.search(r"\b(?:patient|she|he|they)\b", pre, re.I):
        return None
    if _PLANNED.search(near):
        return None
    if _FAILED.search(near):
        return "failed"
    if _PRIOR.search(near):
        return "prior"
    return "current"


def _item(path: str, generic: str, quote: str, start: int, end: int,
          dose: Optional[str], temporal: str) -> FieldItem:
    val: dict = {"generic_name": generic}
    if dose:
        val["dose_text"] = dose
    return FieldItem(
        field_path=path,
        module="medication",
        ev={
            "value": val,
            "evidence_text": quote,
            "char_start": start,
            "char_end": end,
            "certainty": "definite",
            "temporal_status": temporal,
            "reader": DETECTOR,
        },
        multi=True,
    )


def iter_asm_spans(text: str):
    """(generic, start, end, sentence, mention_start_in_sent, mention_end_in_sent)."""
    if not (text or "").strip():
        return
    for m in _name_regex().finditer(text):
        surface = m.group(0)
        if _is_eeg_study_token(surface):
            continue
        generic = _canon(surface)
        if not generic:
            continue
        start, end = m.start(), m.end()
        sent, a, b = _sentence(text, start, end)
        yield generic, start, end, sent, a, b


def extract_ctakes_meds(text: str) -> list[FieldItem]:
    """ASM mentions in ``text`` as LEO medication FieldItems."""
    if not (text or "").strip():
        return []
    out: list[FieldItem] = []
    seen: set[tuple[str, str]] = set()
    for generic, start, end, sent, a, b in iter_asm_spans(text):
        status = _status(sent, a, b)
        if status is None:
            continue
        dose = _dose(text, start, end)
        quote = text[start:end]
        if status == "failed":
            path, temporal = "medication.failed_asms", "historical"
        elif status == "prior":
            path, temporal = "medication.prior_asms", "historical"
        else:
            role, _rule = drug_role(text, start, end)
            if role == "acute":
                path, temporal = "medication.acute_administration", "current"
            elif role == "rescue":
                path, temporal = "medication.rescue_medication", "current"
            else:
                path, temporal = "medication.current_asms", "current"
        key = (path, generic)
        if key in seen:
            continue
        seen.add(key)
        out.append(_item(path, generic, quote, start, end, dose, temporal))
    return out


__all__ = ["DETECTOR", "extract_ctakes_meds", "iter_asm_spans"]
