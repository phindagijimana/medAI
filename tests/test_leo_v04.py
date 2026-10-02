"""leo-v0.4: acute administrations, unconfirmed specialist-only drugs, empty frequency (no GPU)."""

from __future__ import annotations

import pytest

from schema.claim import ReasonCode, ValidatorVerdict
from services.chain_llm import freq_counts, is_empty_frequency, values_agree
from services.chain_pipeline import ACUTE_FIELD_PATH, ChainPipeline
from services.med_context import acute_administration


def _acute(text: str, drug: str):
    i = text.index(drug)
    return acute_administration(text, i, i + len(drug))


# ── acute-administration rule ─────────────────────────────────────────────

@pytest.mark.parametrize("text,drug", [
    ("EMS administered Versed (midazolam) 10 mg IM at 18:42 with transient improvement.", "midazolam"),
    ("At 18:51, Ativan (lorazepam) 4 mg IV was administered with brief cessation.", "lorazepam"),
    ("Keppra (levetiracetam) 4,500 mg IV load started at 18:56.", "levetiracetam"),
    ("He was given lorazepam 2 mg at 03:10 for a cluster.", "lorazepam"),
    ("Fosphenytoin bolus 20 mg PE/kg infused.", "Fosphenytoin"),
])
def test_one_off_administrations_are_acute(text, drug):
    assert _acute(text, drug) is not None


@pytest.mark.parametrize("text,drug", [
    ("Medication: Lamotrigine 200mg twice daily\nBuccal Midazolam 10mg PRN", "Midazolam"),   # home rescue
    ("Continue levetiracetam 1000 mg IV q12h while NPO.", "levetiracetam"),                  # scheduled
    ("Takes levetiracetam 500 mg twice daily.", "levetiracetam"),
    ("Lorazepam 2 mg IV given at 03:10. Patient takes lamotrigine 200 mg daily.", "lamotrigine"),
    ("Intranasal midazolam 5 mg as needed for seizures longer than 5 minutes.", "midazolam"),
    ("Lamotrigine 200 mg daily.", "Lamotrigine"),
])
def test_regimen_and_rescue_mentions_are_not_acute(text, drug):
    assert _acute(text, drug) is None


def test_cue_far_from_mention_in_same_sentence_does_not_mark_it():
    t = ("Received lorazepam 4 mg IV at 18:51, and separately, after a long discussion of the "
         "family situation, work and school, he continues lamotrigine 200 mg nightly.")
    assert _acute(t, "lamotrigine") is None
    assert _acute(t, "lorazepam") is not None


def test_bad_offsets_are_not_acute():
    assert acute_administration("abc", 2, 2) is None
    assert acute_administration("", 0, 1) is None


# ── empty frequency ───────────────────────────────────────────────────────

def test_empty_frequency_values():
    assert is_empty_frequency({"raw_text": "", "period": "unspecified", "count_min": None,
                               "count_max": None, "seizure_free": False})
    assert not is_empty_frequency({"period": "month", "count_min": 2})
    assert not is_empty_frequency({"seizure_free": True})          # seizure-free asserts something
    assert not is_empty_frequency("focal")


def test_empty_frequency_does_not_agree_with_anything():
    empty = {"period": "unspecified", "count_min": None, "count_max": None, "seizure_free": False}
    assert not values_agree(empty, {"period": "month", "count_min": 2, "count_max": 2})
    assert not values_agree(empty, empty)


def test_seizure_free_agrees_with_count_zero_only():
    sf = {"seizure_free": True, "period": "unspecified"}
    assert freq_counts(sf) == (0.0, 0.0)
    assert values_agree(sf, {"count_min": 0, "count_max": 0})
    assert not values_agree(sf, {"period": "month", "count_min": 2, "count_max": 2})
    assert not values_agree(sf, {"seizure_free": False, "count_min": 0, "count_max": 0})


# ── pipeline ──────────────────────────────────────────────────────────────

def ev(value, quote, text=None, **kw):
    d = {"value": value, "certainty": "definite", "temporal_status": "current",
         "evidence_text": quote, "char_start": None, "char_end": None}
    if text is not None and quote:
        i = text.index(quote)
        d["char_start"], d["char_end"] = i, i + len(quote)
    d.update(kw)
    return d


class _Pheno:
    def __init__(self, d): self._d = d
    def model_dump(self, **kw): return self._d


class _Assembler:
    def __init__(self, d): self._d = d
    def process(self, text, **kw): return _Pheno(self._d)


class _NoCandidates:
    def get_candidates(self, **kw): return []


def _run(note, specialist, llm, **cfg):
    pipe = ChainPipeline(assembler=_Assembler(specialist), extractor=object(),
                         candidate_service=_NoCandidates(),
                         llm_reasoner=(lambda t, d, dd: llm) if llm is not None else None)
    pipe.cfg.enable_preprocessing = False
    for k, v in cfg.items():
        setattr(pipe.cfg, k, v)
    return pipe.extract(note, document_id="D1", return_claims=True)


ED = ("At baseline he takes perampanel 8 mg nightly. "
      "At 18:51, Ativan (lorazepam) 4 mg IV was administered with brief cessation. "
      "He has about 2 seizures per month.")


def _spec_meds(*pairs):
    return {"document": {"doc_id": "x"},
            "medication": {"current_asms": [ev({"generic_name": g}, q, ED) for g, q in pairs]}}


