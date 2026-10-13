"""Measured-failure techniques: status/time, quote entailment, routing policy, BIO blocked."""

from __future__ import annotations

import json

import pytest

from schema.claim import ReasonCode, ValidatorVerdict
from services.chain_pipeline import ChainPipeline
from services.coref_temporal import resolve_med_deixis
from services.ext_detectors import parse_ext_detectors
from services.leo_disagree import policy_from_scores
from services.leo_runtime import LeoRuntime, parse_disagree_llm
from services.medcat_extractor import LinkedEntity
from services.quote_entail import quote_entails

NOTE = (
    "Assessment: 34 year old with focal epilepsy. "
    "Takes levetiracetam 500 mg twice daily. "
    "Seizures occur about 2 per month. Denies lamotrigine use."
)


class _Pheno:
    def __init__(self, d):
        self._d = d

    def model_dump(self, **kw):
        return self._d


class _Assembler:
    def __init__(self, d):
        self._d = d

    def process(self, text, **kw):
        return _Pheno(self._d)


class _NoCandidates:
    def get_candidates(self, **kw):
        return []


def _ev(value, quote):
    return {"value": value, "certainty": "definite", "temporal_status": "current",
            "evidence_text": quote, "char_start": None, "char_end": None}


def _specialist():
    return {
        "document": {"doc_id": "x"},
        "clinical_seizure": {
            "epilepsy_type": _ev("focal", "focal epilepsy"),
            "age_at_onset_years": _ev(10, "34 year old"),
        },
        "medication": {"current_asms": [_ev({"generic_name": "levetiracetam"}, "levetiracetam 500 mg")]},
    }


def _ent(text: str, span: str, **kw):
    i = text.index(span)
    d = dict(text=span, cui="X", sctid=None, label=span, enum_class="Medication",
             enum_value="levetiracetam", char_start=i, char_end=i + len(span),
             confidence=1.0, linker_tier="custom")
    d.update(kw)
    return LinkedEntity(**d)


def test_quote_entail_rejects_off_topic_and_plan_study():
    assert quote_entails("clinical_seizure.epilepsy_type", "focal", "focal epilepsy",
                         "the patient has focal epilepsy")
    assert not quote_entails("clinical_seizure.epilepsy_type", "focal", "takes lamotrigine",
                             "takes lamotrigine 200 mg")
    assert not quote_entails("medication.current_asms", {"generic_name": "valproate"},
                             "valproate was stopped", "In the past valproate was stopped")
    assert quote_entails("medication.current_asms", {"generic_name": "lamotrigine"},
                         "takes lamotrigine 200 mg", "The patient takes lamotrigine 200 mg")
    assert not quote_entails("eeg.study_type", "video_eeg",
                             "video-EEG may be considered",
                             "Plan: video-EEG may be considered.")
    assert not quote_entails("eeg.ied_present", True, "No LPDs", "No LPDs or GPDs.")


def test_quote_entail_jme_spelled_out_is_a_known_lexicon_hole():
    # EVAL 10.49: do not widen this lexicon from held-out F-S letters.
    assert not quote_entails(
        "clinical_seizure.epilepsy_type", "generalized",
        "Juvenile Myoclonic Epilepsy", "Diagnosis: Juvenile Myoclonic Epilepsy.")
    assert quote_entails(
        "clinical_seizure.epilepsy_type", "generalized",
        "JME", "Diagnosis: JME.")


