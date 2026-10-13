"""Weak labels from EpExtra rules, for later Trove-style supervision (Fries et al. 2021).

Each function is a labeling function: note text → a field value or None (abstain). They wrap the same
rules LEO already runs, so a label model can learn their accuracies on unlabelled notes without new gold.
Do not train a classifier from these until the field rules in steps 1–4 are frozen
(``writing/further_LEO.md`` M3 / step 6).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any, Callable, Optional

from schema.enums import DocumentType

_META = {"doc_id": "weak", "doc_type": DocumentType.PROGRESS_NOTE, "doc_date": date(2020, 1, 1)}


def _ev_value(ev) -> Any:
    if ev is None:
        return None
    if isinstance(ev, list):
        return None
    return getattr(ev, "value", ev)


def lf_epilepsy_type(text: str) -> Optional[str]:
    from rules.fields.epilepsy_type import EpilepsyTypeRule
    v = _ev_value(EpilepsyTypeRule().apply([], SimpleNamespace(text=text), _META))
    return getattr(v, "value", v) if v is not None else None


def lf_seizure_free(text: str) -> Optional[bool]:
    from rules.fields.seizure_frequency import SeizureFrequencyRule
    from services.seizure_free import seizure_free_value
    ev = SeizureFrequencyRule().apply([], SimpleNamespace(text=text), _META)
    return seizure_free_value(_ev_value(ev)) if ev is not None else None


def lf_pnes_status(text: str) -> Optional[str]:
    from rules.pnes import pnes_status
    hit = pnes_status(text)
    return None if hit is None else hit[0]


def lf_ied_present(text: str) -> Optional[bool]:
    from rules.fields.eeg import IedPresentRule
    return _ev_value(IedPresentRule().apply([], SimpleNamespace(text=text), _META))


LABELING_FUNCTIONS: dict[str, Callable[[str], Any]] = {
    "clinical_seizure.epilepsy_type": lf_epilepsy_type,
    "clinical_seizure.seizure_free": lf_seizure_free,
    "clinical_seizure.pnes_status": lf_pnes_status,
    "eeg.ied_present": lf_ied_present,
}


def weak_labels(text: str, fields: Optional[list[str]] = None) -> dict[str, Any]:
    """``{field_path: value}`` for functions that do not abstain."""
    want = fields or list(LABELING_FUNCTIONS)
    out = {}
    for path in want:
        fn = LABELING_FUNCTIONS[path]
        v = fn(text)
        if v is not None:
            out[path] = v
    return out


__all__ = ["LABELING_FUNCTIONS", "weak_labels", "lf_epilepsy_type", "lf_seizure_free",
           "lf_pnes_status", "lf_ied_present"]
