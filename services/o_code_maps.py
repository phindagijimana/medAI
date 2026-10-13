"""Post-extract export codes: ICD-10-CM, Orphanet, SCORE, EpSO.

O, not E. After E or L has already emitted a value, attach a stable id so a registry or
NINDS CDE export can join sites. These tables are never loaded as gazetteers in
``rules/fields/`` or ``rules/epilepsy_ontology.py``. They do not change ACCEPT/REVIEW.

  * ICD-10-CM G40.x — cohort/billing category from ILAE epilepsy/seizure type.
    Never map ``drug_resistance_status`` to ICD "intractable" (that is not ILAE DRE).
  * Orphanet — rare-syndrome id when the *extracted* etiology/syndrome name already
    names a disease (Dravet, LGS, …). Not a seizure-type filler.
  * SCORE — map an EEG finding already extracted (spike, LPD, …) to a SCORE label.
    Not a gazetteer that invents LPDs.
  * EpSO — ILAE enum → EpSO class label for interoperability. EPIO is already the
    retrieval source in O; this does not add EpSO strings to E.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Category-level ICD-10-CM (not a billable 7-character code). ILAE type stays the phenotype.
_EPILEPSY_ICD = {
    "focal": ("ICD-10-CM", "G40.1", "focal / localization-related epilepsy (category)"),
    "generalized": ("ICD-10-CM", "G40.4", "other generalized epilepsy (category)"),
    "combined_focal_generalized": ("ICD-10-CM", "G40.8", "other epilepsy (category)"),
    "unknown": ("ICD-10-CM", "G40.9", "epilepsy, unspecified (category)"),
}
_SEIZURE_ICD = {
    "focal_aware": ("ICD-10-CM", "G40.1", "focal / simple partial seizures (category)"),
    "focal_impaired_awareness": ("ICD-10-CM", "G40.2", "focal / complex partial seizures (category)"),
    "focal_unknown_awareness": ("ICD-10-CM", "G40.2", "focal seizures (category)"),
    "focal_to_bilateral_tonic_clonic": ("ICD-10-CM", "G40.1", "focal seizures (category)"),
    "generalized_tonic_clonic": ("ICD-10-CM", "G40.4", "generalized seizures (category)"),
    "generalized_tonic": ("ICD-10-CM", "G40.4", "generalized seizures (category)"),
    "generalized_clonic": ("ICD-10-CM", "G40.4", "generalized seizures (category)"),
    "generalized_myoclonic": ("ICD-10-CM", "G40.4", "generalized seizures (category)"),
    "generalized_absence_typical": ("ICD-10-CM", "G40.4", "generalized seizures (category)"),
    "generalized_absence_atypical": ("ICD-10-CM", "G40.4", "generalized seizures (category)"),
    "generalized_atonic": ("ICD-10-CM", "G40.4", "generalized seizures (category)"),
    "generalized_epileptic_spasms": ("ICD-10-CM", "G40.4", "generalized seizures (category)"),
    "unknown_onset_tonic_clonic": ("ICD-10-CM", "G40.9", "epilepsy, unspecified (category)"),
    "unclassified": ("ICD-10-CM", "G40.9", "epilepsy, unspecified (category)"),
}

# Sahoo / EpSO-style class names (interoperability labels, not OWL loaded into E).
_EPILEPSY_EPSO = {
    "focal": ("EpSO", "FocalEpilepsy", "focal epilepsy"),
    "generalized": ("EpSO", "GeneralizedEpilepsy", "generalized epilepsy"),
    "combined_focal_generalized": ("EpSO", "CombinedFocalAndGeneralizedEpilepsy",
                                   "combined focal and generalized epilepsy"),
    "unknown": ("EpSO", "UnknownEpilepsy", "unknown epilepsy"),
}
_SEIZURE_EPSO = {
    "focal_aware": ("EpSO", "FocalAwareSeizure", "focal aware seizure"),
    "focal_impaired_awareness": ("EpSO", "FocalImpairedAwarenessSeizure", "focal impaired-awareness seizure"),
    "focal_to_bilateral_tonic_clonic": ("EpSO", "FocalToBilateralTonicClonicSeizure",
                                        "focal to bilateral tonic-clonic seizure"),
    "generalized_tonic_clonic": ("EpSO", "GeneralizedTonicClonicSeizure", "generalized tonic-clonic seizure"),
    "generalized_absence_typical": ("EpSO", "AbsenceSeizure", "typical absence seizure"),
    "generalized_myoclonic": ("EpSO", "MyoclonicSeizure", "myoclonic seizure"),
    "generalized_atonic": ("EpSO", "AtonicSeizure", "atonic seizure"),
    "generalized_epileptic_spasms": ("EpSO", "EpilepticSpasm", "epileptic spasm"),
}

# Beniczky SCORE labels for IED types already extracted. OTHER + LPD evidence → LPD, not a finder.
_IED_SCORE = {
    "spike": ("SCORE", "spike", "spike"),
    "sharp_wave": ("SCORE", "sharp_wave", "sharp wave"),
    "spike_and_wave": ("SCORE", "spike_and_wave", "spike-and-wave"),
    "polyspike": ("SCORE", "polyspike", "polyspike"),
    "polyspike_and_wave": ("SCORE", "polyspike_and_wave", "polyspike-and-wave"),
    "sharp_and_slow": ("SCORE", "sharp_and_slow_wave", "sharp-and-slow wave"),
    "generalized_spike_wave_3hz": ("SCORE", "generalized_3hz_spike_and_wave", "3 Hz spike-and-wave"),
}
_LPD = re.compile(r"\b(?:LPDs?|PLEDs?)\b", re.I)
_GPD = re.compile(r"\bGPDs?\b", re.I)
_BIPD = re.compile(r"\bBiPDs?\b", re.I)
_NEG_PRE = re.compile(r"\b(?:no|without|denies|denied|not)\b", re.I)


def _affirmed(blob: str, rx: re.Pattern) -> bool:
    """True when the pattern is present and not under a short-range negation (do not invent LPDs)."""
    m = rx.search(blob or "")
    if not m:
        return False
    pre = blob[max(0, m.start() - 48):m.start()]
    return not _NEG_PRE.search(pre)

# Orphanet: only when the extracted value/evidence already names the disease.
_ORPHA = (
    (re.compile(r"\bdravet\b", re.I), "ORPHA:33069", "Dravet syndrome"),
    (re.compile(r"\b(?:lennox[- ]gastaut|LGS)\b", re.I), "ORPHA:2382", "Lennox-Gastaut syndrome"),
    (re.compile(r"\b(?:west syndrome|infantile spasms?)\b", re.I), "ORPHA:3451", "West syndrome"),
    (re.compile(r"\b(?:tuberous sclerosis|TSC)\b", re.I), "ORPHA:805", "tuberous sclerosis complex"),
    (re.compile(r"\b(?:GLUT1|glucose transporter type 1)\b", re.I), "ORPHA:71277", "GLUT1 deficiency syndrome"),
    (re.compile(r"\b(?:Doose|EMAS|myoclonic[- ]atonic)\b", re.I), "ORPHA:1942", "epilepsy with myoclonic-atonic seizures"),
    (re.compile(r"\b(?:Landau[- ]Kleffner|LKS)\b", re.I), "ORPHA:98818", "Landau-Kleffner syndrome"),
    (re.compile(r"\bRasmussen\b", re.I), "ORPHA:1929", "Rasmussen encephalitis"),
)

_NO_ICD_PATHS = frozenset({
    "medication.drug_resistance_status",
})
_ORPHA_PATHS = (
    "clinical_seizure.etiology_specifics",
    "clinical_seizure.etiology_details_text",
    "clinical_seizure.etiology_category",
    "clinical_seizure.epilepsy_type",
)
_IED_PATHS = ("eeg.ied_findings", "eeg.ied_present")


def _val_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        parts = [str(value.get("generic_name") or ""), str(value.get("type") or ""),
                 str(value.get("value") or ""), str(value.get("ied_type") or "")]
        return " ".join(p for p in parts if p and p != "None")
    return str(getattr(value, "value", value) or "")


def _blob(value: Any, evidence: str = "") -> str:
    return f"{_val_text(value)} {evidence or ''}".strip()


def map_export_codes(field_path: str, value: Any, evidence: str = "") -> list[dict]:
    """Stable extra ids for one already-extracted claim. Empty if nothing maps."""
    path = field_path or ""
    raw = _val_text(value).strip().lower()
    blob = _blob(value, evidence)
    out: list[dict] = []

    if path in _NO_ICD_PATHS:
        return out  # ILAE DRE ≠ ICD intractable

    if path.endswith("epilepsy_type") and raw in _EPILEPSY_ICD:
        sys, cid, lab = _EPILEPSY_ICD[raw]
        out.append({"system": sys, "id": cid, "label": lab})
        sys, cid, lab = _EPILEPSY_EPSO[raw]
        out.append({"system": sys, "id": cid, "label": lab})
    elif path.endswith("predominant_seizure_type") or path.endswith("other_seizure_types"):
        if raw in _SEIZURE_ICD:
            sys, cid, lab = _SEIZURE_ICD[raw]
            out.append({"system": sys, "id": cid, "label": lab})
        if raw in _SEIZURE_EPSO:
            sys, cid, lab = _SEIZURE_EPSO[raw]
            out.append({"system": sys, "id": cid, "label": lab})

    if any(path.endswith(p.split(".", 1)[-1]) or path == p for p in _IED_PATHS):
        if raw in _IED_SCORE:
            sys, cid, lab = _IED_SCORE[raw]
            out.append({"system": sys, "id": cid, "label": lab})
        elif _affirmed(blob, _LPD):
            out.append({"system": "SCORE", "id": "LPD", "label": "lateralized periodic discharges"})
        elif _affirmed(blob, _GPD):
            out.append({"system": "SCORE", "id": "GPD", "label": "generalized periodic discharges"})
        elif _affirmed(blob, _BIPD):
            out.append({"system": "SCORE", "id": "BiPD", "label": "bilateral independent periodic discharges"})

    if any(path == p or path.endswith(p.split(".", 1)[-1]) for p in _ORPHA_PATHS):
        for rx, oid, lab in _ORPHA:
            if rx.search(blob):
                out.append({"system": "Orphanet", "id": oid, "label": lab})
                break

    # Dedup by (system, id), keep order.
    seen: set[tuple[str, str]] = set()
    uniq = []
    for row in out:
        key = (row["system"], row["id"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(row)
    return uniq


def attach_export_codes(claims: list[Any]) -> int:
    """Fill ``claim.export_codes``. Does not touch verdict, concept, or detectors. Returns n filled."""
    n = 0
    for c in claims:
        codes = map_export_codes(
            getattr(c, "field_path", None) or "",
            getattr(c, "value", None),
            getattr(getattr(c, "mention", None), "text", "") or "",
        )
        c.export_codes = codes
        n += int(bool(codes))
    return n


__all__ = ["map_export_codes", "attach_export_codes"]
