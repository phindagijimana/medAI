"""
onset_age.py — Age at first seizure / epilepsy onset (float years).

Field populated
---------------
- ``clinical_seizure.age_at_onset_years``  (Evidence[float])

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``jape/OnsetAge.jape``              — canonical "Person + Disease + onset + Age"
- ``jape/OnsetAgeA.jape``             — variant with different word order
- ``jape/OnsetAgeB.jape``             — probability + onset combined
- ``jape/OnsetAgeC.jape``             — small residual cases
- ``jape/OnsetAgeRange.jape``         — age range (e.g. "in his teens", "aged 6-8")
- ``jape/onset.jape``                 — Onset trigger annotations
- ``jape/times.jape``                 — TimePeriod gazetteer parse
- ``jape/Age.jape`` / ``age3.jape``   — Age token composition
- ``jape/AgeDiagnosed.jape``          — age-at-diagnosis (distinct from onset;
                                        we prefer onset when both present)
- ``jape/TimeSinceOnset.jape``        — "seizures since age X"
- ``jape/TimeSinceOnsetB.jape``       — "X years since first seizure"
- ``Groovy/Onset.groovy``             — output serializer
- ``Groovy/WhenDiagnosed.groovy``     — diagnosis-age serializer (fallback)

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
Regex bank ordered by specificity → first match wins:
1. "seizures/epilepsy started/began at age N"
2. "first seizure at N" / "at the age of N had first seizure"
3. "since age N" / "from age N"  (in the presence of a seizure/epilepsy word)
4. "onset at N years" / "age of onset N"
5. "diagnosed at age N" (fallback — diagnosis-age serves when onset-age absent;
   ExECT distinguished these in AgeDiagnosed.jape but the F-S train gold
   commonly conflates them).
6. "N-year-old with X-year history of seizures" → onset ≈ age − history

Age-in-months (< 24 months) → fractional years (e.g. 6 months → 0.5).
Reject: age ≤ 0 or age > 100 (typo filter).

ConText flags
-------------
Nearby ``is_negated`` on a seizure entity in the same clause → skip.
``is_family`` (e.g. "father had epilepsy at 30") → skip.
Historical is expected here (age refers to a past event); default temporal
status remains ``CURRENT`` because the *record* is a current fact.

Cite: Fonferko-Shadrach et al. 2019; 2024.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import Certainty, TemporalStatus
from schema.evidence import Evidence
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Patterns (specificity descending)
# ---------------------------------------------------------------------------

# 1. "seizures started/began/first occurred at (the age of) N"
_RE_STARTED_AT = re.compile(
    r"(?:seizures?|epilepsy|episodes?|attacks?|fits?)"
    r"[^.]{0,60}?"
    r"(?:started|began|first\s+occurred|first\s+started|first\s+began|"
    r"first\s+happened|first\s+presented|were\s+first)"
    r"[^.]{0,30}?"
    r"(?:at\s+(?:the\s+)?age\s+of\s+|at\s+age\s+|aged\s+|at\s+)"
    r"(?P<n>\d+(?:\.\d+)?)(?:\s*(?P<u>months?|years?|yrs?|mo\b))?",
    re.IGNORECASE,
)

# 1b. Verb-first variant: "began having seizures ... at N years of age"
#     Catches MTSamples-style "He began having seizures, however, at 9 years of age."
_RE_VERB_FIRST_STARTED = re.compile(
    r"(?:began|started|first\s+had|first\s+experienced|developed)"
    r"[^.]{0,40}?"
    r"(?:seizures?|epilepsy|episodes?|attacks?|fits?|spells?|convulsions?)"
    r"[^.]{0,60}?"
    r"(?:at\s+(?:the\s+)?age\s+of\s+|at\s+age\s+|aged\s+|"
    r"at\s+(?P<n_alt>\d+(?:\.\d+)?)\s*(?:months?|years?|yrs?|mo\b)?\s+of\s+age)"
    r"(?:(?P<n>\d+(?:\.\d+)?)(?:\s*(?P<u>months?|years?|yrs?|mo\b))?)?",
    re.IGNORECASE,
)

# 2. "first seizure at N" (compact form)
_RE_FIRST_SEIZURE_AT = re.compile(
    r"(?:her|his|their|the)?\s*first\s+(?:seizure|fit|episode)"
    r"[^.]{0,40}?"
    r"(?:at\s+(?:the\s+)?age\s+of\s+|at\s+age\s+|aged\s+|at\s+)"
    r"(?P<n>\d+(?:\.\d+)?)(?:\s*(?P<u>months?|years?|yrs?|mo\b))?",
    re.IGNORECASE,
)

# 3. "since age N" / "from age N" combined with an epilepsy/seizure word
#    within the same sentence (checked separately).
_RE_SINCE_AGE = re.compile(
    r"(?:since|from)\s+(?:the\s+)?age\s+(?:of\s+)?(?P<n>\d+(?:\.\d+)?)"
    r"(?:\s*(?P<u>months?|years?|yrs?|mo\b))?",
    re.IGNORECASE,
)

# 4. "onset at N years" / "age of onset (was) N"
_RE_ONSET_AT = re.compile(
    r"(?:age\s+of\s+onset|onset\s+(?:at|of|age))"
    r"[^.]{0,20}?"
    r"(?P<n>\d+(?:\.\d+)?)(?:\s*(?P<u>months?|years?|yrs?|mo\b))?",
    re.IGNORECASE,
)

# 5. "diagnosed with (epilepsy) at (the age of) N" — fallback for onset.
_RE_DIAGNOSED_AT = re.compile(
    r"diagnosed(?:\s+with\s+(?:epilepsy|seizures?))?"
    r"[^.]{0,30}?"
    r"(?:at\s+(?:the\s+)?age\s+of\s+|at\s+age\s+|aged\s+)"
    r"(?P<n>\d+(?:\.\d+)?)(?:\s*(?P<u>months?|years?|yrs?|mo\b))?",
    re.IGNORECASE,
)

# 6. "N-year-old with M-year history of seizures" → onset ≈ N − M
_RE_HISTORY_OF = re.compile(
    r"(?P<age>\d+)[- ]year[- ]?old"
    r"[^.]{0,60}?"
    r"(?P<hist>\d+)[- ]year(?:s)?\s+history\s+of\s+"
    r"(?:seizures?|epilepsy)",
    re.IGNORECASE,
)

# 6b. Compound reasoning: "N-year-old ... developed/began seizures M year(s) ago"
#     Onset = current_age − years_ago.  Catches MTSamples MT_V0073 pattern.
_RE_HISTORY_YEARS_AGO = re.compile(
    r"(?P<age>\d+)[- ]year[- ]?old"
    r"[^.]{0,140}?"
    r"(?:developed|began\s+having|started\s+having|first\s+had)"
    r"\s+(?:seizures?|epilepsy|episodes?|spells?)"
    r"[^.]{0,40}?"
    r"(?:about\s+|approximately\s+|~\s*)?"
    r"(?P<hist>\d+)\s+year(?:s)?\s+ago",
    re.IGNORECASE,
)

# 7. Fractional / hyphenated age: "2-1/2-year-old", "18-month-old", "3½-year-old"
#    Common in pediatric neurology notes.  Catches MTSamples MT_V0067.
_RE_FRACTIONAL_AGE = re.compile(
    r"(?P<whole>\d+)"
    r"(?:[- ](?:1/2|½|1/4|3/4))?"
    r"[- ](?:month|year|yr)[- ]?old"
    r"[^.]{0,80}?"
    r"(?:history\s+of|with\s+(?:known\s+)?|"
    r"(?:known|febrile|myoclonic|absence)\s+seizures?)",
    re.IGNORECASE,
)

# Family-history clause — used to *reject* onset ages captured within it.
_FAMILY_CLAUSE = re.compile(
    r"\b(?:father|mother|brother|sister|sibling|uncle|aunt|grandmother|"
    r"grandfather|cousin|son|daughter|parent|family\s+history)\b",
    re.IGNORECASE,
)

_SEIZURE_WORD = re.compile(
    r"\b(?:seizures?|epilepsy|convulsions?|fits?|episodes?)\b", re.IGNORECASE
)


def _normalise_age(n: float, unit: Optional[str]) -> Optional[float]:
    if unit and unit.lower().startswith("mo"):
        n = n / 12.0
    if n <= 0 or n > 100:
        return None
    return round(n, 3)


def _find_sentence(doc, char_start: int) -> tuple[str, int]:
    """Return the (sentence_text, sentence_char_start) enclosing ``char_start``."""
    if doc is None or not hasattr(doc, "sents"):
        return "", -1
    for sent in doc.sents:
        if sent.start_char <= char_start < sent.end_char:
            return sent.text, sent.start_char
    return "", -1


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------


class OnsetAgeRule(BaseFieldRule):
    """Populate ``clinical_seizure.age_at_onset_years``."""

    field_name = "clinical_seizure.age_at_onset_years"

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        if not text:
            return None

        # Ordered attempts — first successful → win.
        for pattern in (_RE_STARTED_AT, _RE_FIRST_SEIZURE_AT):
            m = pattern.search(text)
            if m and self._sentence_ok(doc, m.start()):
                age = _normalise_age(float(m.group("n")), m.group("u"))
                if age is not None:
                    return self._emit(age, m, meta)

        # Verb-first variant ("began having seizures at N years of age") —
        # handles insertions like "however," between the verb phrase and the age.
        for m in _RE_VERB_FIRST_STARTED.finditer(text):
            if not self._sentence_ok(doc, m.start()):
                continue
            n_str = m.group("n") or m.group("n_alt")
            if not n_str:
                continue
            age = _normalise_age(float(n_str), m.group("u"))
            if age is not None:
                return self._emit(age, m, meta)

        # "since age N" only if the same sentence mentions a seizure/epilepsy word.
        for m in _RE_SINCE_AGE.finditer(text):
            sent_text, _ = _find_sentence(doc, m.start())
            if not _SEIZURE_WORD.search(sent_text or ""):
                continue
            if not self._sentence_ok(doc, m.start()):
                continue
            age = _normalise_age(float(m.group("n")), m.group("u"))
            if age is not None:
                return self._emit(age, m, meta)

        m = _RE_ONSET_AT.search(text)
        if m and self._sentence_ok(doc, m.start()):
            age = _normalise_age(float(m.group("n")), m.group("u"))
            if age is not None:
                return self._emit(age, m, meta)

        m = _RE_DIAGNOSED_AT.search(text)
        if m and self._sentence_ok(doc, m.start()):
            age = _normalise_age(float(m.group("n")), m.group("u"))
            if age is not None:
                return self._emit(age, m, meta, certainty=Certainty.PROBABLE)

        m = _RE_HISTORY_OF.search(text)
        if m and self._sentence_ok(doc, m.start()):
            try:
                current_age = float(m.group("age"))
                hist = float(m.group("hist"))
                onset = current_age - hist
            except ValueError:
                onset = None
            if onset is not None:
                age = _normalise_age(onset, None)
                if age is not None:
                    return self._emit(age, m, meta, certainty=Certainty.PROBABLE)

        # "N-year-old ... developed seizures M years ago" → onset = N − M
        for m in _RE_HISTORY_YEARS_AGO.finditer(text):
            if not self._sentence_ok(doc, m.start()):
                continue
            try:
                current_age = float(m.group("age"))
                hist = float(m.group("hist"))
                onset = current_age - hist
            except ValueError:
                continue
            age = _normalise_age(onset, None)
            if age is not None:
                return self._emit(age, m, meta, certainty=Certainty.PROBABLE)

        # Fractional-age composite ("2-1/2-year-old with a history of ...
        # seizures") — the age itself is the onset when history is present.
        for m in _RE_FRACTIONAL_AGE.finditer(text):
            if not self._sentence_ok(doc, m.start()):
                continue
            whole = float(m.group("whole"))
            # Detect the fraction in the raw match text.
            raw = m.group(0).lower()
            if "1/2" in raw or "½" in raw:
                whole += 0.5
            elif "1/4" in raw:
                whole += 0.25
            elif "3/4" in raw:
                whole += 0.75
            # Month-old → convert to years.
            if "month" in raw:
                whole = whole / 12.0
            age = _normalise_age(whole, None)
            if age is not None:
                return self._emit(age, m, meta, certainty=Certainty.PROBABLE)

        return None

    # ------------------------------------------------------------------

    def _sentence_ok(self, doc, char_start: int) -> bool:
        """Reject matches inside a family-history clause."""
        sent_text, _ = _find_sentence(doc, char_start)
        if _FAMILY_CLAUSE.search(sent_text or ""):
            return False
        return True

    # ------------------------------------------------------------------

    def _emit(
        self,
        age: float,
        m: re.Match,
        meta: dict[str, Any],
        *,
        certainty: Certainty = Certainty.DEFINITE,
    ) -> Evidence:
        return Evidence[float](
            value=age,
            certainty=certainty,
            temporal_status=TemporalStatus.CURRENT,
            evidence_text=m.group(0),
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
            char_start=m.start(),
            char_end=m.end(),
        )


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(OnsetAgeRule())

__all__ = ["OnsetAgeRule"]
