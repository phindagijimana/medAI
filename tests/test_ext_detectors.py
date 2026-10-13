"""cTAKES-style sidecar (S1+S2): no GPU, no MedCAT, no new training."""

from __future__ import annotations

import pytest

from schema.claim import ReasonCode, ValidatorVerdict
from services.chain_llm import fuse, flatten
from services.chain_pipeline import ChainPipeline
from services.ext_detectors import extract_ext_detectors, parse_ext_detectors
from services.ext_detectors.attach import SidecarIndex
from services.ext_detectors.ctakes_meds import extract_ctakes_meds
from services.ext_detectors.freq import extract_freq
from services.ext_detectors.hs import extract_hs
from services.ext_detectors.guideline import (
    extract_dre,
    extract_eeg_done,
    extract_fail_reason,
    extract_first_feature,
    extract_ictal,
    extract_rescue_if,
)
from services.ext_detectors.stated_type import extract_stated_type

NOTE = (
    "Assessment: 34 year old with focal epilepsy. "
    "Takes levetiracetam 500 mg twice daily. "
    "Seizures occur about 2 per month. Denies lamotrigine use."
)


def ev(value, quote, **kw):
    d = {"value": value, "certainty": "definite", "temporal_status": "current",
         "evidence_text": quote, "char_start": None, "char_end": None}
    d.update(kw)
    return d


def pheno(**modules):
    return {"document": {"doc_id": "x"}, **modules}


class _Pheno:
    def __init__(self, d): self._d = d
    def model_dump(self, **kw): return self._d


class _Assembler:
    def __init__(self, d): self._d = d
    def process(self, text, **kw): return _Pheno(self._d)


class _NoCandidates:
    def get_candidates(self, **kw): return []


def _specialist():
    return pheno(
        clinical_seizure={
            "epilepsy_type": ev("focal", "focal epilepsy"),
            "age_at_onset_years": ev(10, "34 year old"),
        },
        medication={"current_asms": [ev({"generic_name": "levetiracetam"}, "levetiracetam 500 mg")]},
    )


def _run(llm):
    pipe = ChainPipeline(
        assembler=_Assembler(_specialist()),
        extractor=object(), candidate_service=_NoCandidates(),
        llm_reasoner=(lambda t, d, dd: llm) if llm is not None else None,
    )
    pipe.cfg.enable_preprocessing = False
    stats, claims = pipe.extract(NOTE, document_id="D1", return_claims=True)
    return stats, claims


def _paths(items):
    return {(it.field_path, it.ev["value"]["generic_name"]) for it in items}


def test_parse_empty_and_ctakes():
    assert parse_ext_detectors("") == ()
    assert parse_ext_detectors("ctakes") == ("ctakes",)
    assert parse_ext_detectors("freq,stated-type,hs") == ("freq", "stated-type", "hs")
    with pytest.raises(ValueError, match="trained"):
        parse_ext_detectors("b1")
    with pytest.raises(ValueError, match="freq"):
        parse_ext_detectors("xie")
    with pytest.raises(ValueError, match="stated-type"):
        parse_ext_detectors("decker")
    with pytest.raises(ValueError, match="column"):
        parse_ext_detectors("engel")
    assert parse_ext_detectors("dre,fail-reason") == ("dre", "fail-reason")


def test_s1_finds_current_asm_and_skips_negation():
    items = extract_ctakes_meds(NOTE)
    assert ("medication.current_asms", "levetiracetam") in _paths(items)
    assert all(p[1] != "lamotrigine" for p in _paths(items))  # "Denies lamotrigine"


def test_s2_i2b2_status_prior_vs_current():
    note = "Keppra was d/c'd last month. Now on Vimpat 200 mg twice daily."
    items = extract_ctakes_meds(note)
    got = _paths(items)
    assert ("medication.prior_asms", "levetiracetam") in got
    assert ("medication.current_asms", "lacosamide") in got


def test_s2_planned_is_dropped():
    note = "Will start Keppra next week if seizures continue."
    assert extract_ctakes_meds(note) == []


def test_s2_rescue_maps_to_rescue_path():
    note = "Rescue: buccal midazolam 10 mg as needed."
    items = extract_ctakes_meds(note)
    assert any(it.field_path == "medication.rescue_medication"
               and "midazolam" in it.ev["value"]["generic_name"] for it in items)


