"""Stated-only epilepsy / seizure type sidecar (Decker *task*, not Decker weights).

Fires only on explicit ILAE 2017 operational names and explicit epilepsy-type
phrases. Does **not** infer epilepsy type from seizure types, and does **not**
map old aliases (CPS, SPS, grand mal, secondarily generalized) — that mapping
is E. Silent when the diagnosis line names none.

Detector name: ``stated-type``.
Paths: ``clinical_seizure.epilepsy_type``, ``clinical_seizure.predominant_seizure_type``.
"""

from __future__ import annotations

import re

from services.chain_llm import FieldItem
from services.ext_detectors.span import sentence_window, skip_mention

DETECTOR = "stated-type"

# Explicit epilepsy *type* (Fisher 2017 top-level). No TLE/FLE inference, no
# seizure-to-epilepsy composition.
_EPILEPSY: list[tuple[re.Pattern[str], str]] = [
    (re.compile(
        r"combined\s+focal\s+and\s+generali[sz]ed(?:\s+epilepsy)?",
        re.I), "combined_focal_generalized"),
    (re.compile(
        r"idiopathic\s+generali[sz]ed\s+epilepsy|\bIGE\b|"
        r"juvenile\s+myoclonic\s+epilepsy|\bJME\b|"
        r"childhood\s+absence\s+epilepsy|\bCAE\b|"
        r"juvenile\s+absence\s+epilepsy|\bJAE\b|"
        r"generali[sz]ed\s+epilepsy",
        re.I), "generalized"),
    (re.compile(r"focal\s+epilepsy", re.I), "focal"),
    (re.compile(
        r"unknown[- ]onset\s+epilepsy|epilepsy\s+of\s+unknown\s+onset",
        re.I), "unknown"),
]

# ILAE 2017 operational seizure names only (Fisher 2017). No CPS/SPS/grand mal.
_SEIZURE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(
        r"focal[- ]?to[- ]?bilateral\s+tonic[- ]?clonic\s+seizures?|\bFBTC\b",
        re.I), "focal_to_bilateral_tonic_clonic"),
    (re.compile(
        r"focal\s+impaired[- ]awareness\s+seizures?",
        re.I), "focal_impaired_awareness"),
    (re.compile(r"focal\s+aware\s+seizures?", re.I), "focal_aware"),
    (re.compile(
        r"typical\s+absence\s+seizures?|3[- ]?Hz\s+spike[- ]?wave\s+absences?",
        re.I), "generalized_absence_typical"),
    (re.compile(r"atypical\s+absence\s+seizures?", re.I),
     "generalized_absence_atypical"),
    (re.compile(r"\babsence\s+seizures?\b", re.I),
     "generalized_absence_typical"),
    (re.compile(
        r"generali[sz]ed\s+tonic[- ]?clonic\s+seizures?|\bGTCS\b|\bGTC\b",
        re.I), "generalized_tonic_clonic"),
    (re.compile(r"generali[sz]ed\s+myoclonic\s+seizures?|myoclonic\s+seizures?",
                re.I), "generalized_myoclonic"),
    (re.compile(r"atonic\s+seizures?", re.I), "generalized_atonic"),
    (re.compile(r"(?:epileptic|infantile)\s+spasms?", re.I),
     "generalized_epileptic_spasms"),
    (re.compile(r"generali[sz]ed\s+tonic\s+seizures?|tonic\s+seizures?(?!\s+clonic)",
                re.I), "generalized_tonic"),
    (re.compile(r"generali[sz]ed\s+clonic\s+seizures?", re.I),
     "generalized_clonic"),
]


def _item(path: str, value: str, quote: str, start: int, end: int) -> FieldItem:
    return FieldItem(
        field_path=path,
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


def _first(text: str, patterns: list[tuple[re.Pattern[str], str]], path: str) -> list[FieldItem]:
    for pat, value in patterns:
        for m in pat.finditer(text):
            start, end = m.start(), m.end()
            sent, a, _b = sentence_window(text, start, end)
            if skip_mention(sent, a):
                continue
            quote = re.sub(r"\s+", " ", text[start:end].strip())
            return [_item(path, value, quote, start, end)]
    return []


def extract_stated_type(text: str) -> list[FieldItem]:
    """Explicit type mentions only; empty when the note never names one."""
    if not (text or "").strip():
        return []
    out: list[FieldItem] = []
    out.extend(_first(text, _EPILEPSY, "clinical_seizure.epilepsy_type"))
    out.extend(_first(text, _SEIZURE, "clinical_seizure.predominant_seizure_type"))
    return out


__all__ = ["DETECTOR", "extract_stated_type"]
