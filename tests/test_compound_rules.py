"""Phase 5 acceptance tests — compound / relational rules in
``rules/compound.py``.

Hermetic tests that build a partial :class:`EpilepsyPhenotype` skeleton
directly (bypassing MedCAT + medspaCy) and assert each of the ten
compound rules produces the expected schema mutation or
``pheno._derived`` entry. Each rule gets a positive case, a negative
case, and an ambiguous / partial-evidence case.
"""

from __future__ import annotations

import logging as _lg
import sys as _sys
from datetime import date
from pathlib import Path

import pytest

# Silence PyRuSH banner.
try:  # pragma: no cover
    from loguru import logger as _loguru
    _loguru.remove()
except Exception:
    pass
_lg.disable(_lg.CRITICAL)

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_REPO_ROOT))

from rules.compound import (
    apply_compound_rules,
    derive_autoimmune_probable,
    derive_drug_resistance,
    derive_epilepsy_duration_years,
    derive_focal_to_bilateral_tc,
    derive_ilae_classification_full,
    derive_localization_concordance,
    derive_medication_currently_taking,
    derive_polytherapy_flag,
    derive_seizure_free_since,
    derive_surgery_outcome_class,
)
from schema.enums import (
    Awareness,
    CausativeAntibody,
    Certainty,
    ConcordanceStatus,
    DocumentType,
    DrugResistanceStatus,
    EngelClass,
    EpilepsyType,
    FocalMotorOnset,
    IlaeOutcome,
    Laterality,
    LobarLocalization,
    LocalizationSource,
    MedicationStatus,
    SeizureType,
    TemporalStatus,
)
from schema.evidence import DocumentMetadata, Evidence
from schema.ontology import (
    ClinicalLocalizationModule,
    ClinicalSeizureModule,
    EegModule,
    EpilepsyPhenotype,
    EtiologySpecifics,
    IntegratedPhenotypeModule,
    LobarClaim,
    Medication,
    MedicationModule,
    MriModule,
    SurgeryHistoryItem,
)


DOC_ID = "TEST_P5"
DOC_DATE = date(2024, 6, 15)


def _meta() -> dict:
    return {"doc_id": DOC_ID, "doc_type": DocumentType.PROGRESS_NOTE, "doc_date": DOC_DATE}


def _nd():
    return Evidence.not_documented(
        source_doc_id=DOC_ID,
        source_doc_type=DocumentType.PROGRESS_NOTE,
        source_date=DOC_DATE,
    )


def _ev(value, evidence_text="span", certainty=Certainty.PROBABLE,
        temporal_status=TemporalStatus.CURRENT):
    return Evidence(
        value=value,
        certainty=certainty,
        temporal_status=temporal_status,
        evidence_text=evidence_text,
        source_doc_id=DOC_ID,
        source_doc_type=DocumentType.PROGRESS_NOTE,
        source_date=DOC_DATE,
    )


def _med_ev(name: str, status: MedicationStatus,
            temporal=TemporalStatus.CURRENT, char_start=0, char_end=10):
    m = Medication(generic_name=name, status=status)
    return Evidence[Medication](
        value=m,
        certainty=Certainty.DEFINITE,
        temporal_status=temporal,
        evidence_text=name,
        source_doc_id=DOC_ID,
        source_doc_type=DocumentType.PROGRESS_NOTE,
        source_date=DOC_DATE,
        char_start=char_start,
        char_end=char_end,
    )


