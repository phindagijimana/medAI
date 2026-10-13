"""LEO Reason-B: fusion rule and pipeline routing (no GPU, no MedCAT)."""

from __future__ import annotations

import pytest

from schema.claim import ReasonCode, ValidatorVerdict
from services.chain_llm import (
    flatten, fuse, is_nullish, is_unknown_value, locate_quote, values_agree,
)
from services.chain_pipeline import ChainPipeline

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


# ── values_agree ─────────────────────────────────────────────────────────

def test_strings_case_and_space_insensitive():
    assert values_agree("Focal ", "focal")
    assert not values_agree("focal", "generalized")


def test_numbers_use_tolerance_one():
    assert values_agree(34, 35)
    assert not values_agree(34, 40)


def test_drug_names_canonicalised():
    assert values_agree({"generic_name": "Levetiracetam"}, {"generic_name": "levetiracetam"})
    assert not values_agree({"generic_name": "lamotrigine"}, {"generic_name": "levetiracetam"})


def test_frequency_ignores_unspecified_period_and_tolerates_counts():
    a = {"period": "month", "count_min": 2, "count_max": 2}
    assert values_agree(a, {"period": "unspecified", "count_min": 2, "count_max": 3})
    assert not values_agree(a, {"period": "week", "count_min": 2, "count_max": 2})
    assert not values_agree(a, {"period": "month", "count_min": 8, "count_max": 8})


def test_nullish():
    assert is_nullish(None) and is_nullish("Unspecified") and is_nullish("not_documented")
    assert not is_nullish("focal")


# ── fuse ─────────────────────────────────────────────────────────────────

def test_scalar_agree_and_disagree():
    spec = flatten(pheno(clinical_seizure={
        "epilepsy_type": ev("focal", "focal epilepsy"),
        "age_at_onset_years": ev(10, "onset at 10"),
    }))
    llm = flatten(pheno(clinical_seizure={
        "epilepsy_type": ev("Focal", "focal epilepsy"),
        "age_at_onset_years": ev(30, "onset at 30"),
    }))
    f = fuse(spec, llm)
    status = {s.item.field_path: s for s in f.specialist}
    assert status["clinical_seizure.epilepsy_type"].status == "agree"
    d = status["clinical_seizure.age_at_onset_years"]
    assert d.status == "disagree" and d.alternative == "30"
    assert f.llm_only == []


def test_list_pairs_and_leftovers():
    spec = flatten(pheno(medication={"current_asms": [
        ev({"generic_name": "levetiracetam"}, "levetiracetam"),
        ev({"generic_name": "lacosamide"}, "lacosamide"),
    ]}))
    llm = flatten(pheno(medication={"current_asms": [
        ev({"generic_name": "levetiracetam"}, "levetiracetam"),
        ev({"generic_name": "lamotrigine"}, "lamotrigine"),
    ]}))
    f = fuse(spec, llm)
    st = [(s.item.ev["value"]["generic_name"], s.status) for s in f.specialist]
    assert ("levetiracetam", "agree") in st and ("lacosamide", "specialist_only") in st
    assert [i.ev["value"]["generic_name"] for i in f.llm_only] == ["lamotrigine"]


