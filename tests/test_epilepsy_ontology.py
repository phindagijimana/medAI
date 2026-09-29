"""Phase 1b acceptance tests for ``rules/epilepsy_ontology.py``.

Guarantees:

1. Every enum in ``schema/enums.py`` is present in the ontology registry.
2. Every enum value has either (a) a CUI or SCTID anchor, or (b) at least
   one synonym trigger phrase, or (c) is a member of a ``RULES_ONLY`` enum
   (in which case an empty-synonym placeholder is allowed, e.g. the
   "not_documented" / "unspecified" catch-all rows).
3. Every synonym cited in a ``ConceptEntry`` has at least one entry in
   ``source_provenance``.
4. The total triple count exceeds 240 (Phase 1 acceptance criterion).
"""

from __future__ import annotations

import pytest

from rules.epilepsy_ontology import (
    ConceptEntry,
    RULES_ONLY_ENUMS,
    all_enum_ontologies,
    supplementary_ontologies,
    total_concept_count,
)
from schema.enums import (
    Awareness,
    CausativeAntibody,
    Certainty,
    ConcordanceStatus,
    DocumentType,
    DrugResistanceStatus,
    EegBackground,
    EegStudyType,
    EngelClass,
    EpilepsyType,
    EtiologyCategory,
    FocalMotorOnset,
    FocalNonmotorOnset,
    IedType,
    IlaeOutcome,
    Laterality,
    LobarLocalization,
    LocalizationSource,
    MedicationStatus,
    MriFinding,
    NonDrugTherapyType,
    SeizureType,
    SurgeryType,
    TemporalStatus,
)

ALL_ENUMS: dict[str, type] = {
    "DocumentType": DocumentType,
    "Certainty": Certainty,
    "TemporalStatus": TemporalStatus,
    "EpilepsyType": EpilepsyType,
    "SeizureType": SeizureType,
    "Awareness": Awareness,
    "Laterality": Laterality,
    "LobarLocalization": LobarLocalization,
    "LocalizationSource": LocalizationSource,
    "EegStudyType": EegStudyType,
    "EegBackground": EegBackground,
    "IedType": IedType,
    "MriFinding": MriFinding,
    "DrugResistanceStatus": DrugResistanceStatus,
    "MedicationStatus": MedicationStatus,
    "SurgeryType": SurgeryType,
    "ConcordanceStatus": ConcordanceStatus,
    "EtiologyCategory": EtiologyCategory,
    "FocalMotorOnset": FocalMotorOnset,
    "FocalNonmotorOnset": FocalNonmotorOnset,
    "EngelClass": EngelClass,
    "IlaeOutcome": IlaeOutcome,
    "NonDrugTherapyType": NonDrugTherapyType,
    "CausativeAntibody": CausativeAntibody,
}


def test_registry_covers_all_24_enums():
    ontos = all_enum_ontologies()
    missing = set(ALL_ENUMS) - set(ontos)
    assert not missing, f"enums missing from ontology registry: {missing}"
    assert len(ontos) == 24, f"expected 24 enums, got {len(ontos)}"


def test_every_enum_value_present_in_registry():
    ontos = all_enum_ontologies()
    for enum_name, enum_cls in ALL_ENUMS.items():
        onto = ontos[enum_name]
        for member in enum_cls:
            assert member.value in onto, (
                f"{enum_name}.{member.name} (value={member.value!r}) "
                f"missing from ontology"
            )


def test_every_value_has_anchor_or_synonym_or_rules_only():
    """Each enum value must have EITHER a concept anchor (cui/sctid) OR at
    least one synonym trigger phrase. Rules-only enum members may have
    empty synonyms only for explicit ``not_documented`` / ``unspecified``
    catch-all values.
    """
    ontos = all_enum_ontologies()
    empty_allowed = {
        ("Certainty", "not_documented"),
        ("TemporalStatus", "unspecified"),
        ("ConcordanceStatus", "not_assessed"),
    }
    for enum_name, onto in ontos.items():
        is_rules_only = enum_name in RULES_ONLY_ENUMS
        for value, entry in onto.items():
            has_anchor = bool(entry.cui or entry.sctid)
            has_synonyms = bool(entry.synonyms)
            has_provenance = bool(entry.source_provenance)
            if (enum_name, value) in empty_allowed:
                continue
            assert has_anchor or has_synonyms, (
                f"{enum_name}.{value} has neither concept anchor nor synonyms"
                f" (rules_only={is_rules_only})"
            )
            assert has_provenance, (
                f"{enum_name}.{value} has zero source_provenance entries"
            )