def _bare_pheno(text: str = "") -> EpilepsyPhenotype:
    """Build a bare phenotype skeleton with every module bootstrapped."""
    pheno = EpilepsyPhenotype(
        document=DocumentMetadata(
            doc_id=DOC_ID,
            doc_type=DocumentType.PROGRESS_NOTE,
            doc_date=DOC_DATE,
            patient_id=DOC_ID,
        ),
    )
    pheno.clinical_seizure = ClinicalSeizureModule(
        epilepsy_type=_nd(),
        predominant_seizure_type=_nd(),
        other_seizure_types=[],
        awareness=_nd(),
        semiology_text=_nd(),
        age_at_onset_years=_nd(),
        seizure_frequency=_nd(),
        other_seizure_frequencies=[],
        status_epilepticus_history=_nd(),
        etiology_category=_nd(),
        etiology_details_text=_nd(),
        etiology_specifics=_nd(),
        focal_motor_onset=_nd(),
        focal_nonmotor_onset=_nd(),
    )
    pheno.medication = MedicationModule(
        current_asms=[],
        prior_asms=[],
        failed_asms=[],
        adverse_effects_text=_nd(),
        drug_resistance_status=_nd(),
        surgery_history=[],
        non_drug_therapies=[],
    )
    pheno.mri = MriModule(
        overall_normal=_nd(),
        findings=[],
        lesion_lobe=_nd(),
        lesion_laterality=_nd(),
        hippocampal_sclerosis=_nd(),
        focal_cortical_dysplasia=_nd(),
        mri_negative_for_epilepsy=_nd(),
        field_strength_tesla=_nd(),
    )
    pheno.eeg = EegModule(
        study_type=_nd(),
        background=_nd(),
        ied_present=_nd(),
        ied_findings=[],
        seizures_captured=_nd(),
        seizures_captured_count=_nd(),
        ictal_onset_lobe=_nd(),
        ictal_onset_laterality=_nd(),
    )
    pheno.clinical_localization = ClinicalLocalizationModule(
        primary_claim=_nd(),
        alternative_claims=[],
    )
    pheno.integrated = IntegratedPhenotypeModule(
        clinical_localization=_nd(),
        eeg_localization=_nd(),
        mri_localization=_nd(),
        concordance=_nd(),
        concordance_notes_text=_nd(),
    )
    object.__setattr__(pheno, "_text", text)
    object.__setattr__(pheno, "_entities", [])
    return pheno


# ============================================================================
# 1. drug_resistance
# ============================================================================


def test_drug_resistance_direct_trigger():
    ph = _bare_pheno("Patient has drug-resistant focal epilepsy of temporal origin.")
    ev = derive_drug_resistance(ph, _meta())
    assert ev is not None
    assert ev.value == DrugResistanceStatus.DRUG_RESISTANT
    assert ph._derived["drug_resistance_detail"] == "drug_resistant"


def test_drug_resistance_kwan_two_failed():
    ph = _bare_pheno("She failed levetiracetam and failed lamotrigine.")
    ph.medication.failed_asms = [
        _med_ev("levetiracetam", MedicationStatus.FAILED),
        _med_ev("lamotrigine", MedicationStatus.FAILED),
    ]
    ph.medication.current_asms = [
        _med_ev("carbamazepine", MedicationStatus.CURRENT),
    ]
    ev = derive_drug_resistance(ph, _meta())
    assert ev is not None
    assert ev.value == DrugResistanceStatus.DRUG_RESISTANT
    assert ph._derived["drug_resistance_detail"] == "drug_resistant"


def test_drug_resistance_in_remission_two_failed_but_free():
    ph = _bare_pheno(
        "Failed levetiracetam and failed lamotrigine. Currently seizure-free "
        "on carbamazepine for 2 years."
    )
    ph.medication.failed_asms = [
        _med_ev("levetiracetam", MedicationStatus.FAILED),
        _med_ev("lamotrigine", MedicationStatus.FAILED),
    ]
    ph.medication.current_asms = [
        _med_ev("carbamazepine", MedicationStatus.CURRENT),
    ]
    ev = derive_drug_resistance(ph, _meta())
    assert ev is not None
    # Projects onto DRUG_RESPONSIVE (patient is in remission).
    assert ev.value == DrugResistanceStatus.DRUG_RESPONSIVE
    assert ph._derived["drug_resistance_detail"] == "in_remission_on_treatment"


def test_drug_resistance_responding():
    ph = _bare_pheno("On levetiracetam, seizure-free for 1 year.")
    ph.medication.current_asms = [_med_ev("levetiracetam", MedicationStatus.CURRENT)]
    ev = derive_drug_resistance(ph, _meta())
    assert ev is not None
    assert ev.value == DrugResistanceStatus.DRUG_RESPONSIVE