def test_acute_dose_is_review_outside_current_asms():
    spec = _spec_meds(("perampanel", "perampanel 8 mg"), ("lorazepam", "lorazepam"))
    llm = {"document": {"doc_id": "x"},
           "medication": {"current_asms": [ev({"generic_name": "perampanel"}, "perampanel 8 mg")]}}
    stats, claims = _run(ED, spec, llm)
    acute = [c for c in claims if c.field_path == ACUTE_FIELD_PATH]
    assert len(acute) == 1 and stats.n_acute_rerouted == 1
    assert acute[0].validator_verdict == ValidatorVerdict.REVIEW
    assert ReasonCode.ACUTE_ADMINISTRATION in acute[0].reason_codes
    current = [c for c in claims if c.field_path == "medication.current_asms"]
    assert [c.validator_verdict for c in current] == [ValidatorVerdict.ACCEPT]


def test_acute_filter_can_be_switched_off():
    spec = _spec_meds(("lorazepam", "lorazepam"))
    _, claims = _run(ED, spec, None, acute_administration_filter=False)
    assert all(c.field_path == "medication.current_asms" for c in claims)


def test_specialist_only_drug_is_reviewed_when_llm_listed_other_drugs():
    note = "He takes perampanel 8 mg nightly and also lamotrigine 100 mg twice daily."
    spec = {"document": {"doc_id": "x"}, "medication": {"current_asms": [
        ev({"generic_name": "perampanel"}, "perampanel 8 mg", note),
        ev({"generic_name": "lamotrigine"}, "lamotrigine 100 mg", note)]}}
    llm = {"document": {"doc_id": "x"}, "medication": {"current_asms": [
        ev({"generic_name": "perampanel"}, "perampanel 8 mg")]}}
    stats, claims = _run(note, spec, llm)
    by = {c.value["generic_name"]: c for c in claims if c.field_path == "medication.current_asms"}
    assert by["perampanel"].validator_verdict == ValidatorVerdict.ACCEPT
    assert by["lamotrigine"].validator_verdict == ValidatorVerdict.REVIEW
    assert ReasonCode.SPECIALIST_ONLY_UNCONFIRMED in by["lamotrigine"].reason_codes
    assert stats.n_specialist_only_unconfirmed == 1
    # switched off: back to the earlier behaviour
    _, claims2 = _run(note, spec, llm, specialist_only_drug_review=False)
    lam = next(c for c in claims2 if c.value["generic_name"] == "lamotrigine")
    assert lam.validator_verdict == ValidatorVerdict.ACCEPT


def test_specialist_only_drug_is_not_demoted_when_llm_listed_no_drugs():
    # An LLM silent about medication gives no evidence against the specialist's drug.
    note = "He takes lamotrigine 100 mg twice daily."
    spec = {"document": {"doc_id": "x"}, "medication": {"current_asms": [
        ev({"generic_name": "lamotrigine"}, "lamotrigine 100 mg", note)]}}
    llm = {"document": {"doc_id": "x"},
           "clinical_seizure": {"epilepsy_type": ev("focal", "focal")}}
    _, claims = _run(note, spec, llm)
    lam = next(c for c in claims if c.field_path == "medication.current_asms")
    assert lam.validator_verdict == ValidatorVerdict.ACCEPT


def test_empty_specialist_frequency_does_not_reject_the_llm_value():
    placeholder = {"raw_text": "", "period": "unspecified", "count_min": None,
                   "count_max": None, "seizure_free": False}
    spec = {"document": {"doc_id": "x"},
            "clinical_seizure": {"seizure_frequency": ev(placeholder, "")}}
    llm_val = {"raw_text": "about 2 seizures per month", "period": "month",
               "count_min": 2, "count_max": 2, "seizure_free": False}
    llm = {"document": {"doc_id": "x"},
           "clinical_seizure": {"seizure_frequency": ev(llm_val, "about 2 seizures per month")}}
    stats, claims = _run(ED, spec, llm)
    freq = [c for c in claims if (c.field_path or "").endswith("seizure_frequency")]
    assert len(freq) == 1 and stats.n_empty_frequency_dropped == 1
    assert freq[0].detectors == ["llm"]
    assert freq[0].validator_verdict == ValidatorVerdict.REVIEW      # LLM-only: never auto-accepted
    assert ReasonCode.OFFSETS_UNRESOLVED not in freq[0].reason_codes
    assert "2 seizures per month" in freq[0].mention.text


def test_approximate_frequency_from_both_detectors_is_accepted():
    note = "He has about 2 seizures per month on lamotrigine."
    val = {"raw_text": "about 2 seizures per month", "period": "month", "count_min": 2,
           "count_max": 2, "seizure_free": False}
    spec = {"document": {"doc_id": "x"}, "clinical_seizure": {
        "seizure_frequency": ev(val, "about 2 seizures per month", note, certainty="probable")}}
    llm = {"document": {"doc_id": "x"}, "clinical_seizure": {
        "seizure_frequency": ev(val, "about 2 seizures per month")}}
    _, claims = _run(note, spec, llm)
    f = next(c for c in claims if (c.field_path or "").endswith("seizure_frequency"))
    assert f.validator_verdict == ValidatorVerdict.ACCEPT
    # a hedged frequency is not an approximation and still goes to review
    spec["clinical_seizure"]["seizure_frequency"]["certainty"] = "possible"
    _, claims = _run(note, spec, llm)
    f = next(c for c in claims if (c.field_path or "").endswith("seizure_frequency"))
    assert f.validator_verdict == ValidatorVerdict.REVIEW
    # switch off: approximate frequency stays in review
    spec["clinical_seizure"]["seizure_frequency"]["certainty"] = "probable"
    _, claims = _run(note, spec, llm, approx_frequency_is_asserted=False)
    f = next(c for c in claims if (c.field_path or "").endswith("seizure_frequency"))
    assert f.validator_verdict == ValidatorVerdict.REVIEW
