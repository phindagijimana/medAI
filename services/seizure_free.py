"""Seizure freedom and date of the last seizure, as their own LEO fields.

``seizure_free`` is read off each reader's current seizure frequency (seizure free, or counts of zero, is true;
a positive count is false) and fused on its own, so the readers can agree that a patient is not seizure free while
disagreeing on the exact rate.  Seizure freedom and the date of the last seizure are the outcomes US epilepsy
outcome studies extract (Xie et al., Epilepsia 2023; Ojemann et al., J Healthc Inform Res 2025).

``date_of_last_seizure`` is a rules reader of explicit dates only ("last event July 2016", "no seizures since
Christmas 2015").  Durations ("seizure free for 7 months") are not turned into dates, because that needs the visit
date and the pipeline's default document date is a placeholder.  All-numeric dates keep only the year unless the
day/month order is unambiguous (UK letters write 03/06/2007, US notes 06/03/2007).
"""

from __future__ import annotations

import re
from typing import Any, Optional

FREQUENCY_PATH = "clinical_seizure.seizure_frequency"
OTHER_FREQUENCIES_PATH = "clinical_seizure.other_seizure_frequencies"
SEIZURE_FREE_PATH = "clinical_seizure.seizure_free"
LAST_SEIZURE_PATH = "clinical_seizure.date_of_last_seizure"

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12, "christmas": 12,
}
_MONTH_RX = (r"(?:christmas(?:\s+(?:day|eve))?|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?"
             r"|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_DATE_RX = (r"(?P<date>(?:(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?)?(?P<month>" + _MONTH_RX +
            r")\.?,?\s+(?P<year>(?:19|20)\d\d)"
            r"|(?P<n1>\d{1,2})[/.](?P<n2>\d{1,2})[/.](?P<nyear>(?:19|20)\d\d)"
            r"|(?P<yonly>(?:19|20)\d\d))(?!\d)")
_EVENT = r"(?:seizures?|events?|attacks?|convulsions?|absences?|fits?|episodes?|jerks?|one)"
_LAST_RX = re.compile(
    r"\b(?:last|most\s+recent|latest)\s+(?:\w+\s+){0,4}?" + _EVENT + r"\b[^.\n]{0,30}?" + _DATE_RX,
    re.IGNORECASE)
_SINCE_RX = re.compile(
    r"(?:\b(?:no|not\s+had|n't\s+had|free\s+of|without)\b[^.\n]{0,50}?\b" + _EVENT + r"\b[^.\n]{0,30}?"
    r"|\bseizure[- ]?free\s+)since\s+(?:(?:about|around|approximately)\s+)?" + _DATE_RX,
    re.IGNORECASE)


def seizure_free_value(freq: Any) -> Optional[bool]:
    """True / False / None from one seizure-frequency value."""
    if not isinstance(freq, dict):
        return None
    lo, hi = freq.get("count_min"), freq.get("count_max")
    counts = [float(x) for x in (lo, hi) if isinstance(x, (int, float)) and not isinstance(x, bool)]
    if any(c > 0 for c in counts):
        return False
    if freq.get("seizure_free") is True or (counts and all(c == 0 for c in counts)):
        return True
    return None


def _date_value(m: re.Match) -> Optional[str]:
    if m.group("month"):
        mon = _MONTHS.get(m.group("month").lower()[:3]) or _MONTHS.get(m.group("month").lower().split()[0])
        day = m.group("day")
        y = m.group("year")
        if mon is None:
            return y
        if day and 1 <= int(day) <= 31:
            return f"{y}-{mon:02d}-{int(day):02d}"
        return f"{y}-{mon:02d}"
    if m.group("nyear"):
        a, b, y = int(m.group("n1")), int(m.group("n2")), m.group("nyear")
        if a > 12 >= b >= 1:
            return f"{y}-{b:02d}-{a:02d}"
        if b > 12 >= a >= 1:
            return f"{y}-{a:02d}-{b:02d}"
        return y
    return m.group("yonly")


def last_seizure_dates(text: str) -> list[tuple[str, int, int]]:
    """Every explicit last-seizure date in ``text``: (ISO value at the stated precision, span start, span end)."""
    out: list[tuple[str, int, int]] = []
    seen: set[tuple[int, int]] = set()
    for rx in (_LAST_RX, _SINCE_RX):
        for m in rx.finditer(text or ""):
            if (m.start(), m.end()) in seen:
                continue
            seen.add((m.start(), m.end()))
            v = _date_value(m)
            if v:
                out.append((v, m.start(), m.end()))
    return sorted(out, key=lambda x: x[1])


def last_seizure_date(text: str) -> Optional[tuple[str, int, int]]:
    """The latest explicit last-seizure date in ``text`` (a note can give one per seizure type)."""
    found = last_seizure_dates(text)
    return max(found, key=lambda x: x[0]) if found else None


def date_matches(pred: Optional[str], gold: Optional[str]) -> bool:
    """Same date at the gold's precision (``2016`` matches ``2016-07``; ``2016-07`` needs year and month)."""
    if not pred or not gold:
        return False
    g, p = gold.split("-"), pred.split("-")
    k = min(len(g), 2)
    return len(p) >= k and p[:k] == g[:k]


def seizure_free_items(items: list) -> list:
    """One ``seizure_free`` item from the reader's current frequency item, same evidence span.

    A positive count among the other seizure types' frequencies makes the patient not seizure free.
    """
    from services.chain_llm import FieldItem
    main = next((it for it in items if it.field_path == FREQUENCY_PATH and not it.multi), None)
    if main is None:
        return []
    val = seizure_free_value(main.ev.get("value"))
    if val is True and any(seizure_free_value(it.ev.get("value")) is False
                           for it in items if it.field_path == OTHER_FREQUENCIES_PATH):
        val = False
    if val is None:
        return []
    return [FieldItem(SEIZURE_FREE_PATH, main.module, {**main.ev, "value": val}, False)]


def last_seizure_items(text: str) -> list:
    """The rules reader's ``date_of_last_seizure`` item (explicit dates only)."""
    from services.chain_llm import FieldItem
    hit = last_seizure_date(text)
    if hit is None:
        return []
    v, s, e = hit
    return [FieldItem(LAST_SEIZURE_PATH, "clinical_seizure", {
        "value": v, "certainty": "definite", "temporal_status": "past",
        "evidence_text": text[s:e], "char_start": s, "char_end": e}, False)]


__all__ = ["SEIZURE_FREE_PATH", "LAST_SEIZURE_PATH", "seizure_free_value", "last_seizure_dates",
           "last_seizure_date", "date_matches", "seizure_free_items", "last_seizure_items"]