def test_drug_resistance_not_assessed():
    ph = _bare_pheno("Some unrelated note.")
    ev = derive_drug_resistance(ph, _meta())
    assert ev is None
    assert ph._derived.get("drug_resistance_detail") == "not_assessed"


# ============================================================================
# 2. epilepsy_duration_years
# ============================================================================


def test_duration_age_delta_positive():
    ph = _bare_pheno("She is a 35-year-old woman with epilepsy since age 15.")
    ph.clinical_seizure.age_at_onset_years = _ev(15.0, "age 15")
    result = derive_epilepsy_duration_years(ph, _meta())
    assert result == 20


def test_duration_from_text_years():
    ph = _bare_pheno("The patient has had seizures for 8 years.")
    result = derive_epilepsy_duration_years(ph, _meta())
    assert result == 8


def test_duration_from_text_months():
    ph = _bare_pheno("The patient has had epilepsy for 18 months.")
    result = derive_epilepsy_duration_years(ph, _meta())
    # 18 months → round(1.5) → 2
    assert result == 2


def test_duration_no_data():
    ph = _bare_pheno("Some unrelated note.")
    result = derive_epilepsy_duration_years(ph, _meta())
    assert result is None


# ============================================================================
# 3. medication currently-taking hygiene
# ============================================================================


def test_currently_taking_moves_discontinued():
    text = "Was on phenytoin but stopped due to gum hyperplasia. Now on lamotrigine."
    ph = _bare_pheno(text)
    # Note: phenytoin span sits within the "stopped" clause.
    phe_start = text.index("phenytoin")
    phe_end = phe_start + len("phenytoin")
    lam_start = text.index("lamotrigine")
    lam_end = lam_start + len("lamotrigine")
    ph.medication.current_asms = [
        _med_ev("phenytoin", MedicationStatus.CURRENT, char_start=phe_start, char_end=phe_end),
        _med_ev("lamotrigine", MedicationStatus.CURRENT, char_start=lam_start, char_end=lam_end),
    ]

    derive_medication_currently_taking(ph, _meta())

    current_names = {ev.value.generic_name for ev in ph.medication.current_asms}
    prior_names = {ev.value.generic_name for ev in ph.medication.prior_asms}
    assert "lamotrigine" in current_names
    assert "phenytoin" in prior_names
    # Migrated med should have status=PRIOR now.
    for ev in ph.medication.prior_asms:
        if ev.value.generic_name == "phenytoin":
            assert ev.value.status == MedicationStatus.PRIOR


def test_currently_taking_no_signal_leaves_unchanged():
    text = "Currently taking carbamazepine 200 mg twice daily."
    ph = _bare_pheno(text)
    cb_start = text.index("carbamazepine")
    cb_end = cb_start + len("carbamazepine")
    ph.medication.current_asms = [
        _med_ev("carbamazepine", MedicationStatus.CURRENT, char_start=cb_start, char_end=cb_end),
    ]
    derive_medication_currently_taking(ph, _meta())
    assert len(ph.medication.current_asms) == 1
    assert ph.medication.current_asms[0].value.generic_name == "carbamazepine"


def test_currently_taking_empty_list():
    ph = _bare_pheno("No medication data.")
    derive_medication_currently_taking(ph, _meta())
    assert ph.medication.current_asms == []
    assert ph.medication.prior_asms == []


# ============================================================================
# 4. ilae_classification_full
# ============================================================================


def test_ilae_classification_focal_motor_clonic():
    ph = _bare_pheno("Focal epilepsy with awareness of clonic left arm jerking.")
    ph.clinical_seizure.epilepsy_type = _ev(EpilepsyType.FOCAL, "focal epilepsy")
    ph.clinical_seizure.awareness = _ev(Awareness.AWARE, "aware")
    ph.clinical_seizure.predominant_seizure_type = _ev(
        SeizureType.FOCAL_AWARE, "focal aware")
    ph.clinical_seizure.focal_motor_onset = _ev(FocalMotorOnset.CLONIC, "clonic")
    result = derive_ilae_classification_full(ph, _meta())
    assert result is not None
    assert result["level_1"] == "focal"
    assert result["level_2"] == "aware"
    assert result["level_3"] == "motor"
    assert result["level_4"] == "clonic"