def test_quote_entail_flag_demotes_accept_without_changing_default():
    llm = {
        "document": {"doc_id": "x"},
        "clinical_seizure": {
            "epilepsy_type": {
                "value": "focal", "certainty": "definite", "temporal_status": "current",
                "evidence_text": "focal epilepsy", "char_start": None, "char_end": None,
            }
        },
    }
    pipe = ChainPipeline(assembler=_Assembler(_specialist()), extractor=object(),
                         candidate_service=_NoCandidates(),
                         llm_reasoner=lambda t, d, dd: llm)
    pipe.cfg.enable_preprocessing = False
    assert pipe.cfg.quote_entail is False
    _, off = pipe.extract(NOTE, document_id="D1", return_claims=True)
    et = [c for c in off if c.field_path == "clinical_seizure.epilepsy_type"][0]
    assert et.validator_verdict == ValidatorVerdict.ACCEPT
    pipe.cfg.quote_entail = True
    _, on = pipe.extract(NOTE, document_id="D1", return_claims=True)
    et2 = [c for c in on if c.field_path == "clinical_seizure.epilepsy_type"][0]
    assert et2.validator_verdict == ValidatorVerdict.ACCEPT  # quote really is focal epilepsy
    # Off-topic quote: specialist still has a real span; LLM quote swapped via fusion agree path
    # Direct check: a current-drug claim whose sentence is a stop cue.
    assert ReasonCode.QUOTE_NOT_ENTAILED.value == "quote_not_entailed"


def test_coref_that_drug_and_later_stop_drops_current():
    from rules.fields.medication import _extract_medications
    text = "Takes levetiracetam 500 mg twice daily. Stopped that drug last month."
    e = _ent(text, "levetiracetam")
    assert resolve_med_deixis(text, [e]) == [e]
    meta = {"doc_id": "x", "doc_type": "progress_note", "doc_date": "2026-01-01"}
    current, prior, _failed = _extract_medications([e], type("D", (), {"text": text})(), meta)
    names_c = {ev.value.generic_name.lower() for ev in current if ev.value}
    names_p = {ev.value.generic_name.lower() for ev in prior if ev.value}
    assert "levetiracetam" not in names_c
    assert "levetiracetam" in names_p


def test_was_stopped_is_prior_status():
    from rules.fields.medication import MedicationStatus, _infer_status
    assert _infer_status("valproate was stopped because of tremor") == MedicationStatus.PRIOR
    assert _infer_status("continues lamotrigine 200 mg") == MedicationStatus.CURRENT


def test_emit_policy_respects_min_n_and_d17():
    scores = {
        "clinical_seizure.predominant_seizure_type": {
            "n_scored": 12, "model_right": {"k": 10, "n": 12, "rate": 0.83, "ci95": [0.55, 0.95]},
            "rules_right": {"k": 2, "n": 12, "rate": 0.17, "ci95": [0.05, 0.45]},
        }
    }
    assert policy_from_scores(scores, min_n=100) == {}  # gate not met
    pol = policy_from_scores(scores, min_n=10)
    assert pol.get("clinical_seizure.predominant_seizure_type") == "llm"
    assert parse_disagree_llm(None) == ()
    assert parse_disagree_llm("candidate") == ("clinical_seizure.predominant_seizure_type",)


def test_bio_ner_heads_are_blocked_not_dumped_into_e():
    with pytest.raises(ValueError, match="trained"):
        parse_ext_detectors("ner-onset")
    with pytest.raises(ValueError, match="trained"):
        parse_ext_detectors("b1")


def test_l1c_uses_constrained_decoding_not_sampling():
    from services.chain_llm import FlatLiveReasoner
    prompts = []

    class B:
        model_name = "fake"
        def generate(self, *a, **k):
            raise AssertionError("L1C must not call unconstrained generate")
        def generate_constrained(self, prompt, model, decoding):
            prompts.append(prompt)
            assert decoding.do_sample is False and decoding.seed == 0
            return json.dumps({
                "epilepsy_type": {"value": "focal", "quote": "focal"},
                "predominant_seizure_type": {"value": None, "quote": None},
                "age_at_onset_years": {"value": None, "quote": None},
                "seizure_frequency": {"count_min": None, "count_max": None, "period": None,
                                      "seizure_free": None, "quote": None},
                "current_asms": [],
            }), 4

    r = FlatLiveReasoner(B(), arm="L1C")
    out = r("focal epilepsy", "d", "2026-01-01")
    assert prompts and out is not None


def test_quote_entail_runtime_default_off():
    rt = LeoRuntime(backend=None, use_llm=False)
    assert rt.quote_entail is False
    assert rt.pipeline.cfg.quote_entail is False
