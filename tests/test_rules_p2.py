"""Phase 3b acceptance tests — P2 rules in ``rules/fields/``.

Consolidated tests for the 16 P2 fields extending the Phase 3a foundation.
Each rule gets 3 cases minimum (positive + negation + historical/hypothetical
or edge case). Uses a session-scoped ``PhenotypeAssembler`` shared across the
whole Phase 3b test module for load-once economy.

Categories covered
------------------
1. awareness
2. focal_motor_onset + focal_nonmotor_onset + semiology_text
3. status_epilepticus_history
4. clinical_localization.primary_claim + alternative_claims + concordance
5. medication.drug_resistance_status + adverse_effects_text + non_drug_therapies
6. mri.lesion_lobe + lesion_laterality + field_strength_tesla
7. eeg.study_type + seizures_captured + ictal_onset_lobe + ictal_onset_laterality
8. medication.surgery_history
9. clinical_seizure.etiology_specifics (CausativeAntibody)
"""

from __future__ import annotations

import logging as _lg_mod
import sys as _sys
from datetime import date as _date
from pathlib import Path as _Path

import pytest

# Silence PyRuSH debug noise.
try:  # pragma: no cover
    from loguru import logger as _loguru
    _loguru.remove()
except Exception:
    pass
_lg_mod.disable(_lg_mod.CRITICAL)

_REPO_ROOT = _Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_REPO_ROOT))

from rules.context_config import build_medspacy_pipeline  # noqa: E402
from schema.enums import (  # noqa: E402
    Awareness as _Aw,
    CausativeAntibody as _Ab,
    Certainty as _Certainty,
    ConcordanceStatus as _Conc,
    DocumentType as _DocType,
    DrugResistanceStatus as _DR,
    EegStudyType as _EegST,
    FocalMotorOnset as _FM,
    FocalNonmotorOnset as _FN,
    Laterality as _Lat,
    LobarLocalization as _Lobe,
    SurgeryType as _Surg,
)
from services.medcat_extractor import MedCATExtractor as _MedCATExtractor  # noqa: E402
from services.phenotype_assembler import PhenotypeAssembler as _Assembler  # noqa: E402
import rules.fields as _rules_fields  # noqa: F401, E402 — registers rules


@pytest.fixture(scope="module")
def _p3b_assembler() -> "_Assembler":
    cdb = str(_REPO_ROOT / "data" / "medcat_cdb_epilepsy" / "cdb")
    ex = _MedCATExtractor(cdb, verbose=False)
    nlp = build_medspacy_pipeline()
    return _Assembler(ex, nlp=nlp)


@pytest.fixture()
def run_p2(_p3b_assembler):
    def _run(text: str, doc_id: str = "TEST_P2"):
        return _p3b_assembler.process(
            text, doc_id=doc_id,
            doc_type=_DocType.PROGRESS_NOTE,
            doc_date=_date(2020, 1, 1),
            patient_id=doc_id,
        )
    return _run


# ===========================================================================
# 1. Awareness
# ===========================================================================


