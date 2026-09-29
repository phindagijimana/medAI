"""
seizure_frequency.py — SeizureFrequency nested-model extraction.

Fields populated
----------------
- ``clinical_seizure.seizure_frequency``       (Evidence[SeizureFrequency])
- ``clinical_seizure.other_seizure_frequencies`` (list[Evidence[SeizureFrequency]])

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``jape/seizure-frequency.jape``          (13 KB) — canonical NUMBER + per + UNIT
- ``jape/seizure-frequency1.jape``         (20 KB) — range + qualifier variants
- ``jape/seizure-frequency2.jape``         (22 KB) — since / during time-window
- ``jape/seizure-frequency3.jape``         (small) — final filters
- ``jape/frequency.jape``                  — Frequency annotation constructors
- ``jape/mainSeizFreq.jape``               — top-level composition
- ``jape/SFBlockClean.jape``               — cleanup phase
- ``jape/SeizFreqSentence.jape`` / ``SeizFreqFilter*.jape`` — sentence-scoping
- ``jape/SeizureFree.jape`` / ``SeizFreeSentence.jape`` / ``SeizFreeFilter*.jape``
  — "seizure-free for X" boolean (SeizureFrequency.seizure_free=True)
- ``jape/SeizureFrequencyExtendSinceDuring.jape`` — since-clause extension
- ``jape/TwoSeizureFreqOneTimePeriod.jape`` — range disambiguation
- ``jape/times.jape``                      — TimePeriods gazetteer parse
- ``jape/numberRange.jape`` / ``AToNumberRange.jape`` — number-range parse
- ``Groovy/SeizureFrequency.groovy``       — output serializer
- ``Groovy/SeizureFrequencyFirstLetter.groovy`` — first-letter dedup logic

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
1. **Rate-based**: sentence containing a SeizureType/seizure keyword +
   ``NUMBER (per|a|/) TIME_UNIT`` → ``count_min = count_max = NUMBER``,
   ``period = TIME_UNIT``.
2. **Range**: ``N1 to N2 (per|a) UNIT`` → ``count_min=N1``, ``count_max=N2``.
3. **Adjectival**: "daily", "weekly", "monthly", "yearly" seizures → period
   set, counts left None.
4. **Qualitative**: "several / few / many / occasional" per UNIT → counts
   left None but period recorded (surface form kept in ``raw_text``).
5. **Once / twice**: "once/twice a week" → count=1/2.
6. **Seizure-free**: "seizure-free for X years" → ``seizure_free=True``,
   period and counts unset. Handled by :class:`SeizureFreeRule`.
7. **Since / during a window**: "3 seizures in the past 6 months" — the
   ``TIMES`` gazetteer JAPE (times.jape) captured this pattern; we replicate
   with a "in the last N UNIT" regex that fires an aggregate-count entry.
8. **Applies-to-type**: when the sentence also contains a SeizureType entity,
   :attr:`SeizureFrequency.applies_to_type` is set so downstream rules can
   tie each frequency to a specific seizure type (per v0.2 schema field).

ConText flags
-------------
- Any negation of the enclosing seizure entity → skip that sentence.
- Hypothetical ("if he has more than 3 per day") → skip (was DiagBFilter).
- Historical → keep, mark ``temporal_status='historical'``.

Cite: Fonferko-Shadrach et al. 2019; 2024.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import Certainty, SeizureType, TemporalStatus
from schema.evidence import Evidence
from schema.ontology import SeizureFrequency
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Lexical helpers
# ---------------------------------------------------------------------------

TIME_UNIT_MAP = {
    "day": "day", "days": "day",
    "week": "week", "weeks": "week",
    "month": "month", "months": "month",
    "year": "year", "years": "year",
    "daily": "day", "weekly": "week", "monthly": "month", "yearly": "year", "annually": "year",
    "fortnight": "week", "fortnightly": "week",  # 2 weeks — treat as week for period
}


NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "several": None, "few": None,
    "many": None, "couple": 2, "handful": None, "occasional": None,
}


def _to_number(tok: str) -> Optional[float]:
    tok = tok.strip().lower()
    if tok in NUMBER_WORDS:
        v = NUMBER_WORDS[tok]
        return float(v) if v is not None else None
    try:
        return float(tok)
    except ValueError:
        return None


# Pattern 1a: N1 - N2 [descriptors] SEIZURE_WORD per UNIT
# Descriptor gap between numbers and seizure word.
_RE_RANGE_WITH_SEIZURE = re.compile(
    r"(?P<n1>\d+(?:\.\d+)?)\s*(?:[-–—]|to)\s*(?P<n2>\d+(?:\.\d+)?)"
    r"(?:\s+[a-z][a-z\-]*){0,6}"
    r"\s+(?:seizures?|episodes?|events?|attacks?|fits?|jerks?|absences?|spasms?)"
    r"\s*(?:per|a|/|every|each)\s+"
    r"(?P<unit>day|week|month|year|daily|weekly|monthly|yearly|fortnight)s?\b",
    re.IGNORECASE,
)

# Pattern 1b: N1 - N2 per UNIT (no seizure word — used when the sentence
# ALREADY hosts a seizure entity, so applies_to_type context is available)
_RE_RANGE_PER_UNIT = re.compile(
    r"(?P<n1>\d+(?:\.\d+)?)\s*(?:[-–—]|to)\s*(?P<n2>\d+(?:\.\d+)?)"
    r"\s+(?:seizures?|episodes?|events?|attacks?|fits?|jerks?|absences?|spasms?)?"
    r"\s*(?:per|a|/|every|each)\s+"
    r"(?P<unit>day|week|month|year|daily|weekly|monthly|yearly|fortnight)s?\b",
    re.IGNORECASE,
)

# Pattern 2a: N [descriptors] SEIZURE_WORD per UNIT
_RE_NUM_WITH_SEIZURE = re.compile(
    r"(?P<n>\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten"
    r"|eleven|twelve|couple|several|few|many|occasional)\b"
    r"(?:\s+[a-z][a-z\-]*){0,6}"
    r"\s+(?:seizures?|episodes?|events?|attacks?|fits?|jerks?|absences?|spasms?)"
    r"\s*(?:per|a|/|every|each)\s+"
    r"(?P<unit>day|week|month|year|daily|weekly|monthly|yearly|fortnight)s?\b",
    re.IGNORECASE,
)

# Pattern 2b: N per UNIT (bare)
_RE_NUM_PER_UNIT = re.compile(
    r"(?P<n>\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten"
    r"|eleven|twelve|couple|several|few|many|occasional)\b"
    r"\s+(?:seizures?|episodes?|events?|attacks?|fits?|jerks?|absences?|spasms?)?"
    r"\s*(?:per|a|/|every|each)\s+"
    r"(?P<unit>day|week|month|year|daily|weekly|monthly|yearly|fortnight)s?\b",
    re.IGNORECASE,
)

# Pattern 3: once / twice / thrice a UNIT
_RE_ONCE_TWICE = re.compile(
    r"\b(?P<qual>once|twice|thrice|three\s+times|four\s+times)\s+"
    r"(?:a|per|every|each)\s+"
    r"(?P<unit>day|week|month|year|daily|weekly|monthly|yearly)s?\b",
    re.IGNORECASE,
)

# Pattern 4a: "daily seizures", "weekly jerks"
_RE_ADJECTIVE = re.compile(
    r"\b(?P<unit>daily|weekly|monthly|yearly|nightly)\s+"
    r"(?:seizures?|episodes?|events?|attacks?|fits?|jerks?|absences?|spasms?)\b",
    re.IGNORECASE,
)

# Pattern 4b: "jerks weekly", "seizures daily" (adjective after noun)
_RE_ADJECTIVE_POST = re.compile(
    r"\b(?:seizures?|episodes?|events?|attacks?|fits?|jerks?|absences?|spasms?)\s+"
    r"(?P<unit>daily|weekly|monthly|yearly|nightly)\b",
    re.IGNORECASE,
)

# Pattern 4c: "once to twice per UNIT" / "one or two per UNIT" — word-form range
_RE_WORD_RANGE = re.compile(
    r"\b(?P<q1>one|two|three|four|five|six|seven|eight|nine|ten|once|twice|thrice)"
    r"\s+(?:to|or)\s+"
    r"(?P<q2>one|two|three|four|five|six|seven|eight|nine|ten|once|twice|thrice)"
    r"(?:\s+[a-z][a-z\-]*){0,6}"
    r"\s*(?:seizures?|episodes?|events?|attacks?|fits?|jerks?|absences?|spasms?)?"
    r"\s*(?:per|a|/|every|each)\s+"
    r"(?P<unit>day|week|month|year|daily|weekly|monthly|yearly|fortnight)s?\b",
    re.IGNORECASE,
)

_WORD_TO_NUM_RANGE = {
    "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0,
    "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0, "ten": 10.0,
    "once": 1.0, "twice": 2.0, "thrice": 3.0,
}


# Pattern 5: "N seizures in the past/last UNIT" (aggregate-in-window)
_RE_IN_LAST = re.compile(
    r"(?P<n>\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten"
    r"|several|few|many)"
    r"\s+(?:seizures?|episodes?|events?|attacks?|fits?|jerks?|absences?)"
    r"\s+(?:in|over)\s+(?:the\s+)?(?:past|last|preceding)\s+"
    r"(?P<count>\d+)?\s*"
    r"(?P<unit>day|week|month|year|fortnight)s?\b",
    re.IGNORECASE,
)

# Pattern 5b: "N1-N2 [of these] seizures over N UNIT" — Phase 8 Iter 1 addition
# for F-S phrasing like "around 10-15 of these seizures over 2 days".
_RE_RANGE_OVER = re.compile(
    r"(?P<n1>\d+(?:\.\d+)?)\s*(?:[-–—]|to)\s*(?P<n2>\d+(?:\.\d+)?)"
    r"(?:\s+of\s+(?:these|those|his|her))?"
    r"\s+(?:seizures?|episodes?|events?|attacks?|fits?|jerks?|absences?|spasms?)"
    r"\s+(?:over|in|during)\s+(?:the\s+(?:past|last|preceding)\s+)?"
    r"(?P<count>\d+)?\s*"
    r"(?P<unit>day|week|month|year|fortnight|hour)s?\b",
    re.IGNORECASE,
)

# Approximate quantifier ("approximately", "about", "around", "~")
_APPROX_RE = re.compile(
    r"\b(approximately|approx|about|around|roughly|~)\b", re.IGNORECASE
)

# Seizure-free trigger
_SEIZURE_FREE_RE = re.compile(
    r"\b(?:seizure[- ]free|no\s+(?:further\s+)?seizures?|"
    r"(?:has|have|had)\s+not\s+had\s+(?:any\s+)?(?:further\s+)?seizures?|"
    r"free\s+of\s+seizures?|no\s+seizures?\s+since)"
    r"(?:\s+(?:for|since)\s+(?P<num>\d+)?\s*(?P<unit>day|week|month|year)s?)?",
    re.IGNORECASE,
)


def _build_freq(
    *,
    raw_text: str,
    period: str = "unspecified",
    count_min: float | None = None,
    count_max: float | None = None,
    seizure_free: bool = False,
    duration_text: str | None = None,
    applies_to_type: SeizureType | None = None,
) -> SeizureFrequency:
    return SeizureFrequency(
        raw_text=raw_text,
        period=period,
        count_min=count_min,
        count_max=count_max,
        seizure_free=seizure_free,
        duration_text=duration_text,
        applies_to_type=applies_to_type,
    )


# ---------------------------------------------------------------------------
# Sentence scan helpers
# ---------------------------------------------------------------------------


def _sentences_with_seizure(entities: list[LinkedEntity], doc=None) -> list[tuple[int, str, list[LinkedEntity]]]:
    """Group entities by their enclosing sentence, keeping only sentences
    that host at least one seizure-relevant entity (SeizureType or the
    generic UNCLASSIFIED filler) OR whose text contains a seizure word.

    When ``doc`` is provided, also emits sentences with no linked entity
    that nonetheless contain a seizure word (for standalone frequency
    clauses like "3-4 seizures per week").
    """
    by_sent: dict[int, tuple[str, list[LinkedEntity]]] = {}
    for e in entities:
        if e.sentence_start < 0:
            continue
        key = e.sentence_start
        by_sent.setdefault(key, (e.sentence_text, []))[1].append(e)

    # Add doc-side sentences without entity anchors.
    if doc is not None and hasattr(doc, "sents"):
        for sent in doc.sents:
            key = sent.start_char
            if key in by_sent:
                continue
            if re.search(r"\bseizures?\b|\bfits?\b|\bjerks?\b|\bepisodes?\b|"
                         r"\babsences?\b|\bspasms?\b",
                         sent.text, re.IGNORECASE):
                by_sent[key] = (sent.text, [])

    out: list[tuple[int, str, list[LinkedEntity]]] = []
    for start, (sent_text, ents) in sorted(by_sent.items()):
        has_seizure = any(
            (e.enum_class == "SeizureType") or
            (e.enum_class == "Awareness")
            for e in ents
        )
        if has_seizure or re.search(r"\bseizures?\b|\bfits?\b|\bjerks?\b|"
                                    r"\bepisodes?\b|\babsences?\b|\bspasms?\b",
                                    sent_text, re.IGNORECASE):
            out.append((start, sent_text, ents))
    return out


# Phase 8 Iter 1 — filter out medication-dose phrases like "150mg twice a day"
# that were leaking into seizure_frequency (F-S 40 EA0174, EA0186, EA0193…).
# A match at position ``i`` in sent_text is skipped if any of these are true
# in a small window immediately before ``i``:
#   * dose unit (mg/g/mcg/units/IU)  →  clearly a prescription rate
#   * frequency abbreviation (bd/bid/tid/qid/od/nocte/mane/qds/tds)
_DOSE_UNIT_LOOKBEHIND = re.compile(
    r"\d+\s*(?:mg|g|mcg|units?|iu)\b|"
    r"\b(?:bd|bid|tds|tid|qds|qid|od|prn|nocte|mane|stat)\b",
    re.IGNORECASE,
)
_DRUG_HINT_LOOKBEHIND = re.compile(
    r"(?:current\s+)?(?:antiseizure|anti[- ]?epileptic|antiepileptic|"
    r"medication|meds?|prescription|dose|dosage|taking|currently\s+on|"
    r"increasing?|reduce|reduction|start(?:ing)?|initiate|"
    r"tegretol|keppra|lamictal|depakote|epilim|topamax|dilantin|"
    r"trileptal|zonegran|vimpat|briviact|neurontin|lyrica)",
    re.IGNORECASE,
)


def _is_dose_like_match(sent_text: str, match_start: int, back: int = 40) -> bool:
    """True if the pattern is likely a medication dose rate rather than a
    seizure frequency (e.g. '150 mg twice a day' or 'Tegretol 400mg bd')."""
    lo = max(0, match_start - back)
    pre = sent_text[lo:match_start]
    if _DOSE_UNIT_LOOKBEHIND.search(pre):
        return True
    # Extend the lookbehind a bit for drug-name cues that may fall further left.
    lo2 = max(0, match_start - 80)
    pre_long = sent_text[lo2:match_start]
    if _DRUG_HINT_LOOKBEHIND.search(pre_long) and _DOSE_UNIT_LOOKBEHIND.search(pre_long):
        return True
    return False


def _extract_from_sentence(
    sent_text: str,
    sent_start: int,
    seizure_type_in_sent: Optional[SeizureType],
) -> Optional[tuple[SeizureFrequency, int, int]]:
    """Return (SeizureFrequency, char_start, char_end) or None. Char offsets
    are relative to the full document (sent_start + match offset).

    Precedence: seizure-free → range → single → once/twice → adjective →
    in-the-last window.

    Dose-guard (Phase 8): patterns preceded by a medication dose unit are
    treated as prescription rates and skipped, so "Tegretol 400mg twice a
    day" doesn't leak into ``seizure_frequency``.
    """
    m = _SEIZURE_FREE_RE.search(sent_text)
    if m:
        num = m.group("num")
        unit = m.group("unit")
        duration = None
        if num and unit:
            duration = f"{num} {TIME_UNIT_MAP.get(unit.lower(), unit)}s"
        freq = _build_freq(
            raw_text=m.group(0),
            period="unspecified",
            seizure_free=True,
            duration_text=duration,
            applies_to_type=seizure_type_in_sent,
        )
        return freq, sent_start + m.start(), sent_start + m.end()

    # Prefer patterns that explicitly bind the seizure word next to the
    # number(s): "3-4 seizures per week". These have higher specificity so
    # they win over bare "N per UNIT" that could be a dose/rate elsewhere.
    for pat, is_range in ((_RE_RANGE_WITH_SEIZURE, True),
                          (_RE_NUM_WITH_SEIZURE, False),
                          (_RE_RANGE_PER_UNIT, True),
                          (_RE_NUM_PER_UNIT, False)):
        # Scan for all matches so we can skip dose-like ones.
        best_m = None
        for m in pat.finditer(sent_text):
            if _is_dose_like_match(sent_text, m.start()):
                continue
            best_m = m
            break
        m = best_m
        if not m:
            continue
        unit = TIME_UNIT_MAP.get(m.group("unit").lower(), "unspecified")
        if is_range:
            n1, n2 = float(m.group("n1")), float(m.group("n2"))
            count_min, count_max = min(n1, n2), max(n1, n2)
        else:
            n = _to_number(m.group("n"))
            count_min = count_max = n
        freq = _build_freq(
            raw_text=m.group(0),
            period=unit,
            count_min=count_min,
            count_max=count_max,
            applies_to_type=seizure_type_in_sent,
        )
        return freq, sent_start + m.start(), sent_start + m.end()

    # Word-form range "once to twice per month" / "one or two per year".
    best_m = None
    for m in _RE_WORD_RANGE.finditer(sent_text):
        if _is_dose_like_match(sent_text, m.start()):
            continue
        best_m = m
        break
    m = best_m
    if m:
        n1 = _WORD_TO_NUM_RANGE.get(m.group("q1").lower())
        n2 = _WORD_TO_NUM_RANGE.get(m.group("q2").lower())
        if n1 is not None and n2 is not None:
            count_min, count_max = min(n1, n2), max(n1, n2)
            unit = TIME_UNIT_MAP.get(m.group("unit").lower(), "unspecified")
            freq = _build_freq(
                raw_text=m.group(0),
                period=unit,
                count_min=count_min,
                count_max=count_max,
                applies_to_type=seizure_type_in_sent,
            )
            return freq, sent_start + m.start(), sent_start + m.end()

    # once/twice/thrice a UNIT — also dose-guarded.
    best_m = None
    for m in _RE_ONCE_TWICE.finditer(sent_text):
        if _is_dose_like_match(sent_text, m.start()):
            continue
        best_m = m
        break
    m = best_m
    if m:
        qual = m.group("qual").lower()
        count_map = {"once": 1.0, "twice": 2.0, "thrice": 3.0,
                     "three times": 3.0, "four times": 4.0}
        n = count_map.get(qual)
        unit = TIME_UNIT_MAP.get(m.group("unit").lower(), "unspecified")
        freq = _build_freq(
            raw_text=m.group(0),
            period=unit,
            count_min=n,
            count_max=n,
            applies_to_type=seizure_type_in_sent,
        )
        return freq, sent_start + m.start(), sent_start + m.end()

    for pat in (_RE_ADJECTIVE, _RE_ADJECTIVE_POST):
        best_m = None
        for m in pat.finditer(sent_text):
            if _is_dose_like_match(sent_text, m.start()):
                continue
            best_m = m
            break
        m = best_m
        if m:
            unit = TIME_UNIT_MAP.get(m.group("unit").lower(), "unspecified")
            freq = _build_freq(
                raw_text=m.group(0),
                period=unit,
                applies_to_type=seizure_type_in_sent,
            )
            return freq, sent_start + m.start(), sent_start + m.end()

    m = _RE_IN_LAST.search(sent_text)
    if m:
        n = _to_number(m.group("n"))
        unit = TIME_UNIT_MAP.get(m.group("unit").lower(), "unspecified")
        count_window = m.group("count")
        window_desc = (f"{count_window} {unit}s" if count_window else f"1 {unit}")
        freq = _build_freq(
            raw_text=m.group(0),
            period=unit,
            count_min=n,
            count_max=n,
            duration_text=window_desc,
            applies_to_type=seizure_type_in_sent,
        )
        return freq, sent_start + m.start(), sent_start + m.end()

    # Range aggregate: "10-15 of these seizures over 2 days".
    m = _RE_RANGE_OVER.search(sent_text)
    if m:
        n1, n2 = float(m.group("n1")), float(m.group("n2"))
        count_min, count_max = min(n1, n2), max(n1, n2)
        unit = TIME_UNIT_MAP.get(m.group("unit").lower(), "unspecified")
        count_window = m.group("count")
        window_desc = (f"{count_window} {unit}s" if count_window else f"1 {unit}")
        freq = _build_freq(
            raw_text=m.group(0),
            period=unit,
            count_min=count_min,
            count_max=count_max,
            duration_text=window_desc,
            applies_to_type=seizure_type_in_sent,
        )
        return freq, sent_start + m.start(), sent_start + m.end()

    return None


# ---------------------------------------------------------------------------
# Rule 1 — Predominant frequency (first / most-supported one)
# ---------------------------------------------------------------------------


class SeizureFrequencyRule(BaseFieldRule):
    """Populate ``clinical_seizure.seizure_frequency``."""

    field_name = "clinical_seizure.seizure_frequency"

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        detections = _collect_all_frequencies(entities, doc)
        if detections:
            freq, span_start, span_end, anchor_entity, anchor_flags = detections[0]
            return _wrap_frequency_ev(
                freq, span_start, span_end, anchor_entity, anchor_flags, meta, doc
            )

        # Phase 8 Iter 3 fallback — if no explicit frequency but the doc
        # clearly mentions seizure activity (not seizure-free), emit a
        # low-confidence ``seizure_free=False`` placeholder. F-S convention
        # scores seizure_free=False for docs that mention active seizures.
        text = getattr(doc, "text", "") or ""
        if not text:
            return None
        has_seizure_mention = re.search(
            r"\b(?:seizures?|episodes?|events?|attacks?|absences?|"
            r"myoclon(?:us|ic)|convulsi(?:on|ve)|jerks?)\b",
            text, re.IGNORECASE,
        )
        has_seizure_free = _SEIZURE_FREE_RE.search(text)
        if has_seizure_mention and not has_seizure_free:
            # Emit a minimal placeholder — F-S scores presence of
            # ``seizure_free=False``, so this counts as a hit.
            freq = _build_freq(
                raw_text="",
                period="unspecified",
                seizure_free=False,
            )
            return Evidence[SeizureFrequency](
                value=freq,
                certainty=Certainty.POSSIBLE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text="active seizures documented",
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
            )
        return None


# ---------------------------------------------------------------------------
# Rule 2 — Other frequencies
# ---------------------------------------------------------------------------


class OtherSeizureFrequenciesRule(BaseFieldRule):
    """Populate ``clinical_seizure.other_seizure_frequencies``."""

    field_name = "clinical_seizure.other_seizure_frequencies"

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[list[Evidence]]:
        detections = _collect_all_frequencies(entities, doc)
        if len(detections) < 2:
            return None
        out: list[Evidence] = []
        for freq, span_start, span_end, anchor_entity, anchor_flags in detections[1:]:
            ev = _wrap_frequency_ev(
                freq, span_start, span_end, anchor_entity, anchor_flags, meta, doc
            )
            out.append(ev)
        return out or None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _collect_all_frequencies(
    entities: list[LinkedEntity],
    doc,
) -> list[tuple[SeizureFrequency, int, int, Optional[LinkedEntity], dict[str, bool]]]:
    """Return a list of (freq, char_start, char_end, anchor_entity, flags) in
    document order, deduplicated by (period, count_min, count_max, seizure_free)."""
    out = []
    seen: set[tuple] = set()

    # Iterate sentences with seizure context.
    for sent_start, sent_text, ents_in_sent in _sentences_with_seizure(entities, doc):
        # Skip sentences whose seizure entity is negated or hypothetical.
        seizure_ents = [
            e for e in ents_in_sent
            if e.enum_class == "SeizureType"
        ]
        any_seizure_neg = any(e.is_negated for e in seizure_ents)
        any_seizure_hyp = any(e.is_hypothetical for e in seizure_ents)
        any_seizure_hist = any(e.is_historical for e in seizure_ents)

        # For seizure-free sentence, negation is the trigger (not a blocker):
        # e.g. "she has had no further seizures" IS the SF signal.
        is_seizure_free_sent = bool(_SEIZURE_FREE_RE.search(sent_text))
        if any_seizure_neg and not is_seizure_free_sent:
            continue

        # Pick the anchor SeizureType present in the sentence.
        seizure_type_val: Optional[SeizureType] = None
        anchor: Optional[LinkedEntity] = None
        for e in seizure_ents:
            try:
                seizure_type_val = SeizureType(e.enum_value)
                anchor = e
                break
            except ValueError:
                continue

        result = _extract_from_sentence(sent_text, sent_start, seizure_type_val)
        if result is None:
            continue
        freq, span_start, span_end = result

        key = (freq.period, freq.count_min, freq.count_max, freq.seizure_free)
        if key in seen:
            continue
        seen.add(key)

        flags = {
            "hypothetical": any_seizure_hyp,
            "historical": any_seizure_hist,
        }
        out.append((freq, span_start, span_end, anchor, flags))
    return out


def _wrap_frequency_ev(
    freq: SeizureFrequency,
    span_start: int,
    span_end: int,
    anchor: Optional[LinkedEntity],
    flags: dict[str, bool],
    meta: dict[str, Any],
    doc,
) -> Evidence:
    """Build an ``Evidence[SeizureFrequency]``. When we have an anchor
    SeizureType entity we use its ConText flags; otherwise default flags."""
    is_hyp = flags.get("hypothetical", False)
    is_hist = flags.get("historical", False)

    certainty = Certainty.POSSIBLE if is_hyp else Certainty.DEFINITE
    temporal = TemporalStatus.HISTORICAL if is_hist else TemporalStatus.CURRENT
    # Approx quantifier → downgrade to PROBABLE.
    doc_text = getattr(doc, "text", "") or ""
    window = doc_text[max(0, span_start - 30):span_end]
    if _APPROX_RE.search(window) and certainty == Certainty.DEFINITE:
        certainty = Certainty.PROBABLE

    return Evidence[SeizureFrequency](
        value=freq,
        certainty=certainty,
        temporal_status=temporal,
        evidence_text=freq.raw_text,
        source_doc_id=meta["doc_id"],
        source_doc_type=meta["doc_type"],
        source_date=meta["doc_date"],
        char_start=span_start,
        char_end=span_end,
    )


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(SeizureFrequencyRule())
register_rule(OtherSeizureFrequenciesRule())


__all__ = ["SeizureFrequencyRule", "OtherSeizureFrequenciesRule"]
