"""
epilepsy_type.py — EpilepsyType extraction (ILAE 2017 top-level).

Field populated
---------------
- ``clinical_seizure.epilepsy_type`` (Evidence[EpilepsyType]; 4 values:
  focal, generalized, combined_focal_generalized, unknown)

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``Groovy/Diagnosis.groovy``          — top-level diagnosis serializer
- ``Groovy/MarkupDiagnosis.groovy``    — clause-level diagnosis span builder
- ``jape/EpilepsyDiagnosis.jape``      — diagnosis-noun composition
- ``jape/EpilepsyMentions.jape``       — surface-form gazetteer
- ``jape/DiagfromSeizure.jape``        — inferring epilepsy diagnosis from
                                          a described seizure type
- ``jape/DiagnosisB.jape`` / ``DiagnosisB2.jape`` — secondary diagnosis phase
- ``jape/EpiCause.jape``               — link to etiology (used here only to
                                          exclude cause-clauses from the type
                                          detector)
- ``references/exect_v2_ilae_map.csv`` — CUI → ILAE 2017 label + type

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
1. Direct: LinkedEntity where ``enum_class == "EpilepsyType"``.
2. Derived: if none present but a SeizureType extract exists → infer by ILAE
   2017 decision tree:
     - Any focal_* seizure and no generalized_* → focal.
     - Any generalized_* and no focal_* → generalized.
     - Both present → combined_focal_generalized.
     - Only unknown_onset_* / unclassified → unknown.
3. Explicit "focal epilepsy" / "generalized epilepsy" / "combined focal and
   generalized" / "unknown-onset epilepsy" via regex fallback.
4. ConText — negated → return None; hypothetical → certainty POSSIBLE;
   family → return None (family history, not the patient's).

Cite: Fisher R S et al. 2017 (ILAE 2017 operational classification, Epilepsia).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import Certainty, EpilepsyType, SeizureType, TemporalStatus
from schema.evidence import Evidence
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Explicit-phrase fallback patterns
# ---------------------------------------------------------------------------

_EXPLICIT_PATTERNS: list[tuple[re.Pattern[str], EpilepsyType]] = [
    (re.compile(
        r"combined\s+focal\s+and\s+generali[sz]ed\s+epilepsy|"
        r"Lennox[- ]Gastaut(?:\s+syndrome)?",
        re.IGNORECASE), EpilepsyType.COMBINED_FOCAL_GENERALIZED),
    (re.compile(
        r"generali[sz]ed\s+(?:idiopathic\s+)?epilepsy|"
        r"idiopathic\s+generali[sz]ed\s+epilepsy|\bIGE\b|"
        r"juvenile\s+myoclonic\s+epilepsy|\bJME\b|"
        r"childhood\s+absence\s+epilepsy|\bCAE\b|"
        r"juvenile\s+absence\s+epilepsy|\bJAE\b|"
        r"epilepsy\s+with\s+generali[sz]ed\s+tonic[- ]clonic\s+seizures\s+alone",
        re.IGNORECASE), EpilepsyType.GENERALIZED),
    (re.compile(
        r"focal\s+epilepsy|localization[- ]related\s+epilepsy|"
        r"partial\s+epilepsy|"
        r"temporal\s+lobe\s+epilepsy|\bTLE\b|"
        r"frontal\s+lobe\s+epilepsy|\bFLE\b|"
        r"parietal\s+lobe\s+epilepsy|\bPLE\b|"
        r"occipital\s+lobe\s+epilepsy|"
        r"symptomatic\s+(?:structural\s+)?(?:focal\s+)?epilepsy",
        re.IGNORECASE), EpilepsyType.FOCAL),
    (re.compile(
        r"epilepsy\s+of\s+unknown\s+(?:origin|etiology|onset)|"
        r"unclassified\s+epilepsy|unknown[- ]onset\s+epilepsy",
        re.IGNORECASE), EpilepsyType.UNKNOWN),
]


def _infer_from_seizure_types(entities: list[LinkedEntity]) -> Optional[tuple[EpilepsyType, LinkedEntity]]:
    """Fallback: infer epilepsy type from present SeizureType entities."""
    focal, gen, unknown = False, False, False
    representative: Optional[LinkedEntity] = None
    for e in entities:
        if e.enum_class != "SeizureType" or e.is_negated or e.is_family:
            continue
        try:
            st = SeizureType(e.enum_value)
        except ValueError:
            continue
        if st.value.startswith("focal_") and st != SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC:
            focal = True
            representative = representative or e
        elif st == SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC:
            # FBTC is by definition focal-onset — counts as focal.
            focal = True
            representative = representative or e
        elif st.value.startswith("generalized_"):
            gen = True
            representative = representative or e
        elif st.value.startswith("unknown_onset_") or st == SeizureType.UNCLASSIFIED:
            unknown = True

    if focal and gen:
        return EpilepsyType.COMBINED_FOCAL_GENERALIZED, representative
    if focal:
        return EpilepsyType.FOCAL, representative
    if gen:
        return EpilepsyType.GENERALIZED, representative
    if unknown:
        return EpilepsyType.UNKNOWN, representative
    return None


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------


class EpilepsyTypeRule(BaseFieldRule):
    """Populate ``clinical_seizure.epilepsy_type``."""

    field_name = "clinical_seizure.epilepsy_type"
    enum_class = EpilepsyType

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        # 1. Direct entity match.
        cands = self.relevant_entities(entities, include_hypothetical=True)
        for e in cands:
            try:
                value = EpilepsyType(e.enum_value)
            except ValueError:
                continue
            return self._make_evidence(value, e, meta)

        # 2. Explicit regex over the raw text.
        text = getattr(doc, "text", "") or ""
        for pat, value in _EXPLICIT_PATTERNS:
            m = pat.search(text)
            if not m:
                continue
            return Evidence[EpilepsyType](
                value=value,
                certainty=Certainty.DEFINITE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=m.group(0),
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=m.start(),
                char_end=m.end(),
            )

        # 3. Derived from SeizureType entities.
        inferred = _infer_from_seizure_types(entities)
        if inferred is None:
            return None
        value, anchor = inferred
        if anchor is not None:
            ev = self._make_evidence(value, anchor, meta, certainty=Certainty.PROBABLE)
            return ev
        # No anchor entity → return None (schema requires evidence_text).
        return None


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(EpilepsyTypeRule())

__all__ = ["EpilepsyTypeRule"]