def test_ilae_classification_generalized_partial():
    ph = _bare_pheno("Generalized epilepsy with tonic-clonic seizures.")
    ph.clinical_seizure.epilepsy_type = _ev(EpilepsyType.GENERALIZED, "generalized")
    ph.clinical_seizure.predominant_seizure_type = _ev(
        SeizureType.GENERALIZED_TONIC_CLONIC, "GTC")
    result = derive_ilae_classification_full(ph, _meta())
    assert result is not None
    assert result["level_1"] == "generalized"
    # No focal levels for generalized epilepsy.
    assert "level_3" not in result
    assert "level_4" not in result


def test_ilae_classification_none_when_empty():
    ph = _bare_pheno("Empty.")
    result = derive_ilae_classification_full(ph, _meta())
    assert result is None


# ============================================================================
# 5. seizure_free_since
# ============================================================================


def test_seizure_free_since_duration():
    ph = _bare_pheno("The patient has been seizure-free for 6 months on lamotrigine.")
    result = derive_seizure_free_since(ph, _meta())
    assert result is not None
    assert "6" in result and "month" in result.lower()


def test_seizure_free_since_date():
    ph = _bare_pheno("Last seizure was in January 2023, no seizures since then.")
    result = derive_seizure_free_since(ph, _meta())
    assert result is not None
    assert "January 2023" in result or "2023" in result


def test_seizure_free_since_no_cue():
    ph = _bare_pheno("The patient has multiple seizures per week.")
    result = derive_seizure_free_since(ph, _meta())
    assert result is None


# ============================================================================
# 6. focal_to_bilateral_tc
# ============================================================================


def test_fbtc_promotes_focal_to_bilateral():
    text = ("She has focal impaired-awareness seizures that secondarily "
            "generalize to tonic-clonic activity.")
    ph = _bare_pheno(text)
    ph.clinical_seizure.predominant_seizure_type = _ev(
        SeizureType.FOCAL_IMPAIRED_AWARENESS, "focal impaired")
    ph.clinical_seizure.other_seizure_types = [
        _ev(SeizureType.GENERALIZED_TONIC_CLONIC, "tonic-clonic"),
    ]
    ev = derive_focal_to_bilateral_tc(ph, _meta())
    assert ev is not None
    assert ev.value == SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC
    # Mutation applied in place.
    assert ph.clinical_seizure.predominant_seizure_type.value == \
        SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC


def test_fbtc_no_linker_no_promotion():
    text = "She has focal impaired-awareness seizures. Also occasional myoclonic jerks."
    ph = _bare_pheno(text)
    ph.clinical_seizure.predominant_seizure_type = _ev(
        SeizureType.FOCAL_IMPAIRED_AWARENESS, "focal impaired")
    ev = derive_focal_to_bilateral_tc(ph, _meta())
    assert ev is None
    # Unchanged.
    assert ph.clinical_seizure.predominant_seizure_type.value == \
        SeizureType.FOCAL_IMPAIRED_AWARENESS


def test_fbtc_skip_when_already_fbtc():
    text = "Focal-to-bilateral tonic-clonic seizures."
    ph = _bare_pheno(text)
    ph.clinical_seizure.predominant_seizure_type = _ev(
        SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC, "FBTC")
    ev = derive_focal_to_bilateral_tc(ph, _meta())
    assert ev is None


def test_fbtc_skip_when_generalized():
    text = "Primary generalized tonic-clonic seizures."
    ph = _bare_pheno(text)
    ph.clinical_seizure.predominant_seizure_type = _ev(
        SeizureType.GENERALIZED_TONIC_CLONIC, "GTC")
    ev = derive_focal_to_bilateral_tc(ph, _meta())
    assert ev is None


# ============================================================================
# 7. localization_concordance
# ============================================================================


def _lobar_ev(lobe, lat, source=LocalizationSource.CLINICIAN_HYPOTHESIS):
    return _ev(LobarClaim(lobe=lobe, laterality=lat, source=source),
               evidence_text=f"{lobe.value}/{lat.value}")