def test_extract_ext_detectors_unknown_raises():
    with pytest.raises(ValueError):
        extract_ext_detectors(["nope"], NOTE)


def test_flag_off_pipeline_has_no_ctakes_detector():
    llm = pheno(
        clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")},
        medication={"current_asms": [ev({"generic_name": "levetiracetam"}, "levetiracetam 500 mg")]},
    )
    stats, claims = _run(llm)
    assert stats.n_sidecar_agree == stats.n_sidecar_only == 0
    assert all("ctakes" not in (c.detectors or []) for c in claims)


def _run_sidecar(llm, note=NOTE):
    pipe = ChainPipeline(
        assembler=_Assembler(_specialist()),
        extractor=object(), candidate_service=_NoCandidates(),
        llm_reasoner=(lambda t, d, dd: llm) if llm is not None else None,
    )
    pipe.cfg.enable_preprocessing = False
    pipe.cfg.ext_detectors = ("ctakes",)
    return pipe.extract(note, document_id="D1", return_claims=True)


def test_sidecar_agree_appends_detector_keeps_accept():
    llm = pheno(
        clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")},
        medication={"current_asms": [ev({"generic_name": "levetiracetam"}, "levetiracetam 500 mg")]},
    )
    stats, claims = _run_sidecar(llm)
    lev = next(c for c in claims if c.field_path == "medication.current_asms")
    assert "ctakes" in lev.detectors and "llm" in lev.detectors and "epextra" in lev.detectors
    assert lev.validator_verdict == ValidatorVerdict.ACCEPT
    assert ReasonCode.ACCEPT_SPECIALIST_LLM_AGREE in lev.reason_codes
    assert stats.n_sidecar_agree >= 1


