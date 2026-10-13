"""Psychogenic non-epileptic / dissociative / functional seizures (PNES) as a flag on the note.

Hamid et al. (Epilepsy Behav 2013; ``writing/further_LEO.md`` U6) built an NLP filter to keep PNES out of
EHR-based epilepsy cohorts.  LEO does not exclude the note; it says what the note documents:

* ``pnes_only``          PNES is stated and no epilepsy is stated (or epilepsy is denied)
* ``pnes_and_epilepsy``  both are stated (dual diagnosis)
* ``pnes_possible``      PNES is raised as a possibility only ("I wonder if these could be non-epileptic")

"Likely" / "probable" PNES is stated with certainty ``probable``, not ``pnes_possible``.  A negated mention
("no evidence of dissociative seizures") is ignored.  Routing that uses the flag is in
``services.chain_pipeline`` (``pnes_check``).
"""

from __future__ import annotations

import re
from typing import Optional

PNES_PATH = "clinical_seizure.pnes_status"

_PNES_RX = re.compile(
    r"\b(?:psychogenic\s+non[- ]?epileptic(?:\s+(?:seizures?|attacks?|attack\s+disorder|events?|episodes?))?"
    r"|non[- ]?epileptic\s+(?:psychogenic\s+)?(?:seizures?|attacks?|attack\s+disorder|events?|episodes?)"
    r"|non[- ]?epileptic\s+in\s+nature"
    r"|non\s+epileptic\s+(?:rather\s+than|seizures?|attacks?)"
    r"|dissociative\s+(?:\(non[- ]?epileptic\)\s+)?(?:seizures?|attacks?|episodes?|events?|convulsions?)"
    r"|functional\s+(?:seizures?|non[- ]?epileptic\s+\w+|neurological\s+disorder\s+with\s+seizures)"
    r"|pseudo[- ]?seizures?|PNES|NEAD)\b",
    re.IGNORECASE)
_SENT_END = re.compile(r"[.!?\n]")
_HEDGE = re.compile(
    r"\b(?:possib\w*|wonder|could\s+(?:be|represent)|may\s+(?:be|also\s+be|represent)|might|consider\w*|query|"
    r"\?|rule\s+out|exclude|versus|vs\.?|whether|keep\s+in\s+mind|differential|cannot\s+exclude|suspect\w*)\b|\?",
    re.IGNORECASE)
_PROBABLE = re.compile(r"\b(?:probabl[ey]|likely|most\s+likely|suggestive\s+of|consistent\s+with|in\s+keeping\s+with)\b",
                       re.IGNORECASE)
_NEGATED = re.compile(r"\b(?:no\s+(?:evidence|suggestion|features?)\s+of|not\s+(?:consistent\s+with|suggestive\s+of)|"
                      r"rather\s+than|ruled\s+out|unlikely\s+to\s+be|not)\s+(?:\w+\s+){0,3}$", re.IGNORECASE)
_EPILEPSY_RX = re.compile(
    r"\bepilep(?:sy|sies)\b(?!\s+(?:service|clinic|nurse|team|unit|specialist|centre|center|department|society|action))"
    r"|\b(?<!non[- ])(?<!non\s)epileptic\s+(?:and\s+non[- ]?epileptic\s+)?(?:seizures?|events?|attacks?)\b"
    r"|\b(?:complex|simple)\s+partial\s+seizures?\b|\bsecondar(?:y|ily)\s+generali[sz]ed\b"
    r"|\bfocal\s+(?:aware|impaired\s+awareness|onset|to\s+bilateral)\b|\bjuvenile\s+myoclonic\b",
    re.IGNORECASE)
_NEGATION_WORD = re.compile(r"\b(?:not|no|never|doesn't|don't|isn't)\b", re.IGNORECASE)
_EPILEPSY_NEG = re.compile(
    r"(?:\bnot?\s+(?:think\s+(?:that\s+)?(?:these|this|they|it)\s+(?:are|is|were|was)\s+|evidence\s+of\s+|"
    r"have\s+|has\s+)|\bnon[- ]?|\brather\s+than\s+|\bpeople\s+with\s+|\bwhether\s+|\bor\s+)(?:\w+\s+){0,2}$",
    re.IGNORECASE)


def _sentence(text: str, start: int, end: int) -> tuple[int, int]:
    lo = 0
    for m in _SENT_END.finditer(text, 0, start):
        lo = m.end()
    m = _SENT_END.search(text, end)
    return lo, (m.start() if m else len(text))


def _epilepsy_stated(text: str) -> bool:
    for m in _EPILEPSY_RX.finditer(text):
        lo, hi = _sentence(text, m.start(), m.end())
        left = text[lo:m.start()]
        sent = text[lo:hi]
        if _EPILEPSY_NEG.search(left[-60:]) or _HEDGE.search(sent):
            continue
        if _PNES_RX.search(sent) and _NEGATION_WORD.search(sent) and "and non" not in m.group(0).lower():
            continue
        return True
    return False


def pnes_status(text: str) -> Optional[tuple[str, str, int, int]]:
    """(value, certainty, span start, span end) for the most definite PNES mention, or None."""
    best = None   # (rank, certainty, start, end); rank 2 stated, 1 probable, 0 possible
    for m in _PNES_RX.finditer(text or ""):
        lo, hi = _sentence(text, m.start(), m.end())
        left = text[lo:m.start()]
        if _NEGATED.search(left[-50:]) and not re.search(r"non\s+epileptic\s+rather\s+than", m.group(0), re.I):
            continue
        sent = text[lo:hi]
        if _HEDGE.search(sent) or re.search(r"rather\s+than", m.group(0), re.I):
            rank, cert = 0, "possible"
        elif _PROBABLE.search(left[-40:]):
            rank, cert = 1, "probable"
        else:
            rank, cert = 2, "definite"
        if best is None or rank > best[0]:
            best = (rank, cert, m.start(), m.end())
    if best is None:
        return None
    rank, cert, s, e = best
    if rank == 0:
        value = "pnes_possible"
    else:
        value = "pnes_and_epilepsy" if _epilepsy_stated(text) else "pnes_only"
    return value, cert, s, e


def pnes_items(text: str) -> list:
    """The rules reader's ``pnes_status`` item."""
    from services.chain_llm import FieldItem
    hit = pnes_status(text)
    if hit is None:
        return []
    value, cert, s, e = hit
    return [FieldItem(PNES_PATH, "clinical_seizure", {
        "value": value, "certainty": cert, "temporal_status": "current",
        "evidence_text": text[s:e], "char_start": s, "char_end": e}, False)]


__all__ = ["PNES_PATH", "pnes_status", "pnes_items"]