def test_concordance_all_agree():
    ph = _bare_pheno("")
    ph.integrated.clinical_localization = _lobar_ev(
        LobarLocalization.TEMPORAL, Laterality.LEFT)
    ph.integrated.eeg_localization = _lobar_ev(
        LobarLocalization.TEMPORAL, Laterality.LEFT,
        LocalizationSource.EEG_CONFIRMED)
    ph.integrated.mri_localization = _lobar_ev(
        LobarLocalization.TEMPORAL, Laterality.LEFT,
        LocalizationSource.MRI_CONFIRMED)
    ev = derive_localization_concordance(ph, _meta())
    assert ev is not None
    assert ev.value == ConcordanceStatus.CONCORDANT


def test_concordance_partial_lobe_only():
    ph = _bare_pheno("")
    ph.integrated.clinical_localization = _lobar_ev(
        LobarLocalization.TEMPORAL, Laterality.LEFT)
    ph.integrated.eeg_localization = _lobar_ev(
        LobarLocalization.TEMPORAL, Laterality.RIGHT,
        LocalizationSource.EEG_CONFIRMED)
    ev = derive_localization_concordance(ph, _meta())
    assert ev is not None
    assert ev.value == ConcordanceStatus.PARTIALLY_CONCORDANT


def test_concordance_discordant():
    ph = _bare_pheno("")
    ph.integrated.clinical_localization = _lobar_ev(
        LobarLocalization.TEMPORAL, Laterality.LEFT)
    ph.integrated.eeg_localization = _lobar_ev(
        LobarLocalization.FRONTAL, Laterality.RIGHT,
        LocalizationSource.EEG_CONFIRMED)
    ev = derive_localization_concordance(ph, _meta())
    assert ev is not None
    assert ev.value == ConcordanceStatus.DISCORDANT


def test_concordance_not_assessed_single_modality():
    ph = _bare_pheno("")
    ph.integrated.clinical_localization = _lobar_ev(
        LobarLocalization.TEMPORAL, Laterality.LEFT)
    ev = derive_localization_concordance(ph, _meta())
    assert ev is not None
    assert ev.value == ConcordanceStatus.NOT_ASSESSED


# ============================================================================
# 8. surgery_outcome_class
# ============================================================================


def test_surgery_outcome_seizure_free_engel_ia():
    text = ("Underwent left anterior temporal lobectomy in 2020. "
            "Post-operatively she has been seizure-free for 3 years.")
    ph = _bare_pheno(text)
    ph.medication.surgery_history = [
        _ev(SurgeryHistoryItem(
            surgery_type=__import__("schema.enums", fromlist=["SurgeryType"]).SurgeryType.RESECTION,
            target="temporal lobe",
            laterality=Laterality.LEFT,
            year=2020,
        ), "ATL"),
    ]
    result = derive_surgery_outcome_class(ph, _meta())
    assert result is not None
    assert result["engel_class"] == "IA"
    assert result["ilae_outcome"] == "1"
    # Mutation applied to surgery history.
    assert ph.medication.surgery_history[0].value.engel_class == EngelClass.IA


def test_surgery_outcome_no_benefit():
    text = ("Underwent right frontal resection in 2018. Since surgery no improvement "
            "in seizure frequency; persistent seizures continue.")
    ph = _bare_pheno(text)
    ph.medication.surgery_history = [
        _ev(SurgeryHistoryItem(
            surgery_type=__import__("schema.enums", fromlist=["SurgeryType"]).SurgeryType.RESECTION,
            target="frontal lobe",
            laterality=Laterality.RIGHT,
            year=2018,
        ), "frontal resection"),
    ]
    result = derive_surgery_outcome_class(ph, _meta())
    assert result is not None
    assert result["engel_class"] == "IVA"


def test_surgery_outcome_none_when_no_surgery():
    ph = _bare_pheno("Post-operatively seizure-free for years.")
    result = derive_surgery_outcome_class(ph, _meta())
    assert result is None


# ============================================================================
# 9. autoimmune_probable
# ============================================================================