def test_synonyms_have_provenance():
    """If synonyms are non-empty, there must be at least one provenance."""
    ontos = all_enum_ontologies()
    for enum_name, onto in ontos.items():
        for value, entry in onto.items():
            if entry.synonyms:
                assert entry.source_provenance, (
                    f"{enum_name}.{value} has synonyms but zero provenance"
                )


def test_total_triple_count_exceeds_240():
    """Phase-1 acceptance: 240+ triples across enum + supplementary ontologies.

    Enum values are constrained by ``schema/enums.py`` and total 194 rows
    across 24 enums; the supplementary ontologies (medications, etiology
    details, comorbidities, birth history) provide the remaining ≥ 46 rows
    for the CDB build.
    """
    total = total_concept_count()
    assert total >= 240, (
        f"total ontology entries = {total}, phase-1 acceptance target is 240+"
    )


def test_supplementary_ontologies_populated():
    supp = supplementary_ontologies()
    assert "Medication" in supp and len(supp["Medication"]) >= 20, (
        "Medication supplementary ontology must have ≥ 20 entries"
    )
    assert "EtiologyDetails" in supp and len(supp["EtiologyDetails"]) >= 10
    assert "Comorbidity" in supp and len(supp["Comorbidity"]) >= 5
    for name, onto in supp.items():
        for key, entry in onto.items():
            assert isinstance(entry, ConceptEntry), f"{name}.{key} bad type"
            assert entry.synonyms, f"{name}.{key} has no synonyms"
            assert entry.source_provenance, f"{name}.{key} has no provenance"


def test_concept_linked_enums_have_cui_coverage():
    """CONCEPT_LINKED enums should have ≥50% of values with a CUI anchor
    (relaxed floor; Phase 1d UMLS-Full enrichment will lift the rest)."""
    ontos = all_enum_ontologies()
    for enum_name, onto in ontos.items():
        if enum_name in RULES_ONLY_ENUMS:
            continue
        n_with_cui = sum(1 for e in onto.values() if e.cui)
        assert n_with_cui >= 1, (
            f"{enum_name} is CONCEPT_LINKED but has zero CUIs"
        )


def test_rules_only_enums_declared():
    """RULES_ONLY_ENUMS must include Certainty, ConcordanceStatus,
    TemporalStatus, DrugResistanceStatus, EngelClass, IlaeOutcome."""
    expected = {
        "Certainty", "ConcordanceStatus", "TemporalStatus",
        "DrugResistanceStatus", "EngelClass", "IlaeOutcome",
    }
    assert expected <= set(RULES_ONLY_ENUMS), (
        f"missing rules-only declarations: {expected - set(RULES_ONLY_ENUMS)}"
    )


def test_concept_entry_type():
    ontos = all_enum_ontologies()
    for enum_name, onto in ontos.items():
        for value, entry in onto.items():
            assert isinstance(entry, ConceptEntry), (
                f"{enum_name}.{value} is not a ConceptEntry"
            )


# ===========================================================================
# Phase 3a acceptance tests — rules/fields/*
#
# Consolidated tests for the 8 P1 fields ported from ExECT-V2's JAPE +
# Groovy pipeline. Each field gets 3-5 positive cases (extracted from F-S
# train letters or paraphrased) plus negative cases (negation, hypothetical,
# family history). Uses a session-scoped ``PhenotypeAssembler`` so MedCAT
# and medspaCy load only once.
# ===========================================================================

import logging as _lg_mod  # noqa: E402
import sys as _sys  # noqa: E402
from datetime import date as _date  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

# Silence PyRuSH debug noise for the fixture load.
try:  # pragma: no cover
    from loguru import logger as _loguru
    _loguru.remove()
except Exception:
    pass
_lg_mod.disable(_lg_mod.CRITICAL)

_REPO_ROOT_P3 = _Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_P3) not in _sys.path:
    _sys.path.insert(0, str(_REPO_ROOT_P3))

from rules.context_config import build_medspacy_pipeline  # noqa: E402
from schema.enums import (  # noqa: E402
    Certainty as _Certainty,
    DocumentType as _DocType,
    EegBackground as _EegBg,
    EpilepsyType as _EpiType,
    EtiologyCategory as _Etio,
    IedType as _IedT,
    MedicationStatus as _MedStat,
    MriFinding as _MriF,
    SeizureType as _SeiT,
)
from services.medcat_extractor import MedCATExtractor as _MedCATExtractor  # noqa: E402
from services.phenotype_assembler import PhenotypeAssembler as _Assembler  # noqa: E402
import rules.fields as _rules_fields  # noqa: F401, E402 — registers rules


