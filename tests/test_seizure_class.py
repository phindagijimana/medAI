"""Two-level seizure-type agreement: onset class fused on its own, subtype unchanged."""

from __future__ import annotations

from schema.claim import ValidatorVerdict
from services.chain_pipeline import ChainPipeline
from services.seizure_class import ONSET_CLASS_PATH, SEIZURE_TYPE_PATH, onset_class

NOTE = ("Focal epilepsy. She has focal seizures with impaired awareness, "
        "sometimes aware focal seizures, about twice a month.")


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


def _pheno(seizure_type, quote):
    return {
        "document": {"doc_id": "x"},
        "clinical_seizure": {
            "predominant_seizure_type": {
                "value": seizure_type, "certainty": "definite", "temporal_status": "current",
                "evidence_text": quote, "char_start": None, "char_end": None},
        },
    }


def _claims(spec_type, llm_type, onset_on=True):
    pipe = ChainPipeline(assembler=_Assembler(_pheno(spec_type, "focal seizures with impaired awareness")),
                         extractor=object(), candidate_service=_NoCandidates(),
                         llm_reasoner=lambda t, d, dd: _pheno(llm_type, "aware focal seizures"))
    pipe.cfg.enable_preprocessing = False
    pipe.cfg.seizure_onset_class = onset_on
    _, claims = pipe.extract(NOTE, document_id="D1", return_claims=True)
    return {c.field_path: c for c in claims}


def test_onset_class_mapping():
    assert onset_class("focal_aware") == "focal"
    assert onset_class("focal_to_bilateral_tonic_clonic") == "focal"
    assert onset_class("generalized_absence_typical") == "generalized"
    assert onset_class("absence_typical") == "generalized"
    assert onset_class("unknown_onset_tonic_clonic") == "unknown_onset"
    assert onset_class("unclassified") is None
    assert onset_class("tonic_clonic") is None
    assert onset_class(None) is None


def test_subtype_disagreement_keeps_review_but_class_is_accepted():
    by = _claims("focal_impaired_awareness", "focal_aware")
    assert by[SEIZURE_TYPE_PATH].validator_verdict == ValidatorVerdict.REVIEW
    cls = by[ONSET_CLASS_PATH]
    assert cls.value == "focal"
    assert cls.validator_verdict == ValidatorVerdict.ACCEPT


def test_class_disagreement_goes_to_review():
    by = _claims("focal_impaired_awareness", "generalized_tonic_clonic")
    assert by[ONSET_CLASS_PATH].validator_verdict == ValidatorVerdict.REVIEW


def test_switch_off_emits_no_class_claim():
    by = _claims("focal_impaired_awareness", "focal_aware", onset_on=False)
    assert ONSET_CLASS_PATH not in by
    assert by[SEIZURE_TYPE_PATH].validator_verdict == ValidatorVerdict.REVIEW
