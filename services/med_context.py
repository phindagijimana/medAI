"""Is a drug mention a one-off acute administration rather than part of the regimen?

Emergency-department, EMU and inpatient notes record drugs *given* during the encounter
("Ativan (lorazepam) 4 mg IV was administered at 18:51", "Keppra 4,500 mg IV load started").
Those are events, not the patient's current anti-seizure regimen, and counting them as current
ASMs overstates the regimen (audit: 9 of 11 wrong specialist-only drug claims on the synthetic
notes).  Home rescue medication ("buccal midazolam 10 mg PRN") is part of the regimen and is
*not* matched here: it is non-parenteral and has no administration time.

The rule is deliberately narrow, because a false match removes a true current drug from the
auto-accepted list.  A mention is acute when, within its own sentence or line and within 80
characters of the mention (so a parenteral drug elsewhere in the sentence does not mark the others),

* it is a *loading dose or bolus* ("load", "loading dose", "bolus", "stat dose"), or
* a parenteral route (IV, IM, IO and spelled-out forms) appears with **no schedule**
  (q8h, BID, daily ... mark continued inpatient therapy, which stays current), or
* an administration verb ("administered", "given", "gave", "received") appears with a clock
  time ("at 18:51", "1851 hrs").

Pure function; no model, no I/O.  Used by ``services.chain_pipeline``.
"""

from __future__ import annotations

import re
from typing import Optional

_PARENTERAL = re.compile(
    r"\b(?:IV|I\.V\.|IM|I\.M\.|IO|intravenous(?:ly)?|intramuscular(?:ly)?|intraosseous)\b", re.I)
_SCHEDULE = re.compile(
    r"\b(?:q\s?\d{1,2}\s?h|q\.?\s?\d{1,2}\s?hours?|every\s+\d{1,2}\s+hours?|b\.?i\.?d\.?|t\.?i\.?d\.?|"
    r"q\.?i\.?d\.?|daily|q\.?d\.?|q\.?h\.?s\.?|nightly|twice\s+(?:daily|a\s+day)|"
    r"three\s+times\s+(?:daily|a\s+day)|maintenance|scheduled)\b", re.I)
_LOAD = re.compile(r"\b(?:loading\s+dose|loaded|load(?:ing)?|bolus|stat\s+dose|stat)\b", re.I)
_ADMIN_VERB = re.compile(r"\b(?:administered|given|gave|received|was\s+started|were\s+started)\b", re.I)
_CLOCK = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b|\b(?:[01]\d|2[0-3])[0-5]\d\s*(?:hrs?|hours)\b", re.I)

_SENT_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])|\n+")
_MAX_SIDE = 220
_NEAR = 80          # a cue must lie within this many characters of the drug mention


def _sentence(text: str, start: int, end: int) -> tuple[str, int, int]:
    """The sentence or line containing text[start:end], capped on each side, and the
    mention's offsets inside it."""
    lo = max(0, start - _MAX_SIDE)
    hi = min(len(text), end + _MAX_SIDE)
    left = text[lo:start]
    right = text[end:hi]
    cut = [m.end() for m in _SENT_BREAK.finditer(left)]
    if cut:
        left = left[cut[-1]:]
    m = _SENT_BREAK.search(right)
    if m:
        right = right[:m.start()]
    return left + text[start:end] + right, len(left), len(left) + (end - start)


def acute_administration(text: str, start: int, end: int) -> Optional[str]:
    """Name of the rule that marks the mention at text[start:end] as acute, else None."""
    if not text or start is None or end is None or not (0 <= start < end <= len(text)):
        return None
    sent, a, b = _sentence(text, start, end)
    s = sent[max(0, a - _NEAR):b + _NEAR]
    if _LOAD.search(s):
        return "load_or_bolus"
    if _PARENTERAL.search(s) and not _SCHEDULE.search(s):
        return "parenteral_unscheduled"
    if _ADMIN_VERB.search(s) and _CLOCK.search(s):
        return "administered_at_time"
    return None


# ── Rescue role ─────────────────────────────────────────────────────────────
#
# A rescue (seizure-emergency or acute-cluster) drug is taken as needed; it does not replace the
# daily regimen (NINDS epilepsy CDE workshop 2011; Epilepsy Foundation; Pina-Garza et al. 2024,
# see docs/REFERENCES.md).  ExECT keeps rescue drugs as prescriptions with Frequency "As Required".
# The cue must belong to *this* drug: it is read only after the mention, up to the next drug name,
# and in a short stretch before it that holds no other drug name.

_RESCUE_WORD = re.compile(
    r"\b(?:rescue|abortive|seizure\s+action\s+plan|emergency\s+(?:med\w*|plan|use)|"
    r"acute\s+(?:cluster|repetitive)\s+\w+|seizure\s+clusters?|clusters?\s+of\s+seizures?|for\s+clusters?)\b", re.I)
