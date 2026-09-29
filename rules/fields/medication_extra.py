"""
medication_extra.py — Extra medication-module fields.

Fields populated
----------------
- ``medication.drug_resistance_status``  (Evidence[DrugResistanceStatus])  [Wave-2]
- ``medication.adverse_effects_text``    (Evidence[str])
- ``medication.non_drug_therapies``      (list[Evidence[NonDrugTherapy]])

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``jape/DrugPointInTime.jape``         — current vs past medication classifier
- ``jape/prescriptionFilter*.jape``     — adverse-effect exclusion filters
- ``Groovy/Prescription.groovy``        — output serializer

Non-ExECT sources
-----------------
- Kwan P et al. 2010 (Epilepsia 51:1069-77) — ILAE drug-resistance
  definition: failure of 2 tolerated, appropriately chosen, adequately
  dosed ASM schedules to achieve sustained seizure freedom.
- Kossoff E H et al. 2018 (Epilepsia Open 3:175-92) — ketogenic diet
  guidelines.
- Fisher R S et al. 2010 (Neurology 75:e21-27) — VNS overview.

Semantics captured
------------------
1. **drug_resistance_status** [wave-2 compound]:
   Direct trigger phrases: "drug resistant", "refractory", "medically
   intractable", "failed to respond to multiple AEDs" → DRUG_RESISTANT.
   Direct trigger for DRUG_RESPONSIVE: "seizure-free on X" combined with
   no failed_asms.
   Compound: if wave-1 medication rules produced ≥ 2 entries in
   ``medication.failed_asms``, emit DRUG_RESISTANT even without a direct
   trigger (ILAE 2010 Kwan definition).
   Otherwise UNDEFINED.

2. **adverse_effects_text**: quote sentences containing "side effects",
   "rash", "allergic", "not tolerated" if a medication entity is in the
   same or adjacent sentence.

3. **non_drug_therapies**: detect ketogenic / modified Atkins / low
   glycemic index / IVIG / plasmapheresis / steroids / rituximab / ACTH,
   with status (current/prior/failed) from surrounding tense words.

Cite: Kwan 2010; Fisher 2010; Kossoff 2018.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import (
    Certainty,
    DrugResistanceStatus,
    MedicationStatus,
    NonDrugTherapyType,
    TemporalStatus,
)
from schema.evidence import Evidence
from schema.ontology import NonDrugTherapy
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_DRUG_RESISTANT_TRIGGERS = re.compile(
    r"\bdrug[- ]?resistant\b|\brefractory\b|\bmedically\s+intractable\b|"
    r"\bintractable\s+epilepsy\b|\btreatment[- ]?resistant\b|"
    r"failed\s+(?:to\s+respond\s+to\s+)?(?:multiple|several|many|"
    r"\d+)\s+(?:anti[- ]?epileptic\s+drugs?|AEDs?|ASMs?|medications?)",
    re.IGNORECASE,
)

_DRUG_RESPONSIVE_TRIGGERS = re.compile(
    r"\bseizure[- ]?free\b|\bwell[- ]?controlled\b|"
    r"has\s+had\s+no\s+(?:further\s+)?seizures?|"
    r"no\s+seizures?\s+(?:since|for)|\bin\s+remission\b|"
    r"good\s+seizure\s+control",
    re.IGNORECASE,
)

_ADVERSE_TRIGGERS = re.compile(
    r"\b(?:side[- ]?effects?|rash(?:es)?|allergic\s+reaction|allergy|"
    r"not\s+tolerated|adverse\s+(?:effects?|reaction)|"
    r"intoleran(?:ce|t)|hypersensitivity|anaphylaxis|"
    r"Stevens[- ]?Johnson|dizziness|drowsiness|ataxia|nausea|"
    r"weight\s+(?:gain|loss)|fatigue|somnolence|sedation)\b",
    re.IGNORECASE,
)

_NON_DRUG_PATTERNS: list[tuple[re.Pattern[str], NonDrugTherapyType]] = [
    (re.compile(r"modified\s+Atkins", re.IGNORECASE),
     NonDrugTherapyType.MODIFIED_ATKINS),
    (re.compile(r"low\s+glycemic\s+index|low[- ]?glycaemic\s+index|LGIT",
                re.IGNORECASE), NonDrugTherapyType.LOW_GLYCEMIC_INDEX),
    (re.compile(r"ketogenic\s+diet|\bketo\s+diet\b", re.IGNORECASE),
     NonDrugTherapyType.KETOGENIC_DIET),
    (re.compile(r"\bIVIG\b|intravenous\s+immunoglobulin",
                re.IGNORECASE), NonDrugTherapyType.IVIG),
    (re.compile(r"plasmapheresis|plasma\s+exchange",
                re.IGNORECASE), NonDrugTherapyType.PLASMAPHERESIS),
    (re.compile(r"\bACTH\b|adrenocorticotropic\s+hormone",
                re.IGNORECASE), NonDrugTherapyType.ACTH),
    (re.compile(r"rituximab\b", re.IGNORECASE),
     NonDrugTherapyType.RITUXIMAB),
    (re.compile(r"\bsteroids?\b|methylprednisolone|prednisolone|"
                r"prednisone|dexamethasone",
                re.IGNORECASE), NonDrugTherapyType.STEROIDS),
]

_TENSE_PAST_RE = re.compile(
    r"\b(was|were|had|previously|prior|used\s+to|stopped|"
    r"discontinued|ceased|weaned)\b",
    re.IGNORECASE,
)

_TENSE_FAILED_RE = re.compile(
    r"\b(failed|ineffective|inadequate|did\s+not\s+respond)\b",
    re.IGNORECASE,
)


_NEG_PRE = re.compile(
    r"\b(?:no|without|denies?|absent|never|not|negative\s+for)\s+",
    re.IGNORECASE,
)


def _preceded_by_neg(text: str, start: int, back: int = 30) -> bool:
    return bool(_NEG_PRE.search(text[max(0, start - back):start]))


def _find_sentence_bounds(text: str, char: int) -> tuple[int, int]:
    sent_start = 0
    for m in re.finditer(r"[.!?;\n]", text[:char]):
        sent_start = m.end()
    m = re.search(r"[.!?;\n]", text[char:])
    sent_end = char + m.start() if m else len(text)
    return sent_start, sent_end


# ---------------------------------------------------------------------------
# Wave-1 Rules
# ---------------------------------------------------------------------------


class AdverseEffectsTextRule(BaseFieldRule):
    """Populate ``medication.adverse_effects_text`` with the first quoted
    sentence describing an adverse drug effect."""

    field_name = "medication.adverse_effects_text"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        if not text:
            return None

        med_char_starts = [
            e.char_start for e in entities if e.enum_class == "Medication"
        ]

        for m in _ADVERSE_TRIGGERS.finditer(text):
            if _preceded_by_neg(text, m.start()):
                continue
            sent_start, sent_end = _find_sentence_bounds(text, m.start())
            sentence = text[sent_start:sent_end]
            # Require a medication in this or an adjacent sentence.
            near_med = any(abs(cs - m.start()) < 200 for cs in med_char_starts)
            if not near_med:
                continue
            return Evidence[str](
                value=sentence.strip()[:400],
                certainty=Certainty.PROBABLE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=sentence.strip()[:400],
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=sent_start,
                char_end=sent_end,
            )
        return None


class NonDrugTherapiesRule(BaseFieldRule):
    """Populate ``medication.non_drug_therapies`` list."""

    field_name = "medication.non_drug_therapies"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[list[Evidence]]:
        text = getattr(doc, "text", "") or ""
        if not text:
            return None

        out: list[Evidence] = []
        seen: set[str] = set()

        for pat, therapy_type in _NON_DRUG_PATTERNS:
            for m in pat.finditer(text):
                if _preceded_by_neg(text, m.start()):
                    continue
                if therapy_type.value in seen:
                    continue
                sent_start, sent_end = _find_sentence_bounds(text, m.start())
                sentence = text[sent_start:sent_end]

                if _TENSE_FAILED_RE.search(sentence):
                    status = MedicationStatus.FAILED
                    temporal = TemporalStatus.HISTORICAL
                elif _TENSE_PAST_RE.search(sentence):
                    status = MedicationStatus.PRIOR
                    temporal = TemporalStatus.HISTORICAL
                else:
                    status = MedicationStatus.CURRENT
                    temporal = TemporalStatus.CURRENT

                nd = NonDrugTherapy(
                    therapy_type=therapy_type,
                    status=status,
                    response_text=sentence.strip()[:200] or None,
                )
                seen.add(therapy_type.value)
                quote = text[max(0, m.start() - 5):min(len(text), m.end() + 30)].strip()
                out.append(Evidence[NonDrugTherapy](
                    value=nd,
                    certainty=Certainty.PROBABLE,
                    temporal_status=temporal,
                    evidence_text=quote,
                    source_doc_id=meta["doc_id"],
                    source_doc_type=meta["doc_type"],
                    source_date=meta["doc_date"],
                    char_start=m.start(),
                    char_end=m.end(),
                ))

        return out or None


# ---------------------------------------------------------------------------
# Wave-2 Rule — drug resistance (reads current/prior/failed asms)
# ---------------------------------------------------------------------------


class DrugResistanceStatusRule(BaseFieldRule):
    """Populate ``medication.drug_resistance_status`` per ILAE 2010 (Kwan).

    Compound rule — reads ``pheno.medication.failed_asms`` populated by
    Phase 3a's FailedAsmsRule. Also honors direct textual triggers
    ("drug resistant", "refractory") for high-confidence assertions.
    """

    field_name = "medication.drug_resistance_status"
    phase = 2

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        pheno = getattr(self, "pheno", None)

        # 1. Direct trigger — DRUG_RESISTANT.
        m = _DRUG_RESISTANT_TRIGGERS.search(text)
        if m and not _preceded_by_neg(text, m.start()):
            return Evidence[DrugResistanceStatus](
                value=DrugResistanceStatus.DRUG_RESISTANT,
                certainty=Certainty.DEFINITE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=m.group(0),
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=m.start(),
                char_end=m.end(),
            )

        # 2. Compound Kwan check — ≥ 2 failed ASMs.
        n_failed = 0
        if pheno is not None and pheno.medication is not None:
            n_failed = len(pheno.medication.failed_asms or [])
        if n_failed >= 2:
            failed_names = ", ".join(
                str(ev.value.generic_name)
                for ev in pheno.medication.failed_asms[:3]
            )
            return Evidence[DrugResistanceStatus](
                value=DrugResistanceStatus.DRUG_RESISTANT,
                certainty=Certainty.PROBABLE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=f"≥2 failed ASMs ({failed_names}) — ILAE 2010 Kwan",
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
            )

        # 3. DRUG_RESPONSIVE — explicit trigger AND no failed ASMs.
        rm = _DRUG_RESPONSIVE_TRIGGERS.search(text)
        if rm and not _preceded_by_neg(text, rm.start()) and n_failed == 0:
            return Evidence[DrugResistanceStatus](
                value=DrugResistanceStatus.DRUG_RESPONSIVE,
                certainty=Certainty.PROBABLE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=rm.group(0),
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=rm.start(),
                char_end=rm.end(),
            )

        # 4. Otherwise UNDEFINED (per Kwan when neither criterion met and
        # patient not yet trialled on ≥2 AEDs).
        return None


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(AdverseEffectsTextRule())
register_rule(NonDrugTherapiesRule())
register_rule(DrugResistanceStatusRule())

__all__ = [
    "AdverseEffectsTextRule",
    "NonDrugTherapiesRule",
    "DrugResistanceStatusRule",
]
