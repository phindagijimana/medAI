"""Opt-in extra detectors for LEO (literature field specialists).

Default LEO is unchanged: ``ChainPipelineConfig.ext_detectors`` is empty.
A named sidecar emits overlapping schema cells with a quote. It cannot
auto-accept and cannot demote an E+L accept. See
``docs/FIELD_SPECIALIST_DETECTORS.md``.

Registered without new training:

* ``ctakes`` — Savova 2010 dictionary lookup + Chapman NegEx + Uzuner 2010
  medication status (S1+S2). Does not require the Java cTAKES binary.
* ``freq`` — current stated seizure frequency + seizure-free (Xie *task*).
* ``stated-type`` — explicit ILAE / epilepsy-type phrases only (Decker *task*).
* ``hs`` — HS/FCD mention + NegEx; never ``false`` if MRI is unmentioned.
* ``fail-reason`` — NINDS CDE discontinuation reason (efficacy vs ADE vs wean).
* ``rescue-if`` — home PRN rescue; skip instructional if-clauses (Pina-Garza).
* ``ictal`` — ACNS captured electrographic seizure vs not captured.
* ``eeg-done`` — EEG study type only if performed, not recommended.
* ``dre`` — drug-resistance as written (Kwan phrases; no two-drug count).
* ``first-feature`` — Fisher 2017 first prominent sign only.

Not registered: ``b1`` / Xie / Decker heads (need training); ``engel`` (not a
LEO catalogue column). ``acute_administration`` is already on ``ctakes``.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

from services.chain_llm import FieldItem


def _EXTRACTORS_lazy() -> dict:
    from services.ext_detectors.ctakes_meds import extract_ctakes_meds
    from services.ext_detectors.freq import extract_freq
    from services.ext_detectors.stated_type import extract_stated_type
    from services.ext_detectors.hs import extract_hs
    from services.ext_detectors.guideline import (
        extract_dre,
        extract_eeg_done,
        extract_fail_reason,
        extract_first_feature,
        extract_ictal,
        extract_rescue_if,
    )
    return {
        "ctakes": extract_ctakes_meds,
        "freq": extract_freq,
        "stated-type": extract_stated_type,
        "hs": extract_hs,
        "fail-reason": extract_fail_reason,
        "rescue-if": extract_rescue_if,
        "ictal": extract_ictal,
        "eeg-done": extract_eeg_done,
        "dre": extract_dre,
        "first-feature": extract_first_feature,
    }


_EXTRACTORS: dict | None = None


def _extractors() -> dict:
    global _EXTRACTORS
    if _EXTRACTORS is None:
        _EXTRACTORS = _EXTRACTORS_lazy()
    return _EXTRACTORS

KNOWN_EXT_DETECTORS = (
    "ctakes", "freq", "stated-type", "hs",
    "fail-reason", "rescue-if", "ictal", "eeg-done", "dre", "first-feature",
)
_TRAINING_BLOCKED = {
    "b1": "B1 BioClinicalBERT needs a trained head on our labels; not registered.",
    "xie": "Xie-style trained frequency head is not registered; use --ext-detector freq.",
    "decker": "Decker-style trained seizure-type head is not registered; use --ext-detector stated-type.",
    "ner-onset": "Span/BIO NER for onset needs a trained field head; not dumped into E.",
    "ner-laterality": "Span/BIO NER for EEG/MRI laterality needs a trained field head.",
    "ner-drug": "Span/BIO NER for drug+dose needs a trained field head; use --ext-detector ctakes until then.",
}
_NOT_CATALOGUE = {
    "engel": "Engel/ILAE outcome is schema-ready but not a LEO extract column; not registered.",
}


def parse_ext_detectors(value: Optional[str | Iterable[str]] = None) -> tuple[str, ...]:
    """CLI / env ``MEDAI_LEO_EXT_DETECTOR`` → known names. Empty default (LEO frozen)."""
    if value is None:
        value = os.environ.get("MEDAI_LEO_EXT_DETECTOR", "")
    if isinstance(value, str):
        parts = [p.strip().lower() for p in value.replace(";", ",").split(",")]
    else:
        parts = []
        for v in value or ():
            parts.extend(str(v).strip().lower().split(","))
    names = [p for p in parts if p]
    out: list[str] = []
    for name in names:
        if name in _TRAINING_BLOCKED:
            raise ValueError(_TRAINING_BLOCKED[name])
        if name in _NOT_CATALOGUE:
            raise ValueError(_NOT_CATALOGUE[name])
        if name not in KNOWN_EXT_DETECTORS:
            raise ValueError(
                f"unknown extra detector {name!r}; known: {', '.join(KNOWN_EXT_DETECTORS)}"
            )
        if name not in out:
            out.append(name)
    return tuple(out)


def extract_ext_detectors(names: Iterable[str], text: str) -> list[FieldItem]:
    """Run each named sidecar on ``text``. Unknown names raise ``ValueError``."""
    items: list[FieldItem] = []
    seen: set[str] = set()
    for raw in names or ():
        name = str(raw or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        if name in _TRAINING_BLOCKED:
            raise ValueError(_TRAINING_BLOCKED[name])
        if name in _NOT_CATALOGUE:
            raise ValueError(_NOT_CATALOGUE[name])
        fn = _extractors().get(name)
        if fn is None:
            raise ValueError(
                f"unknown extra detector {name!r}; known: {', '.join(KNOWN_EXT_DETECTORS)}"
            )
        items.extend(fn(text))
        continue
    return items


__all__ = ["KNOWN_EXT_DETECTORS", "extract_ext_detectors", "parse_ext_detectors"]