_RESCUE_PRN = re.compile(
    r"\b(?:p\.?\s?r\.?\s?n\.?|as[\s-]+needed|as[\s-]+required|when[\s-]+needed|if[\s-]+needed)\b", re.I)
_RESCUE_IF_SEIZURE = re.compile(
    r"\b(?:if|for|during|when)\s+(?:a\s+|the\s+|any\s+)?(?:\w+\s+){0,3}(?:seizures?|convulsions?)\b|"
    r"\bseizures?\s+(?:lasting|lasts|that\s+last|longer\s+than|exceeding)\b", re.I)
_RESCUE_ROUTE = re.compile(
    r"\b(?:intranasal(?:ly)?|nasal(?:\s+spray)?|buccal(?:ly)?|rectal(?:ly)?|per\s+rectum|PR|"
    r"diastat|valtoco|nayzilam|buccolam|epistatus)\b", re.I)
_TITRATE_AS_NEEDED = re.compile(
    r"(?:titrat\w*|increas\w*|adjust\w*|wean\w*|taper\w*|reduc\w*|decreas\w*)\W+(?:\w+\W+){0,4}$", re.I)

_FWD = 80      # a cue after the mention counts up to this distance
_BACK = 30     # a cue before the mention counts up to this distance
_DRUG_NAMES: Optional[re.Pattern] = None


def _drug_name_re() -> re.Pattern:
    global _DRUG_NAMES
    if _DRUG_NAMES is None:
        from rules.asm_lexicon import ASM_LEXICON
        names: set[str] = set()
        for v in ASM_LEXICON.values():
            for n in [v.get("label")] + list(v.get("salts") or []) + list(v.get("brands") or []) \
                    + list(v.get("other_names") or []):
                if n and len(n) > 3:
                    names.add(n.lower())
        alt = "|".join(sorted((re.escape(n) for n in names), key=len, reverse=True))
        _DRUG_NAMES = re.compile(r"\b(?:" + alt + r")\b", re.I)
    return _DRUG_NAMES


_ALIAS_GAP = re.compile(r"[\s(/,\-]*")


def _own_context(text: str, start: int, end: int) -> tuple[str, str]:
    """(before, after): the text around the mention that belongs to this drug alone.

    Another drug name bounds the context unless it sits right beside the mention with only
    punctuation between ("Valtoco (diazepam nasal)": a brand and its generic are one drug).
    """
    sent, a, b = _sentence(text, start, end)
    names = _drug_name_re()
    after = sent[b:b + _FWD]
    for m in names.finditer(after):
        if _ALIAS_GAP.fullmatch(after[:m.start()]):
            continue
        after = after[:m.start()]
        break
    before = sent[max(0, a - _BACK):a]
    prev = [m for m in names.finditer(before) if not _ALIAS_GAP.fullmatch(before[m.end():])]
    if prev:
        before = before[prev[-1].end():]
    cut = max(before.rfind(","), before.rfind(";"))
    if cut >= 0:
        before = before[cut + 1:]
    return before, after


def rescue_role(text: str, start: int, end: int) -> Optional[str]:
    """Name of the rule that marks the mention as a rescue (as-needed) drug, else None."""
    if not text or start is None or end is None or not (0 <= start < end <= len(text)):
        return None
    before, after = _own_context(text, start, end)
    near = before + " " + after
    if _RESCUE_WORD.search(near):
        return "rescue_word"
    if _RESCUE_IF_SEIZURE.search(after):          # a clause before the drug belongs to the previous one
        return "if_seizure"
    for m in _RESCUE_PRN.finditer(near):
        if not _TITRATE_AS_NEEDED.search(near[:m.start()]):
            return "prn"
    if _RESCUE_ROUTE.search(near) and not _SCHEDULE.search(after):
        return "rescue_route_or_product"
    return None


def drug_role(text: str, start: int, end: int) -> tuple[str, Optional[str]]:
    """("acute" | "rescue" | "maintenance", rule name).

    Order: a loading dose or a time-stamped administration is acute even if the drug is also
    prescribed as needed; an as-needed order is rescue even when given IV (a standing inpatient
    order, not a one-off dose); an unscheduled parenteral dose with no such cue is acute.
    """
    acute = acute_administration(text, start, end)
    if acute in ("load_or_bolus", "administered_at_time"):
        return "acute", acute
    rescue = rescue_role(text, start, end)
    if rescue:
        return "rescue", rescue
    if acute:
        return "acute", acute
    return "maintenance", None


__all__ = ["acute_administration", "rescue_role", "drug_role"]

