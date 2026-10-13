"""Current stated seizure-frequency sidecar (Xie *task*, not Xie weights).

Independent of ``rules.fields.seizure_frequency`` (ExECT JAPE port) and of L1C.
Reads only the current stated rate: count_min / count_max / period and
seizure_free. Skips historical and hypothetical sentences. Does not dump
strings into E.

Detector name: ``freq``. Path: ``clinical_seizure.seizure_frequency``.
"""

from __future__ import annotations

import re
from typing import Optional

from services.chain_llm import FieldItem
from services.ext_detectors.span import (
    CURRENT,
    HYPO,
    family_only,
    is_current_cued,
    is_historical,
    pre_negated,
    sentence_window,
    skip_mention,
)

DETECTOR = "freq"
PATH = "clinical_seizure.seizure_frequency"

_UNIT_MAP = {
    "day": "day", "days": "day", "daily": "day",
    "week": "week", "weeks": "week", "weekly": "week",
    "month": "month", "months": "month", "monthly": "month",
    "year": "year", "years": "year", "yearly": "year", "annually": "year",
}
_WORDS = {
    "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0,
    "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0, "ten": 10.0,
    "once": 1.0, "twice": 2.0, "thrice": 3.0,
}
_NUM = r"(?P<n>\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|once|twice)"
_NUM2 = r"(?P<n2>\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|twice)"
_UNIT = r"(?P<unit>day|days|week|weeks|month|months|year|years|daily|weekly|monthly|yearly|annually)"
_SEIZ = r"(?:seizures?|episodes?|events?|attacks?|fits?|spells?)?"
_APPROX = r"(?:(?:about|around|approximately|approx|roughly|~)\s+)?"

# Stated rate: "about 2 per month", "2-3 seizures a week", "once a day".
_RATE = re.compile(
    rf"{_APPROX}{_NUM}\s*(?:[-–—]|to)\s*{_NUM2}?"
    rf"(?:\s+{_SEIZ})?\s*(?:per|a|/|every|each)\s+{_UNIT}\b",
    re.I,
)
_RATE_SINGLE = re.compile(
    rf"{_APPROX}{_NUM}(?:\s+{_SEIZ})?\s*(?:per|a|/|every|each)\s+{_UNIT}\b",
    re.I,
)
_ONCE = re.compile(
    rf"\b(?P<n>once|twice|thrice)\s+(?:a|per|every|each)\s+{_UNIT}\b",
    re.I,
)
_FREE = re.compile(
    r"\b(?:currently\s+)?(?:remains?\s+)?seizure[- ]free|"
    r"\bno\s+(?:further\s+)?seizures?\s+since|"
    r"\bhas\s+been\s+seizure[- ]free|"
    r"\bfree\s+of\s+seizures?\b",
    re.I,
)


def _to_num(tok: str) -> Optional[float]:
    t = tok.strip().lower()
    if t in _WORDS:
        return _WORDS[t]
    try:
        return float(t)
    except ValueError:
        return None


def _period(unit: str) -> str:
    return _UNIT_MAP.get(unit.strip().lower(), "unspecified")


def _item(value: dict, quote: str, start: int, end: int) -> FieldItem:
    return FieldItem(
        field_path=PATH,
        module="clinical_seizure",
        ev={
            "value": value,
            "evidence_text": quote,
            "char_start": start,
            "char_end": end,
            "certainty": "definite",
            "temporal_status": "current",
            "reader": DETECTOR,
        },
        multi=False,
    )


def _rate_value(n: float, n2: Optional[float], period: str, quote: str) -> dict:
    hi = n2 if n2 is not None else n
    lo, hi = (n, hi) if n <= hi else (hi, n)
    return {
        "raw_text": quote,
        "period": period,
        "count_min": lo,
        "count_max": hi,
        "seizure_free": lo == 0.0 and hi == 0.0,
    }


def extract_freq(text: str) -> list[FieldItem]:
    """One current stated frequency, or empty."""
    if not (text or "").strip():
        return []
    cands: list[tuple[int, bool, bool, FieldItem]] = []
    # (start, current_cued, historical, item)

    def consider(m: re.Match, value: dict) -> None:
        start, end = m.start(), m.end()
        sent, a, _b = sentence_window(text, start, end)
        if skip_mention(sent, a):
            return
        hist = is_historical(sent)
        if hist:
            return
        quote = re.sub(r"\s+", " ", text[start:end].strip())
        value = {**value, "raw_text": quote}
        cands.append((start, is_current_cued(sent), hist, _item(value, quote, start, end)))

    for m in _FREE.finditer(text):
        start, end = m.start(), m.end()
        sent, a, _b = sentence_window(text, start, end)
        if family_only(sent, a):
            continue
        if HYPO.search(sent) and not CURRENT.search(sent):
            continue
        if is_historical(sent):
            continue
        if pre_negated(sent, a) and "since" not in text[start:end].lower():
            continue
        quote = re.sub(r"\s+", " ", text[start:end].strip())
        val = {
            "raw_text": quote,
            "period": "unspecified",
            "count_min": None,
            "count_max": None,
            "seizure_free": True,
        }
        cands.append((start, is_current_cued(sent), False, _item(val, quote, start, end)))

    for pat in (_RATE, _RATE_SINGLE, _ONCE):
        for m in pat.finditer(text):
            n = _to_num(m.group("n"))
            if n is None:
                continue
            n2 = None
            if "n2" in m.groupdict() and m.group("n2"):
                n2 = _to_num(m.group("n2"))
            period = _period(m.group("unit"))
            quote = re.sub(r"\s+", " ", m.group(0).strip())
            consider(m, _rate_value(n, n2, period, quote))

    if not cands:
        return []
    cued = [c for c in cands if c[1]]
    pool = cued or cands
    # Last current statement in the note wins (clinic letter "now").
    _start, _cued, _hist, item = max(pool, key=lambda c: c[0])
    return [item]


__all__ = ["DETECTOR", "PATH", "extract_freq"]