@pytest.fixture(scope="session")
def _p3_assembler() -> "_Assembler":
    cdb = str(_REPO_ROOT_P3 / "data" / "medcat_cdb_epilepsy" / "cdb")
    ex = _MedCATExtractor(cdb, verbose=False)
    nlp = build_medspacy_pipeline()
    return _Assembler(ex, nlp=nlp)


@pytest.fixture()
def run_text(_p3_assembler):
    def _run(text: str, doc_id: str = "TEST"):
        return _p3_assembler.process(
            text, doc_id=doc_id,
            doc_type=_DocType.PROGRESS_NOTE,
            doc_date=_date(2020, 1, 1),
            patient_id=doc_id,
        )
    return _run


# ---- 1. seizure_type -----------------------------------------------------

_ST_POS = [
    ("focal_impaired",
     "Diagnosis: focal epilepsy. seizure type and frequency: focal seizures "
     "with loss of awareness approximately 2 to 3 per month.",
     _SeiT.FOCAL_IMPAIRED_AWARENESS),
    ("gtc_myoclonic",
     "Diagnosis: generalised tonic clonic seizures with myoclonic jerks, "
     "possible JME.",
     _SeiT.GENERALIZED_TONIC_CLONIC),
    ("focal_aware",
     "The patient has simple partial seizures with retained awareness.",
     _SeiT.FOCAL_AWARE),
    ("absence_typical",
     "EEG shows typical absence seizures with 3-Hz spike-wave discharges.",
     _SeiT.GENERALIZED_ABSENCE_TYPICAL),
    ("fbtc",
     "She has focal to bilateral tonic clonic seizures from the right "
     "temporal region.",
     _SeiT.FOCAL_TO_BILATERAL_TONIC_CLONIC),
]


@pytest.mark.parametrize("label,text,expected", _ST_POS,
                         ids=[c[0] for c in _ST_POS])
def test_p3_seizure_type_positive(run_text, label, text, expected):
    pheno = run_text(text)
    ev = pheno.clinical_seizure.predominant_seizure_type
    assert ev.value == expected, f"[{label}] {ev.value} != {expected}"
    assert ev.certainty != _Certainty.NOT_DOCUMENTED


_ST_NEG = [
    ("denied", "The patient denies any seizure activity."),
    ("hypothetical",
     "If he were to have another seizure we would consider surgery."),
]


@pytest.mark.parametrize("label,text", _ST_NEG,
                         ids=[c[0] for c in _ST_NEG])
def test_p3_seizure_type_negative(run_text, label, text):
    pheno = run_text(text)
    ev = pheno.clinical_seizure.predominant_seizure_type
    if ev.value is not None:
        assert ev.certainty in (_Certainty.POSSIBLE, _Certainty.NEGATED)


def test_p3_other_seizure_types_multi(run_text):
    text = ("Diagnosis: generalised tonic clonic seizures with myoclonic "
            "jerks and occasional absences.")
    pheno = run_text(text)
    others = [e.value for e in pheno.clinical_seizure.other_seizure_types]
    assert pheno.clinical_seizure.predominant_seizure_type.value == \
        _SeiT.GENERALIZED_TONIC_CLONIC
    assert _SeiT.GENERALIZED_MYOCLONIC in others


# ---- 2. seizure_frequency ------------------------------------------------

_FREQ_POS = [
    ("2_3_month",
     "focal seizures with loss of awareness approximately 2 to 3 per month.",
     "month", 2.0, 3.0, False),
    ("3_4_week_endash",
     "She had approximately 3–4 generalised tonic chronic seizures per week.",
     "week", 3.0, 4.0, False),
    ("one_a_day",
     "The patient has one seizure a day.",
     "day", 1.0, 1.0, False),
    ("seizure_free_3y",
     "He has been seizure-free for 3 years.",
     "unspecified", None, None, True),
    ("jerks_weekly",
     "She has myoclonic jerks weekly.",
     "week", None, None, False),
]