def test_p3b_awareness_impaired(run_p2):
    text = ("Seizure type: focal seizures with loss of awareness lasting "
            "one to two minutes.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.awareness
    assert ev.value == _Aw.IMPAIRED, f"expected impaired, got {ev.value}"


def test_p3b_awareness_aware(run_p2):
    text = ("The patient has simple partial seizures with retained awareness "
            "throughout.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.awareness
    assert ev.value == _Aw.AWARE


def test_p3b_awareness_none_outside_seizure(run_p2):
    text = ("The patient was fully aware of the diagnosis. No seizures noted.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.awareness
    # Should not fire — no seizure context in the sentence with "aware".
    # Either NOT_DOCUMENTED or POSSIBLE at most.
    assert ev.value is None or ev.certainty in (
        _Certainty.POSSIBLE, _Certainty.NOT_DOCUMENTED,
    )


# ===========================================================================
# 2. Focal motor / nonmotor / semiology_text
# ===========================================================================


def test_p3b_focal_motor_myoclonic(run_p2):
    text = ("Focal seizures with myoclonic jerks of the right arm.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.focal_motor_onset
    assert ev.value == _FM.MYOCLONIC


def test_p3b_focal_motor_automatisms(run_p2):
    text = ("Focal impaired-awareness seizures with lip-smacking automatisms "
            "and picking at clothing.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.focal_motor_onset
    assert ev.value == _FM.AUTOMATISMS


def test_p3b_focal_nonmotor_sensory(run_p2):
    text = ("Focal aware seizures beginning with an unusual smell aura.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.focal_nonmotor_onset
    assert ev.value == _FN.SENSORY


def test_p3b_focal_nonmotor_cognitive(run_p2):
    text = ("Focal seizures with déjà vu and a feeling of memory disturbance.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.focal_nonmotor_onset
    assert ev.value == _FN.COGNITIVE


def test_p3b_semiology_text_captured(run_p2):
    text = ("Seizure type and frequency: focal seizures with loss of "
            "awareness. During them, she smells burnt rubber and has an "
            "epigastric rising. She then loses consciousness for a couple "
            "of minutes.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.semiology_text
    assert ev.value is not None
    assert len(ev.value) > 10


def test_p3b_focal_motor_not_on_generalized(run_p2):
    text = ("Diagnosis: generalized tonic-clonic seizures with myoclonic "
            "jerks. Juvenile myoclonic epilepsy.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.focal_motor_onset
    # Should not fire — no focal context in this generalized-only note.
    assert ev.value is None or ev.certainty == _Certainty.NOT_DOCUMENTED


# ===========================================================================
# 3. Status epilepticus history
# ===========================================================================


def test_p3b_status_epilepticus_positive(run_p2):
    text = ("The patient presented in convulsive status epilepticus "
            "requiring ICU admission.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.status_epilepticus_history
    assert ev.value is True


def test_p3b_status_epilepticus_history(run_p2):
    text = ("Patient has a history of status epilepticus in 2015.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.status_epilepticus_history
    assert ev.value is True


def test_p3b_status_epilepticus_negated(run_p2):
    text = ("No history of status epilepticus. Occasional focal seizures only.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.status_epilepticus_history
    assert ev.value is False


# ===========================================================================
# 4. Clinical localization
# ===========================================================================


def test_p3b_primary_claim_temporal_right(run_p2):
    text = ("Diagnosis: right temporal lobe epilepsy. EEG shows right "
            "temporal spikes.")
    pheno = run_p2(text)
    ev = pheno.clinical_localization.primary_claim
    assert ev.value is not None
    assert ev.value.lobe == _Lobe.TEMPORAL
    assert ev.value.laterality == _Lat.RIGHT


def test_p3b_concordance_concordant(run_p2):
    text = ("Clinical diagnosis: left temporal lobe epilepsy. "
            "EEG shows left temporal spikes and sharp waves. "
            "MRI brain: left hippocampal sclerosis with mesial temporal "
            "atrophy.")
    pheno = run_p2(text)
    ev = pheno.integrated.concordance
    assert ev.value in (_Conc.CONCORDANT, _Conc.PARTIALLY_CONCORDANT)


def test_p3b_concordance_not_assessed(run_p2):
    text = ("The patient has focal seizures.")
    pheno = run_p2(text)
    ev = pheno.integrated.concordance
    # Only clinical claim (if any); definitely not enough for concordance.
    assert ev.value in (_Conc.NOT_ASSESSED, None)


# ===========================================================================
# 5. Medication extras
# ===========================================================================


def test_p3b_drug_resistant_direct_trigger(run_p2):
    text = ("Diagnosis: drug-resistant focal epilepsy of temporal lobe origin.")
    pheno = run_p2(text)
    ev = pheno.medication.drug_resistance_status
    assert ev.value == _DR.DRUG_RESISTANT


def test_p3b_drug_resistant_compound_2_failed(run_p2):
    text = ("She has failed levetiracetam and failed lamotrigine due to "
            "inadequate seizure control. Now on carbamazepine.")
    pheno = run_p2(text)
    ev = pheno.medication.drug_resistance_status
    # Should trigger DRUG_RESISTANT via the compound rule.
    assert ev.value == _DR.DRUG_RESISTANT


def test_p3b_drug_responsive(run_p2):
    text = ("On sodium valproate 400 mg BD, seizure-free for 3 years.")
    pheno = run_p2(text)
    ev = pheno.medication.drug_resistance_status
    assert ev.value in (_DR.DRUG_RESPONSIVE, None)


def test_p3b_adverse_effects_captured(run_p2):
    text = ("She was on carbamazepine but developed a Stevens-Johnson rash "
            "and was switched to lamotrigine.")
    pheno = run_p2(text)
    ev = pheno.medication.adverse_effects_text
    assert ev.value is not None
    assert "rash" in ev.value.lower() or "stevens" in ev.value.lower()


def test_p3b_non_drug_therapy_keto(run_p2):
    text = ("The patient was started on the ketogenic diet with some "
            "improvement in seizure frequency.")
    pheno = run_p2(text)
    therapies = [e.value.therapy_type for e in pheno.medication.non_drug_therapies]
    from schema.enums import NonDrugTherapyType as _NDT
    assert _NDT.KETOGENIC_DIET in therapies


# ===========================================================================
# 6. MRI extras
# ===========================================================================


def test_p3b_mri_lesion_lobe_and_laterality(run_p2):
    text = ("MRI brain: right hippocampal sclerosis with volume loss.")
    pheno = run_p2(text)
    lobe_ev = pheno.mri.lesion_lobe
    lat_ev = pheno.mri.lesion_laterality
    assert lobe_ev.value == _Lobe.TEMPORAL
    assert lat_ev.value == _Lat.RIGHT


def test_p3b_mri_field_strength_3t(run_p2):
    text = ("MRI performed on 3T scanner with epilepsy protocol.")
    pheno = run_p2(text)
    ev = pheno.mri.field_strength_tesla
    assert ev.value == 3.0


def test_p3b_mri_field_strength_7t(run_p2):
    text = ("Follow-up 7T MRI shows subtle FCD in left frontal region.")
    pheno = run_p2(text)
    ev = pheno.mri.field_strength_tesla
    assert ev.value == 7.0


# ===========================================================================
# 7. EEG extras
# ===========================================================================


def test_p3b_eeg_study_type_video(run_p2):
    text = ("48-hour video-EEG monitoring in the EMU captured 3 typical "
            "seizures.")
    pheno = run_p2(text)
    ev = pheno.eeg.study_type
    assert ev.value in (_EegST.VIDEO_EEG, _EegST.EMU)


def test_p3b_eeg_seizures_captured_positive(run_p2):
    text = ("Prolonged EEG: 3 clinical seizures were captured over "
            "48 hours.")
    pheno = run_p2(text)
    ev = pheno.eeg.seizures_captured
    count_ev = pheno.eeg.seizures_captured_count
    assert ev.value is True
    assert count_ev.value == 3


def test_p3b_eeg_seizures_captured_none(run_p2):
    text = ("Video-EEG for 24 hours: no seizures were captured.")
    pheno = run_p2(text)
    ev = pheno.eeg.seizures_captured
    assert ev.value is False


def test_p3b_eeg_ictal_onset_left_frontal(run_p2):
    text = ("Video-EEG captured 2 seizures with ictal onset from the "
            "left frontal region.")
    pheno = run_p2(text)
    lobe_ev = pheno.eeg.ictal_onset_lobe
    lat_ev = pheno.eeg.ictal_onset_laterality
    assert lobe_ev.value == _Lobe.FRONTAL
    assert lat_ev.value == _Lat.LEFT


@pytest.mark.parametrize("text", [
    "Video-EEG captured no seizures, so the ictal onset could not be localised to the left temporal lobe.",
    "No ictal onset zone was identified; interictal spikes arose from the right frontal region.",
    "Admission to the EMU is recommended to localise the ictal onset in the left temporal lobe.",
    "She was referred for video-EEG to define the seizure onset in the right frontal lobe.",
])
def test_eeg_ictal_onset_not_reported_when_not_found_or_only_planned(run_p2, text):
    pheno = run_p2("EEG report. " + text)
    assert pheno.eeg.ictal_onset_lobe.value is None
    assert pheno.eeg.ictal_onset_laterality.value is None


@pytest.mark.parametrize("text", [
    "Video-EEG is recommended to characterise her events.",
    "She was referred for an EMU admission.",
    "Stored ECoG was not available for review.",
    "No video-EEG has been performed.",
    "If seizures persist we would consider ambulatory EEG.",
])
def test_eeg_study_type_not_reported_for_advice_plans_or_absent_studies(run_p2, text):
    pheno = run_p2(text)
    assert pheno.eeg.study_type.value is None


def test_eeg_study_type_still_found_when_done_even_with_a_later_negation(run_p2):
    pheno = run_p2("Routine EEG was performed. No seizures were captured. Video-EEG is recommended next.")
    assert pheno.eeg.study_type.value == _EegST.ROUTINE


# ===========================================================================
# 8. Surgery history
# ===========================================================================


def test_p3b_surgery_temporal_lobectomy(run_p2):
    text = ("Prior right anterior temporal lobectomy in 2015, Engel IA at "
            "5-year follow-up.")
    pheno = run_p2(text)
    surgeries = pheno.medication.surgery_history
    assert len(surgeries) >= 1
    s = surgeries[0].value
    assert s.surgery_type == _Surg.RESECTION
    assert s.year == 2015


def test_p3b_surgery_vns_implant(run_p2):
    text = ("VNS implant placed in 2018 for drug-resistant epilepsy.")
    pheno = run_p2(text)
    surg_types = [e.value.surgery_type for e in pheno.medication.surgery_history]
    assert _Surg.NEUROSTIMULATION_VNS in surg_types


def test_p3b_surgery_no_history(run_p2):
    text = ("No history of epilepsy surgery. On lamotrigine 200 mg BD.")
    pheno = run_p2(text)
    assert len(pheno.medication.surgery_history) == 0


def test_p3b_surgery_rns(run_p2):
    text = ("NeuroPace RNS system implanted with leads in left mesial "
            "temporal lobe.")
    pheno = run_p2(text)
    surg_types = [e.value.surgery_type for e in pheno.medication.surgery_history]
    assert _Surg.NEUROSTIMULATION_RNS in surg_types


# ===========================================================================
# 9. Autoimmune (etiology_specifics)
# ===========================================================================


def test_p3b_autoimmune_nmdar(run_p2):
    text = ("Anti-NMDAR antibody positive; autoimmune encephalitis diagnosed.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.etiology_specifics
    assert ev.value is not None
    assert ev.value.causative_antibody == _Ab.ANTI_NMDAR


def test_p3b_autoimmune_lgi1(run_p2):
    text = ("Anti-LGI1 encephalitis with faciobrachial dystonic seizures.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.etiology_specifics
    assert ev.value is not None
    assert ev.value.causative_antibody == _Ab.ANTI_LGI1


def test_p3b_autoimmune_gad65(run_p2):
    text = ("GAD65-associated epilepsy confirmed by serum autoantibody.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.etiology_specifics
    assert ev.value is not None
    assert ev.value.causative_antibody == _Ab.ANTI_GAD65


def test_p3b_autoimmune_negated(run_p2):
    text = ("Negative for NMDAR antibody. Otherwise unremarkable workup.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.etiology_specifics
    # Negated → should not populate the antibody field.
    if ev.value is not None:
        assert ev.value.causative_antibody != _Ab.ANTI_NMDAR


def test_p3b_genetic_scn1a(run_p2):
    text = ("Genetic testing revealed a pathogenic SCN1A variant, "
            "consistent with Dravet syndrome.")
    pheno = run_p2(text)
    ev = pheno.clinical_seizure.etiology_specifics
    assert ev.value is not None
    assert ev.value.causative_gene == "SCN1A"


# ===========================================================================
# 10. Cross-cutting: two-wave dispatch
# ===========================================================================


def test_p3b_two_wave_dispatch_drug_resistance_uses_failed_asms(run_p2):
    """Confirm the wave-2 drug_resistance rule reads wave-1 failed_asms."""
    text = ("She has failed levetiracetam, failed lamotrigine, and failed "
            "carbamazepine.")
    pheno = run_p2(text)
    n_failed = len(pheno.medication.failed_asms)
    assert n_failed >= 2, f"expected ≥ 2 failed ASMs, got {n_failed}"
    ev = pheno.medication.drug_resistance_status
    assert ev.value == _DR.DRUG_RESISTANT


def test_onset_stated_is_reported(run_p2):
    ph = run_p2("Focal seizures begin with clonic jerking of the right hand, then he becomes unresponsive.")
    assert ph.clinical_seizure.focal_motor_onset.value == _FM.CLONIC
    ph = run_p2("Focal seizures start with a sudden wave of fear, then lip smacking.")
    assert ph.clinical_seizure.focal_nonmotor_onset.value == _FN.EMOTIONAL


def test_later_evolution_is_not_onset(run_p2):
    ph = run_p2("Focal seizures begin with an epigastric rising sensation, followed by clonic jerking of the arm.")
    assert ph.clinical_seizure.focal_motor_onset.value is None
    assert ph.clinical_seizure.focal_nonmotor_onset.value == _FN.AUTONOMIC


def test_planned_or_negated_or_family_is_not_reported(run_p2):
    ph = run_p2("Recommend describing whether focal seizures begin with automatisms.")
    assert ph.clinical_seizure.focal_motor_onset.value is None
    ph = run_p2("No focal seizures with myoclonic jerks. This is generalized epilepsy.")
    assert ph.clinical_seizure.focal_motor_onset.value is None
    ph = run_p2("Mother has focal seizures beginning with fear.")
    assert ph.clinical_seizure.focal_nonmotor_onset.value is None


def test_aura_is_nonmotor_onset(run_p2):
    ph = run_p2("Focal aware seizures. Aura of an unusual smell, then impaired awareness.")
    assert ph.clinical_seizure.focal_nonmotor_onset.value == _FN.SENSORY
