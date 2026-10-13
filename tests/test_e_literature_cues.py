"""Held-out cue tests for leftover literature-backed E strings.

Snippets here were not used to tune the v4_ext EEG-skip rules. Each block
cites one paper or standard and checks one pattern. No new ontology.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from rules.asm_lexicon import RXNORM_RELEASE
from rules.asm_us_brand_aliases import leftover_brand_matches
from rules.context_config import _US_ADDITIONS
from rules.fields.eeg import _EEG_CONTEXT_RE, _IED_FALLBACK, _collect_ieds, _sentence_negates_ied
from rules.fields.eeg_extra import _STUDY_TYPE_PATTERNS, _study_type_asserted
from rules.fields.focal_onset import _EVOLUTION_RE
from rules.fields.medication import (
    _extract_medications, _infer_status, canonicalize_drug_name, is_eeg_study_token,
)
from rules.fields.seizure_type import _fallback_seizure_matches
from schema.enums import (
    DocumentType,
    EegStudyType,
    IedType,
    MedicationStatus,
    SeizureType,
)


_META = {
    "doc_id": "heldout_e_cues",
    "doc_type": DocumentType.PROGRESS_NOTE,
    "doc_date": date(2020, 1, 1),
}


def _doc(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


# --- Hirsch et al. 2013 (ACNS EEG terms) -----------------------------------

def test_acns_ltm_and_ceeg_are_prolonged():
    for text in ("LTM was performed for 48 hours.", "cEEG in the ICU showed no seizures."):
        hits = [
            val for pat, val in _STUDY_TYPE_PATTERNS
            for m in pat.finditer(text) if _study_type_asserted(text, m)
        ]
        assert EegStudyType.PROLONGED in hits, text


def test_acns_outpatient_eeg_is_routine():
    text = "Outpatient EEG was performed last week."
    hits = [
        val for pat, val in _STUDY_TYPE_PATTERNS
        for m in pat.finditer(text) if _study_type_asserted(text, m)
    ]
    assert EegStudyType.ROUTINE in hits


def test_acns_lpds_count_as_ied_other():
    text = "EEG showed left hemisphere LPDs at 1 Hz."
    assert _EEG_CONTEXT_RE.search(text)
    hits = _collect_ieds([], _doc(text))
    assert hits
    assert hits[0][0] == IedType.OTHER
    assert any(pat.search(text) for pat, kind in _IED_FALLBACK if kind == IedType.OTHER)


def test_acns_negated_lpds_are_not_ieds():
    text = ("Specifically, there were no temporal sharp waves, spikes, "
            "spike-and-wave discharges, TIRDA, LPDs, or GPDs.")
    assert _sentence_negates_ied(text, text.index("LPDs"), text.index("LPDs") + 4)
    hits = _collect_ieds([], _doc("EEG report. " + text))
    assert not any(h[0] == IedType.OTHER for h in hits)


# --- RxNorm (rxnorm:2026-09-08) + FDA leftover brands ----------------------

def test_rxnorm_release_is_pinned():
    assert RXNORM_RELEASE == "rxnorm:2026-09-08"


def test_leftover_fda_brands_canonicalize():
    assert canonicalize_drug_name("Stavzor") == "sodiumvalproate"
    assert canonicalize_drug_name("Equetro") == "carbamazepine"
    assert canonicalize_drug_name("Carnexiv") == "carbamazepine"
    assert canonicalize_drug_name("Tegretol XR") == "carbamazepine"
    assert canonicalize_drug_name("Keppra XR") == "levetiracetam"
    assert canonicalize_drug_name("Lamictal ODT") == "lamotrigine"


def test_eeg_study_tokens_are_not_drugs():
    assert is_eeg_study_token("LTM")
    assert is_eeg_study_token("VEEG")
    assert is_eeg_study_token("cEEG")
    assert is_eeg_study_token("EMU")
    assert not is_eeg_study_token("Keppra")
    current, prior, failed = _extract_medications(
        [], _doc("If she develops another breakthrough seizure, escalate to LTM."), _META)
    assert current == prior == failed == []


def test_leftover_fda_brand_extracted_without_medcat():
    text = "Current ASM: Stavzor 250 mg BID."
    assert leftover_brand_matches(text)
    current, prior, failed = _extract_medications([], _doc(text), _META)
    assert not prior and not failed
    assert current and current[0].value.generic_name == "sodiumvalproate"
    assert current[0].value.status == MedicationStatus.CURRENT


# --- Uzuner 2010 / Chapman 2001: discontinued or planned, not current ------

def test_dc_mark_is_prior_not_current():
    assert _infer_status("Keppra was d/c'd last month.") == MedicationStatus.PRIOR
    assert _infer_status("Vimpat dc'd due to cost.") == MedicationStatus.PRIOR


def test_will_start_is_planned_not_current():
    assert _infer_status("Will start Vimpat next week.") == MedicationStatus.PLANNED
    assert _infer_status("We will begin lacosamide if seizures persist.") == MedicationStatus.PLANNED


def test_home_meds_stay_current():
    assert _infer_status("Home meds: Keppra 500 mg BID.") == MedicationStatus.CURRENT


def test_context_has_i2b2_leftover_cues():
    literals = {lit.lower() for lit, _cat, _dir, _meta in _US_ADDITIONS}
    assert "d/c'd" in literals
    assert "will start" in literals
    assert "home meds" not in literals


# --- Fisher 2017 / Berg 2010 leftover aliases ------------------------------

def test_berg_psychomotor_and_hyphen_complex_partial_are_fia():
    hits = _fallback_seizure_matches("Psychomotor seizures two times a week.")
    assert hits and hits[0][0] == SeizureType.FOCAL_IMPAIRED_AWARENESS
    hits = _fallback_seizure_matches("Complex-partial seizures continue.")
    assert hits and hits[0][0] == SeizureType.FOCAL_IMPAIRED_AWARENESS


def test_fisher_partial_onset_and_secondarily_generalized():
    hits = _fallback_seizure_matches("Partial-onset seizures since childhood.")
    assert hits and hits[0][0] == SeizureType.FOCAL_UNKNOWN_AWARENESS
    hits = _fallback_seizure_matches("Secondarily generalized seizures at night.")
    assert hits and hits[0][0] == SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC


def test_fisher_thereafter_is_evolution_not_onset():
    sent = "Focal seizures begin with an epigastric rising sensation, thereafter clonic jerking."
    assert _EVOLUTION_RE.search(sent)


# --- Fonferko-Shadrach 2024 leftover EEG skip ------------------------------

def test_exect_pending_or_not_yet_obtained_is_not_asserted():
    for text in (
        "Routine EEG is pending.",
        "Video-EEG has not yet been obtained.",
        "Ambulatory EEG is to be scheduled next month.",
    ):
        asserted = [
            m for pat, _val in _STUDY_TYPE_PATTERNS
            for m in pat.finditer(text) if _study_type_asserted(text, m)
        ]
        assert asserted == [], text