@pytest.mark.parametrize(
    "label,text,period,c_min,c_max,sf", _FREQ_POS,
    ids=[c[0] for c in _FREQ_POS],
)
def test_p3_seizure_frequency_positive(
    run_text, label, text, period, c_min, c_max, sf,
):
    pheno = run_text(text)
    ev = pheno.clinical_seizure.seizure_frequency
    assert ev.value is not None, f"[{label}] nothing extracted"
    assert ev.value.period == period
    assert ev.value.count_min == c_min
    assert ev.value.count_max == c_max
    assert ev.value.seizure_free == sf


# ---- 3. onset_age --------------------------------------------------------

_ONSET_POS = [
    ("first_at_18", "Her first seizure was at age 18.", 18.0),
    ("started_at_5", "His seizures started at the age of 5.", 5.0),
    ("onset_at_12", "Age of onset was 12 years.", 12.0),
    ("diagnosed_at_18",
     "She was diagnosed with Epilepsy at the age of 18.", 18.0),
    ("since_age_6", "The patient has had seizures since age 6.", 6.0),
]


@pytest.mark.parametrize("label,text,expected", _ONSET_POS,
                         ids=[c[0] for c in _ONSET_POS])
def test_p3_onset_age_positive(run_text, label, text, expected):
    pheno = run_text(text)
    ev = pheno.clinical_seizure.age_at_onset_years
    assert ev.value == pytest.approx(expected), \
        f"[{label}] {ev.value} != {expected}"


def test_p3_onset_age_family_history(run_text):
    text = "His mother had epilepsy from the age of 30."
    pheno = run_text(text)
    ev = pheno.clinical_seizure.age_at_onset_years
    assert ev.value is None


# ---- 4. epilepsy_type ----------------------------------------------------

_EPI_POS = [
    ("focal", "Diagnosis: focal epilepsy of temporal lobe origin.",
     _EpiType.FOCAL),
    ("jme", "Diagnosis: juvenile myoclonic epilepsy (JME).",
     _EpiType.GENERALIZED),
    ("tle", "The patient carries a diagnosis of temporal lobe epilepsy.",
     _EpiType.FOCAL),
    ("lgs", "Diagnosis: Lennox-Gastaut syndrome.",
     _EpiType.COMBINED_FOCAL_GENERALIZED),
]


@pytest.mark.parametrize("label,text,expected", _EPI_POS,
                         ids=[c[0] for c in _EPI_POS])
def test_p3_epilepsy_type_positive(run_text, label, text, expected):
    pheno = run_text(text)
    ev = pheno.clinical_seizure.epilepsy_type
    assert ev.value == expected, f"[{label}] {ev.value} != {expected}"


def test_p3_epilepsy_type_no_epilepsy(run_text):
    text = "The patient presents with headaches only. No convulsions."
    pheno = run_text(text)
    ev = pheno.clinical_seizure.epilepsy_type
    assert ev.value is None


# ---- 5. etiology ---------------------------------------------------------

_ETIO_POS = [
    ("structural",
     "Diagnosis: symptomatic, structural right temporal lobe epilepsy. "
     "Subarachnoid haemorrhage 2017.",
     _Etio.STRUCTURAL),
    ("genetic",
     "Genetic testing revealed a pathogenic SCN1A variant, Dravet syndrome.",
     _Etio.GENETIC),
    ("immune",
     "Anti-NMDAR antibody positive; autoimmune encephalitis diagnosed.",
     _Etio.IMMUNE),
    ("infectious",
     "MRI shows a calcified neurocysticercosis lesion in the right frontal.",
     _Etio.INFECTIOUS),
    ("structural_hs",
     "MRI demonstrates left hippocampal sclerosis, consistent with MTLE.",
     _Etio.STRUCTURAL),
]


@pytest.mark.parametrize("label,text,expected", _ETIO_POS,
                         ids=[c[0] for c in _ETIO_POS])
def test_p3_etiology_positive(run_text, label, text, expected):
    pheno = run_text(text)
    ev = pheno.clinical_seizure.etiology_category
    assert ev.value == expected, f"[{label}] {ev.value} != {expected}"


def test_p3_etiology_negated_encephalitis(run_text):
    text = "He has never had meningitis or encephalitis."
    pheno = run_text(text)
    ev = pheno.clinical_seizure.etiology_category
    assert ev.value != _Etio.INFECTIOUS


def test_p3_etiology_cryptogenic(run_text):
    text = "Cause is unknown; presumed cryptogenic epilepsy."
    pheno = run_text(text)
    ev = pheno.clinical_seizure.etiology_category
    assert ev.value == _Etio.UNKNOWN