def test_llm_nullish_value_is_not_a_dissent_or_a_claim():
    spec = flatten(pheno(clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")}))
    llm = flatten(pheno(clinical_seizure={"epilepsy_type": ev("unspecified", "epilepsy")}))
    f = fuse(spec, llm)
    assert f.specialist[0].status == "specialist_only" and f.llm_only == []


def test_unknown_is_a_value_on_epilepsy_type():
    assert is_unknown_value("clinical_seizure.epilepsy_type", "unknown")
    assert not is_unknown_value("clinical_seizure.epilepsy_type", "focal")
    spec = flatten(pheno(clinical_seizure={"epilepsy_type": ev("unknown", "epilepsy")}))
    llm = flatten(pheno(clinical_seizure={"epilepsy_type": ev("unknown", "epilepsy")}))
    f = fuse(spec, llm)
    assert f.specialist[0].status == "agree"


def test_unknown_plus_silent_is_review_not_accept():
    """Development-letter rule: one reader unknown, the other silent → REVIEW. Not hold-out."""
    note = "Assessment: 34 year old with epilepsy. Takes levetiracetam 500 mg twice daily."
    spec = pheno(clinical_seizure={"epilepsy_type": ev("unknown", "epilepsy",
                                                      char_start=note.index("epilepsy"),
                                                      char_end=note.index("epilepsy") + 8)})
    pipe = ChainPipeline(assembler=_Assembler(spec), extractor=object(),
                         candidate_service=_NoCandidates(),
                         llm_reasoner=lambda t, d, dd: pheno())
    pipe.cfg.enable_preprocessing = False
    stats, claims = pipe.extract(note, document_id="D1", return_claims=True)
    et = next(c for c in claims if c.field_path == "clinical_seizure.epilepsy_type")
    assert et.validator_verdict == ValidatorVerdict.REVIEW
    assert ReasonCode.UNKNOWN_SILENT in et.reason_codes
    assert stats.n_unknown_silent == 1


def test_unknown_plus_silent_can_be_switched_off():
    note = "Assessment: 34 year old with epilepsy. Takes levetiracetam 500 mg twice daily."
    spec = pheno(clinical_seizure={"epilepsy_type": ev("unknown", "epilepsy",
                                                      char_start=note.index("epilepsy"),
                                                      char_end=note.index("epilepsy") + 8)})
    pipe = ChainPipeline(assembler=_Assembler(spec), extractor=object(),
                         candidate_service=_NoCandidates(),
                         llm_reasoner=lambda t, d, dd: pheno())
    pipe.cfg.enable_preprocessing = False
    pipe.cfg.unknown_silent_review = False
    _, claims = pipe.extract(note, document_id="D1", return_claims=True)
    et = next(c for c in claims if c.field_path == "clinical_seizure.epilepsy_type")
    assert ReasonCode.UNKNOWN_SILENT not in et.reason_codes


# ── locate_quote ─────────────────────────────────────────────────────────

def test_locate_quote_exact_and_whitespace_case_tolerant():
    s, e = locate_quote("focal epilepsy", NOTE)
    assert NOTE[s:e] == "focal epilepsy"
    s, e = locate_quote("Levetiracetam  500 mg", NOTE)
    assert NOTE[s:e].lower() == "levetiracetam 500 mg"
    assert locate_quote("topiramate 100 mg", NOTE) is None
    assert locate_quote("", NOTE) is None


# ── pipeline routing with stubs ──────────────────────────────────────────

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


def _by(claims, path_value):
    return next(c for c in claims if c.concept.id == path_value or c.concept.label == path_value)


def test_without_llm_nothing_changes():
    stats, claims = _run(None)
    assert not stats.llm_available
    assert all(c.detectors == ["epextra"] for c in claims)
    assert stats.n_llm_agree == stats.n_llm_only == 0


def test_agreement_adds_llm_detector_and_accepts():
    llm = pheno(
        clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")},
        medication={"current_asms": [ev({"generic_name": "levetiracetam"}, "levetiracetam 500 mg")]},
    )
    stats, claims = _run(llm)
    agreed = [c for c in claims if c.detectors == ["epextra", "llm"]]
    assert len(agreed) == 2 and stats.n_llm_agree == 2
    assert all(c.validator_verdict == ValidatorVerdict.ACCEPT for c in agreed)
    assert all(ReasonCode.ACCEPT_SPECIALIST_LLM_AGREE in c.reason_codes for c in agreed)


def test_disagreement_goes_to_review_with_alternative():
    llm = pheno(clinical_seizure={"age_at_onset_years": ev(40, "34 year old")})
    stats, claims = _run(llm)
    c = next(c for c in claims if c.alternative is not None)
    assert c.alternative == "40" and c.detectors == ["epextra"]
    assert c.validator_verdict == ValidatorVerdict.REVIEW
    assert ReasonCode.SOURCE_DISAGREEMENT in c.reason_codes
    assert stats.n_llm_disagree == 1


def test_llm_only_with_verbatim_quote_is_reviewed_never_accepted():
    llm = pheno(medication={"current_asms": [
        ev({"generic_name": "levetiracetam"}, "levetiracetam 500 mg"),
        ev({"generic_name": "lamotrigine"}, "lamotrigine use"),
    ]})
    stats, claims = _run(llm)
    only = [c for c in claims if c.detectors == ["llm"]]
    assert len(only) == 1 and stats.n_llm_only == 1
    assert only[0].validator_verdict == ValidatorVerdict.REVIEW
    assert ReasonCode.LLM_ONLY in only[0].reason_codes


def test_llm_only_with_invented_quote_is_rejected_and_counted():
    llm = pheno(medication={"current_asms": [
        ev({"generic_name": "topiramate"}, "topiramate 100 mg nightly"),
    ]})
    stats, claims = _run(llm)
    bad = [c for c in claims if c.detectors == ["llm"]]
    assert len(bad) == 1 and stats.n_llm_unsupported == 1
    assert bad[0].validator_verdict == ValidatorVerdict.REJECT
    assert ReasonCode.OFFSETS_UNRESOLVED in bad[0].reason_codes


def test_failing_reasoner_degrades_to_specialist_only():
    def boom(*a): raise RuntimeError("gpu on fire")
    pipe = ChainPipeline(assembler=_Assembler(_specialist()), extractor=object(),
                         candidate_service=_NoCandidates(), llm_reasoner=boom)
    pipe.cfg.enable_preprocessing = False
    stats, claims = pipe.extract(NOTE, document_id="D1", return_claims=True)
    assert not stats.llm_available and claims


# ── value grounding and disagreement policy (leo-v0.3) ───────────────────

from services.chain_llm import ground_value  # noqa: E402

GNOTE = ("Rachel started having absence seizures at around the age of 8. She has about 2 to 3 seizures "
         "per month. Medication: Lamotrigine 100 mg twice a day and Keppra 500 mg bd. "
         "She has generalised epilepsy.")


def _sl(span):
    return GNOTE[span[0]:span[1]] if span else None


def test_ground_drug_with_dose_and_brand_alias():
    assert _sl(ground_value("medication.current_asms", {"generic_name": "lamotrigine"}, GNOTE)
               ).lower().startswith("lamotrigine 100 mg")
    assert _sl(ground_value("medication.current_asms", {"generic_name": "levetiracetam"}, GNOTE)
               ).lower().startswith("keppra")
    assert ground_value("medication.current_asms", {"generic_name": "topiramate"}, GNOTE) is None


def test_ground_age_frequency_types():
    assert "age of 8" in _sl(ground_value("clinical_seizure.age_at_onset_years", 8.0, GNOTE))
    assert ground_value("clinical_seizure.age_at_onset_years", 30, GNOTE) is None
    f = {"count_min": 2, "count_max": 3, "period": "month", "seizure_free": False}
    assert "2 to 3" in _sl(ground_value("clinical_seizure.seizure_frequency", f, GNOTE))
    assert ground_value("clinical_seizure.seizure_frequency", {"seizure_free": True}, GNOTE) is None
    assert ground_value("clinical_seizure.epilepsy_type", "generalized", GNOTE) is not None
    assert ground_value("clinical_seizure.predominant_seizure_type", "generalized_absence_typical", GNOTE)
    assert ground_value("clinical_seizure.epilepsy_type", "focal", "No type is stated here.") is None


def test_llm_only_value_with_templated_quote_is_grounded_not_rejected():
    llm = pheno(medication={"current_asms": [
        ev({"generic_name": "lamotrigine"}, "lamotrigine 100.0 mg daily"),   # templated, not in note
    ]})
    stats, claims = _run(llm)
    c = [c for c in claims if c.detectors == ["llm"]][0]
    assert c.validator_verdict == ValidatorVerdict.REVIEW and ReasonCode.LLM_ONLY in c.reason_codes
    assert stats.n_llm_grounded == 1 and stats.n_llm_unsupported == 0


def test_disagree_primary_llm_swaps_value_and_keeps_alternative():
    llm = pheno(clinical_seizure={"age_at_onset_years": ev(34, "34 year old")})
    spec = _specialist()
    pipe = ChainPipeline(assembler=_Assembler(spec), extractor=object(),
                         candidate_service=_NoCandidates(), llm_reasoner=lambda t, d, dd: llm)
    pipe.cfg.enable_preprocessing = False
    pipe.cfg.disagree_primary = {"clinical_seizure.age_at_onset_years": "llm"}
    _, claims = pipe.extract(NOTE, document_id="D1", return_claims=True)
    c = next(c for c in claims if c.field_path == "clinical_seizure.age_at_onset_years")
    assert c.detectors == ["llm"] and float(c.value) == 34 and c.alternative in ("10", "10.0")
    assert c.validator_verdict == ValidatorVerdict.REVIEW


def test_ltm_is_not_kept_as_a_drug():
    note = NOTE + " If seizures persist, escalate to LTM."
    llm = pheno(medication={"current_asms": [
        ev({"generic_name": "ltm"}, "escalate to LTM"),
    ]})
    spec = pheno(
        clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")},
        medication={"current_asms": [ev({"generic_name": "ltm"}, "escalate to LTM")]},
    )
    pipe = ChainPipeline(assembler=_Assembler(spec), extractor=object(),
                         candidate_service=_NoCandidates(), llm_reasoner=lambda t, d, dd: llm)
    pipe.cfg.enable_preprocessing = False
    _, claims = pipe.extract(note, document_id="D1", return_claims=True)
    meds = [c for c in claims if "medication" in c.field_path]
    names = []
    for c in meds:
        v = c.value
        names.append((v.get("generic_name") if isinstance(v, dict) else v) or "")
    assert not any(str(n).lower() == "ltm" for n in names)


def test_ied_silent_accepts_llm_only_ied_when_rules_silent():
    note = "EEG showed left temporal sharp waves."
    spec = pheno(clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")})
    llm = pheno(
        clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")},
        eeg={"ied_present": ev(True, "sharp waves")},
    )
    pipe = ChainPipeline(assembler=_Assembler(spec), extractor=object(),
                         candidate_service=_NoCandidates(), llm_reasoner=lambda t, d, dd: llm)
    pipe.cfg.enable_preprocessing = False
    pipe.cfg.llm_if_silent_accept = ("eeg.ied_present",)
    _, claims = pipe.extract(note, document_id="D1", return_claims=True)
    ied = next(c for c in claims if c.field_path == "eeg.ied_present")
    assert ied.detectors == ["llm"]
    assert ied.validator_verdict == ValidatorVerdict.ACCEPT
    assert ReasonCode.LLM_ONLY not in ied.reason_codes


def test_ied_silent_off_keeps_llm_only_ied_in_review():
    note = "EEG showed left temporal sharp waves."
    spec = pheno(clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")})
    llm = pheno(
        clinical_seizure={"epilepsy_type": ev("focal", "focal epilepsy")},
        eeg={"ied_present": ev(True, "sharp waves")},
    )
    pipe = ChainPipeline(assembler=_Assembler(spec), extractor=object(),
                         candidate_service=_NoCandidates(), llm_reasoner=lambda t, d, dd: llm)
    pipe.cfg.enable_preprocessing = False
    _, claims = pipe.extract(note, document_id="D1", return_claims=True)
    ied = next(c for c in claims if c.field_path == "eeg.ied_present")
    assert ied.validator_verdict == ValidatorVerdict.REVIEW
    assert ReasonCode.LLM_ONLY in ied.reason_codes