def test_sidecar_cannot_auto_accept_alone():
    note = "Takes clobazam 10 mg daily."
    llm = pheno(clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")})
    stats, claims = _run_sidecar(llm, note=note)
    only = [c for c in claims if c.detectors == ["ctakes"]]
    assert only, "sidecar should surface a drug the specialist stub did not list"
    assert all(c.validator_verdict == ValidatorVerdict.REVIEW for c in only)
    assert all(ReasonCode.SIDECAR_ONLY in c.reason_codes for c in only)
    assert stats.n_sidecar_only >= 1


def test_sidecar_status_mismatch_sets_alternative_keeps_verdict():
    note = (
        "Assessment: 34 year old with focal epilepsy. "
        "Keppra was d/c'd last month. Denies lamotrigine use."
    )
    spec = pheno(
        clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")},
        medication={"current_asms": [ev({"generic_name": "levetiracetam"}, "Keppra")]},
    )
    llm = pheno(
        clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")},
        medication={"current_asms": [ev({"generic_name": "levetiracetam"}, "Keppra")]},
    )
    pipe = ChainPipeline(
        assembler=_Assembler(spec), extractor=object(),
        candidate_service=_NoCandidates(), llm_reasoner=lambda t, d, dd: llm,
    )
    pipe.cfg.enable_preprocessing = False
    pipe.cfg.ext_detectors = ("ctakes",)
    stats, claims = pipe.extract(note, document_id="D1", return_claims=True)
    lev = next(c for c in claims if c.field_path == "medication.current_asms")
    assert lev.validator_verdict == ValidatorVerdict.ACCEPT
    assert lev.sidecar_alternative and "prior" in lev.sidecar_alternative.lower()
    assert stats.n_sidecar_mismatch >= 1


def test_attach_index_does_not_consume_unrelated_drug():
    spec_claim_val = {"generic_name": "levetiracetam"}
    items = extract_ctakes_meds("Takes lamotrigine 100 mg daily.")
    idx = SidecarIndex(items)
    class C:
        field_path = "medication.current_asms"
        value = spec_claim_val
        detectors = ["epextra", "llm"]
        sidecar_alternative = None
    c = C()
    idx.apply(c)
    assert c.detectors == ["epextra", "llm"]
    assert idx.leftovers()


def test_fuse_unchanged_by_sidecar_module_import():
    spec = flatten(pheno(clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")}))
    llm = flatten(pheno(clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")}))
    assert fuse(spec, llm).specialist[0].status == "agree"


def _run_named(llm, detectors, note=NOTE, spec=None):
    pipe = ChainPipeline(
        assembler=_Assembler(spec or _specialist()),
        extractor=object(), candidate_service=_NoCandidates(),
        llm_reasoner=(lambda t, d, dd: llm) if llm is not None else None,
    )
    pipe.cfg.enable_preprocessing = False
    pipe.cfg.ext_detectors = tuple(detectors)
    return pipe.extract(note, document_id="D1", return_claims=True)


def test_freq_reads_about_n_per_month():
    items = extract_freq(NOTE)
    assert len(items) == 1
    v = items[0].ev["value"]
    assert v["period"] == "month" and v["count_min"] == 2.0 and v["seizure_free"] is False


def test_freq_current_seizure_free_beats_old_rate():
    note = "Used to have 2 seizures per month. Currently seizure-free."
    items = extract_freq(note)
    assert len(items) == 1
    assert items[0].ev["value"]["seizure_free"] is True


def test_freq_skips_hypothetical_and_historical_only():
    assert extract_freq("If she has more than 3 seizures per day, call EMS.") == []
    assert extract_freq("Used to have 2 seizures per month as a child.") == []


def test_stated_type_explicit_only_no_old_alias_no_inference():
    items = extract_stated_type("Assessment: focal epilepsy. GTCS twice this year.")
    paths = {it.field_path: it.ev["value"] for it in items}
    assert paths["clinical_seizure.epilepsy_type"] == "focal"
    assert paths["clinical_seizure.predominant_seizure_type"] == "generalized_tonic_clonic"
    cps = extract_stated_type("History of complex partial seizures and grand mal.")
    assert cps == []
    gtc_only = extract_stated_type("Witnessed GTCS last night.")
    assert [it.field_path for it in gtc_only] == ["clinical_seizure.predominant_seizure_type"]


def test_hs_true_on_mts_false_only_with_mri_else_silent():
    items = extract_hs("MRI brain: left mesial temporal sclerosis.")
    assert any(it.field_path == "mri.hippocampal_sclerosis" and it.ev["value"] is True
               for it in items)
    neg = extract_hs("MRI: no hippocampal sclerosis.")
    assert any(it.field_path == "mri.hippocampal_sclerosis" and it.ev["value"] is False
               for it in neg)
    assert extract_hs("No hippocampal sclerosis on exam today.") == []
    assert extract_hs("Clinic follow-up. Continues levetiracetam.") == []


def test_freq_sidecar_agree_appends_detector():
    freq = {"raw_text": "about 2 per month", "period": "month",
            "count_min": 2.0, "count_max": 2.0, "seizure_free": False}
    spec = pheno(
        clinical_seizure={
            "epilepsy_type": ev("focal", "focal epilepsy"),
            "seizure_frequency": ev(freq, "about 2 per month"),
        },
        medication={"current_asms": [ev({"generic_name": "levetiracetam"}, "levetiracetam")]},
    )
    llm = spec
    stats, claims = _run_named(llm, ("freq",), spec=spec)
    fr = next(c for c in claims if c.field_path == "clinical_seizure.seizure_frequency")
    assert "freq" in fr.detectors
    assert fr.validator_verdict == ValidatorVerdict.ACCEPT
    assert stats.n_sidecar_agree >= 1


def test_freq_mismatch_sets_alternative_keeps_accept():
    freq = {"raw_text": "2 per month", "period": "month",
            "count_min": 2.0, "count_max": 2.0, "seizure_free": False}
    note = (
        "Assessment: focal epilepsy. Used to have 2 per month. "
        "Currently seizure-free. Takes levetiracetam."
    )
    spec = pheno(
        clinical_seizure={
            "epilepsy_type": ev("focal", "focal epilepsy"),
            "seizure_frequency": ev(freq, "2 per month"),
        },
        medication={"current_asms": [ev({"generic_name": "levetiracetam"}, "levetiracetam")]},
    )
    stats, claims = _run_named(spec, ("freq",), note=note, spec=spec)
    fr = next(c for c in claims if c.field_path == "clinical_seizure.seizure_frequency")
    assert fr.validator_verdict == ValidatorVerdict.ACCEPT
    assert fr.sidecar_alternative
    assert "seizure_free" in fr.sidecar_alternative.lower() or "True" in fr.sidecar_alternative
    assert stats.n_sidecar_mismatch >= 1


def test_stated_type_sidecar_only_is_review():
    note = "Witnessed GTCS last night. Not on medications."
    spec = pheno(clinical_seizure={"age_at_onset_years": ev(10, "onset at 10")})
    llm = spec
    stats, claims = _run_named(llm, ("stated-type",), note=note, spec=spec)
    only = [c for c in claims if c.detectors == ["stated-type"]]
    assert only
    assert all(c.validator_verdict == ValidatorVerdict.REVIEW for c in only)
    assert all(ReasonCode.SIDECAR_ONLY in c.reason_codes for c in only)
    assert stats.n_sidecar_only >= 1


def test_hs_sidecar_only_cpu_mention_is_review():
    note = "MRI brain demonstrates left MTS. Follow-up in clinic."
    spec = pheno(clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")})
    stats, claims = _run_named(spec, ("hs",), note=note, spec=spec)
    hs = [c for c in claims if c.field_path == "mri.hippocampal_sclerosis"]
    assert hs and hs[0].detectors == ["hs"]
    assert hs[0].validator_verdict == ValidatorVerdict.REVIEW
    assert ReasonCode.SIDECAR_ONLY in hs[0].reason_codes


def test_fail_reason_efficacy_vs_wean_vs_silent():
    items = extract_fail_reason(
        "Carbamazepine was stopped for lack of efficacy. "
        "Lamotrigine weaned as she is seizure-free. "
        "Takes levetiracetam."
    )
    got = {(it.field_path, it.ev["value"]["generic_name"],
            it.ev["value"].get("reason_discontinued")) for it in items}
    assert ("medication.failed_asms", "carbamazepine", "lack_of_efficacy") in got
    assert ("medication.prior_asms", "lamotrigine", "seizure_free_wean") in got
    assert all(g[1] != "levetiracetam" for g in got)


def test_rescue_if_skips_instruction_keeps_home_prn():
    home = extract_rescue_if("Rescue: buccal midazolam 10 mg as needed at home.")
    assert any(it.field_path == "medication.rescue_medication"
               and "midazolam" in it.ev["value"]["generic_name"] for it in home)
    instr = extract_rescue_if(
        "If she has a cluster, use nasal midazolam. Not prescribed yet."
    )
    assert instr == []


def test_ictal_not_captured_emits_false_not_a_lobe():
    items = extract_ictal("EEG: no ictal onset captured. Background slowing.")
    assert any(it.field_path == "eeg.seizures_captured" and it.ev["value"] is False
               for it in items)
    assert all(it.field_path != "eeg.ictal_onset_lobe" for it in items)
    cap = extract_ictal("Video-EEG captured an electrographic seizure from the left temporal region.")
    paths = {it.field_path: it.ev["value"] for it in cap}
    assert paths.get("eeg.seizures_captured") is True
    assert paths.get("eeg.ictal_onset_lobe") == "temporal"


def test_eeg_done_skips_recommended():
    assert extract_eeg_done("Video-EEG is recommended if seizures continue.") == []
    items = extract_eeg_done("Video-EEG was performed last month.")
    assert items and items[0].ev["value"] == "video_eeg"


def test_dre_as_stated_not_inferred():
    items = extract_dre("She has drug-resistant epilepsy.")
    assert items[0].ev["value"] == "drug_resistant"
    assert extract_dre("Failed two ASMs. Continues levetiracetam.") == []
    denied = extract_dre("This is not drug-resistant epilepsy.")
    assert denied == []


def test_first_feature_needs_onset_cue():
    items = extract_first_feature(
        "Seizures begin with lip smacking, then impaired awareness."
    )
    assert any(it.field_path == "clinical_seizure.focal_motor_onset"
               and it.ev["value"] == "automatisms" for it in items)
    assert extract_first_feature("She has chewing automatisms during seizures.") == []


def test_dre_sidecar_only_is_review():
    note = "Assessment: drug-resistant epilepsy. No other details."
    spec = pheno(clinical_seizure={"epilepsy_type": ev("focal", "focal")})
    stats, claims = _run_named(spec, ("dre",), note=note, spec=spec)
    dre = [c for c in claims if c.field_path == "medication.drug_resistance_status"]
    assert dre and dre[0].detectors == ["dre"]
    assert dre[0].validator_verdict == ValidatorVerdict.REVIEW
    assert ReasonCode.SIDECAR_ONLY in dre[0].reason_codes