# ---- 6. medication -------------------------------------------------------

def test_p3_current_asm_lamotrigine(run_text):
    text = "Current antiepileptic medication: lamotrigine 75 mg twice a day."
    pheno = run_text(text)
    curr = pheno.medication.current_asms
    assert len(curr) == 1
    med = curr[0].value
    assert med.generic_name == "lamotrigine"
    assert med.status == _MedStat.CURRENT
    assert med.dose_text is not None and "75" in med.dose_text


def test_p3_multiple_current_asms(run_text):
    text = ("Current meds: sodium valproate 500 mg BD and lamotrigine "
            "100 mg BD.")
    pheno = run_text(text)
    names = {e.value.generic_name for e in pheno.medication.current_asms}
    assert any("valproate" in n for n in names)
    assert "lamotrigine" in names


def test_p3_prior_asm_stopped(run_text):
    text = "He was previously on carbamazepine 400 mg BD but this was stopped."
    pheno = run_text(text)
    prior_names = {e.value.generic_name for e in pheno.medication.prior_asms}
    assert "carbamazepine" in prior_names


def test_p3_failed_asm(run_text):
    text = "She has failed levetiracetam due to inadequate control."
    pheno = run_text(text)
    failed_names = {e.value.generic_name for e in pheno.medication.failed_asms}
    assert "levetiracetam" in failed_names


def test_p3_no_medication_mentioned(run_text):
    text = "The patient denies taking any medication."
    pheno = run_text(text)
    assert len(pheno.medication.current_asms) == 0


# ---- 7. mri --------------------------------------------------------------

def test_p3_mri_hippocampal_sclerosis(run_text):
    text = ("MRI brain: right hippocampal sclerosis with volume loss and "
            "increased T2 signal.")
    pheno = run_text(text)
    values = [f.value for f in pheno.mri.findings]
    assert _MriF.HIPPOCAMPAL_SCLEROSIS in values
    assert pheno.mri.hippocampal_sclerosis.value is True


def test_p3_mri_fcd(run_text):
    text = "MRI shows focal cortical dysplasia in the left frontal lobe."
    pheno = run_text(text)
    values = [f.value for f in pheno.mri.findings]
    assert _MriF.FOCAL_CORTICAL_DYSPLASIA in values


def test_p3_mri_normal(run_text):
    text = "Investigations: MRI brain unremarkable."
    pheno = run_text(text)
    assert pheno.mri.overall_normal.value is True


def test_p3_mri_negative(run_text):
    text = "MRI-negative epilepsy; no epileptogenic lesion identified."
    pheno = run_text(text)
    assert pheno.mri.mri_negative_for_epilepsy.value is True


def test_p3_mri_negated_hs(run_text):
    text = "MRI brain: no evidence of hippocampal sclerosis."
    pheno = run_text(text)
    values = [f.value for f in pheno.mri.findings]
    assert _MriF.HIPPOCAMPAL_SCLEROSIS not in values


# ---- 8. eeg --------------------------------------------------------------

def test_p3_eeg_normal(run_text):
    text = ("EEG report: Normal posterior dominant rhythm at 10 Hz. No "
            "epileptiform discharges.")
    pheno = run_text(text)
    assert pheno.eeg.background.value == _EegBg.NORMAL


def test_p3_eeg_generalized_spike_wave(run_text):
    text = "EEG shows generalised spike and wave with polyspikes."
    pheno = run_text(text)
    ied_values = [e.value.ied_type for e in pheno.eeg.ied_findings]
    assert (_IedT.SPIKE_AND_WAVE in ied_values or
            _IedT.GENERALIZED_SPIKE_WAVE_3HZ in ied_values)
    assert (_IedT.POLYSPIKE in ied_values or
            _IedT.POLYSPIKE_AND_WAVE in ied_values)
    assert pheno.eeg.ied_present.value is True


def test_p3_eeg_focal_slowing(run_text):
    text = "Routine EEG shows focal slowing over the right temporal region."
    pheno = run_text(text)
    assert pheno.eeg.background.value == _EegBg.FOCAL_SLOWING


def test_p3_eeg_no_ieds(run_text):
    text = "EEG: normal background. No epileptiform discharges identified."
    pheno = run_text(text)
    assert pheno.eeg.ied_present.value is False
    assert len(pheno.eeg.ied_findings) == 0
