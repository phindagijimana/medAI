"""Sentence window and Chapman NegEx for extra detectors.

Separate path from E's medspaCy ConText. Shared by freq / stated-type / hs
sidecars so those files do not import ``rules.fields``.
"""

from __future__ import annotations

import re

_SENT_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])|\n+")

# Chapman 2001 NegEx pre-negation (sentence-scope, before the mention).
NEG_PRE = re.compile(
    r"\b(?:no evidence of|not on|is not on|isn't on|denies|denied|deny|"
    r"without|never|neither|nor|no|not)\b",
    re.I,
)
NEG_PSEUDO = re.compile(
    r"\b(?:not only|no increase|no change|not necessarily|not certain|"
    r"no longer seizure[- ]free)\b",
    re.I,
)
FAMILY = re.compile(
    r"\b(?:mother|father|sister|brother|parent|mom|dad|family history|"
    r"family hx|maternal|paternal)\b",
    re.I,
)
HYPO = re.compile(
    r"\b(?:if (?:he|she|they|the patient)|were to have|would have|"
    r"should (?:he|she) have|in case of)\b",
    re.I,
)
HISTORICAL = re.compile(
    r"\b(?:used to|previously|in childhood|as a child|years ago|"
    r"formerly|history of having|at age \d+|in \d{4})\b",
    re.I,
)
CURRENT = re.compile(
    r"\b(?:currently|now|at present|these days|today|this visit|"
    r"at this time|remains|is now)\b",
    re.I,
)


def sentence_window(text: str, start: int, end: int) -> tuple[str, int, int]:
    """(sentence, mention_start_in_sentence, mention_end_in_sentence)."""
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


def pre_negated(sentence: str, mention_start: int) -> bool:
    pre = sentence[:mention_start]
    if NEG_PSEUDO.search(pre):
        return False
    return bool(NEG_PRE.search(pre))


def family_only(sentence: str, mention_start: int) -> bool:
    pre = sentence[:mention_start]
    if not FAMILY.search(pre):
        return False
    return not re.search(r"\b(?:patient|she|he|they)\b", pre, re.I)


def skip_mention(sentence: str, mention_start: int) -> bool:
    """True when the mention is not a current patient fact."""
    if pre_negated(sentence, mention_start):
        return True
    if family_only(sentence, mention_start):
        return True
    if HYPO.search(sentence) and not CURRENT.search(sentence):
        return True
    return False


def is_historical(sentence: str) -> bool:
    return bool(HISTORICAL.search(sentence)) and not CURRENT.search(sentence)


def is_current_cued(sentence: str) -> bool:
    return bool(CURRENT.search(sentence))


__all__ = [
    "CURRENT",
    "FAMILY",
    "HISTORICAL",
    "HYPO",
    "NEG_PRE",
    "family_only",
    "is_current_cued",
    "is_historical",
    "pre_negated",
    "sentence_window",
    "skip_mention",
]