def test_autoimmune_probable_antibody_plus_subacute():
    ph = _bare_pheno("Subacute onset of memory loss over 6 weeks with seizures.")
    ph.clinical_seizure.etiology_specifics = _ev(
        EtiologySpecifics(causative_antibody=CausativeAntibody.ANTI_LGI1),
        "anti-LGI1 positive",
    )
    result = derive_autoimmune_probable(ph, _meta())
    assert result is True
    assert ph._derived["autoimmune_probable"] is True


def test_autoimmune_probable_no_antibody_but_mri_csf():
    ph = _bare_pheno(
        "MRI shows mesial temporal T2 hyperintensity. "
        "CSF pleocytosis with 25 lymphocytes."
    )
    result = derive_autoimmune_probable(ph, _meta())
    assert result is True


def test_autoimmune_probable_false_partial_signal():
    # Only subacute cue, no antibody, no MRI/CSF cue → False (not enough).
    ph = _bare_pheno("Subacute onset over 3 weeks.")
    result = derive_autoimmune_probable(ph, _meta())
    assert result is False


def test_autoimmune_probable_none_no_signal():
    ph = _bare_pheno("Chronic epilepsy since childhood.")
    result = derive_autoimmune_probable(ph, _meta())
    assert result is None


# ============================================================================
# 10. polytherapy_flag
# ============================================================================


def test_polytherapy_true_two_active():
    ph = _bare_pheno("")
    ph.medication.current_asms = [
        _med_ev("levetiracetam", MedicationStatus.CURRENT),
        _med_ev("lamotrigine", MedicationStatus.CURRENT),
    ]
    result = derive_polytherapy_flag(ph, _meta())
    assert result is True
    assert ph._derived["polytherapy_active_asm_count"] == 2


def test_polytherapy_false_single():
    ph = _bare_pheno("")
    ph.medication.current_asms = [
        _med_ev("levetiracetam", MedicationStatus.CURRENT),
    ]
    result = derive_polytherapy_flag(ph, _meta())
    assert result is False


def test_polytherapy_excludes_historical():
    ph = _bare_pheno("")
    ph.medication.current_asms = [
        _med_ev("levetiracetam", MedicationStatus.CURRENT),
        _med_ev("phenytoin", MedicationStatus.CURRENT,
                temporal=TemporalStatus.HISTORICAL),
    ]
    result = derive_polytherapy_flag(ph, _meta())
    # Historical med excluded → only 1 active → False.
    assert result is False


def test_polytherapy_excludes_planned_status():
    ph = _bare_pheno("")
    ph.medication.current_asms = [
        _med_ev("levetiracetam", MedicationStatus.CURRENT),
        _med_ev("valproate", MedicationStatus.PLANNED),
    ]
    result = derive_polytherapy_flag(ph, _meta())
    # PLANNED status excluded → only 1 CURRENT → False.
    assert result is False


# ============================================================================
# Dispatcher smoke test
# ============================================================================


def test_apply_compound_rules_dispatcher_runs_all_ten():
    ph = _bare_pheno("Drug-resistant focal epilepsy since age 15, currently 30.")
    ph.clinical_seizure.epilepsy_type = _ev(EpilepsyType.FOCAL, "focal")
    ph.clinical_seizure.age_at_onset_years = _ev(15.0, "age 15")
    ph.medication.failed_asms = [
        _med_ev("levetiracetam", MedicationStatus.FAILED),
        _med_ev("lamotrigine", MedicationStatus.FAILED),
    ]

    outcomes = apply_compound_rules(ph, _meta())
    # Every one of the ten rules must appear in the outcomes.
    expected_names = {
        "derive_drug_resistance",
        "derive_epilepsy_duration_years",
        "derive_medication_currently_taking",
        "derive_ilae_classification_full",
        "derive_seizure_free_since",
        "derive_focal_to_bilateral_tc",
        "derive_localization_concordance",
        "derive_surgery_outcome_class",
        "derive_autoimmune_probable",
        "derive_polytherapy_flag",
    }
    assert expected_names.issubset(set(outcomes.keys()))
    # Drug resistance direct trigger should populate.
    assert outcomes["derive_drug_resistance"] == "populated"
    # Concordance should have run (fallback = NOT_ASSESSED).
    assert outcomes["derive_localization_concordance"] == "populated"
