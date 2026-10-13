"""Broad onset class of an ILAE 2017 seizure type: focal, generalized or unknown onset.

The two readers often name different subtypes of the same seizure ("focal aware" vs "focal impaired
awareness").  LEO fuses the onset class as its own field (``ONSET_CLASS_PATH``), so the broad class can be
accepted when both readers agree on it while the subtype disagreement still goes to a person.  The coarse
level matches the categories Fang et al. (Epilepsia 2025) scored on real clinic letters.
"""

from __future__ import annotations

from typing import Any, Optional

SEIZURE_TYPE_PATH = "clinical_seizure.predominant_seizure_type"
ONSET_CLASS_PATH = "clinical_seizure.seizure_onset_class"
ONSET_CLASSES = ("focal", "generalized", "unknown_onset")

# Gold labels that are not schema enum names (scripts/score_leo_vs_fs_gold.GOLD_SEIZURE_TYPE_TO_ENUM).
_GENERALIZED_BARE = {"absence_typical", "absence_atypical", "myoclonic", "atonic"}


def onset_class(seizure_type: Any) -> Optional[str]:
    """``focal`` / ``generalized`` / ``unknown_onset`` for an ILAE seizure type, else None (unclassified, empty)."""
    if seizure_type is None:
        return None
    v = getattr(seizure_type, "value", seizure_type)
    v = str(v).strip().lower().replace(" ", "_").replace("-", "_")
    if v.startswith("focal"):
        return "focal"
    if v.startswith("generalized") or v.startswith("generalised") or v in _GENERALIZED_BARE:
        return "generalized"
    if v.startswith("unknown_onset"):
        return "unknown_onset"
    return None


__all__ = ["onset_class", "ONSET_CLASS_PATH", "ONSET_CLASSES", "SEIZURE_TYPE_PATH"]
