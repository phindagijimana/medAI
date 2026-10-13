"""Seizure freedom fused on its own; explicit date of the last seizure from the rules."""

from __future__ import annotations

from schema.claim import ValidatorVerdict
from services.chain_pipeline import ChainPipeline
from services.seizure_free import (
    LAST_SEIZURE_PATH, SEIZURE_FREE_PATH, date_matches, last_seizure_date, last_seizure_dates, seizure_free_value,
)

NOTE = ("Seizure type and frequency: focal seizures with altered awareness, about 2 per month. "
        "Focal to bilateral convulsive seizures, last event October 2019.")


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


def _pheno(freq, quote="about 2 per month"):
    return {
        "document": {"doc_id": "x"},
        "clinical_seizure": {
            "seizure_frequency": {"value": freq, "certainty": "definite", "temporal_status": "current",
                                  "evidence_text": quote, "char_start": None, "char_end": None},
        },
    }


def _claims(spec_freq, llm_freq, note=NOTE, **cfg):
    pipe = ChainPipeline(assembler=_Assembler(_pheno(spec_freq)), extractor=object(),
                         candidate_service=_NoCandidates(),
                         llm_reasoner=(lambda t, d, dd: _pheno(llm_freq)) if llm_freq is not None else None)
    pipe.cfg.enable_preprocessing = False
    for k, v in cfg.items():
        setattr(pipe.cfg, k, v)
    _, claims = pipe.extract(note, document_id="D1", return_claims=True)
    return {c.field_path: c for c in claims}


def _f(lo, hi, period="month", free=False):
    return {"count_min": lo, "count_max": hi, "period": period, "seizure_free": free}


def test_seizure_free_value():
    assert seizure_free_value(_f(None, None, None, True)) is True
    assert seizure_free_value(_f(0, 0)) is True
    assert seizure_free_value(_f(2, 3)) is False
    assert seizure_free_value(_f(None, None, "month", False)) is None
    assert seizure_free_value(None) is None


def test_rate_disagreement_still_agrees_not_seizure_free():
    by = _claims(_f(2, 2), _f(6, 6))
    assert by["clinical_seizure.seizure_frequency"].validator_verdict == ValidatorVerdict.REVIEW
    sf = by[SEIZURE_FREE_PATH]
    assert sf.value is False
    assert sf.validator_verdict == ValidatorVerdict.ACCEPT


def test_seizure_free_disagreement_goes_to_review():
    by = _claims(_f(None, None, None, True), _f(2, 2))
    assert by[SEIZURE_FREE_PATH].validator_verdict == ValidatorVerdict.REVIEW


def test_last_seizure_dates_from_letter_phrasings():
    assert last_seizure_date("Generalised tonic clonic seizure-last event July 2016.")[0] == "2016-07"
    assert last_seizure_date("his last one was on Christmas day 2009")[0] == "2009-12"
    assert last_seizure_date("no seizures since Christmas 2015")[0] == "2015-12"
    assert last_seizure_date("has not had any further generalised tonic clonic seizures since August 2016")[0] \
        == "2016-08"
    assert last_seizure_date("His last seizure was in February 2005")[0] == "2005-02"
    assert last_seizure_date("Focal to bilateral convulsive seizures, last event 2013")[0] == "2013"
    assert last_seizure_date("last episode was on 31st August 2018")[0] == "2018-08-31"


def test_latest_date_wins_and_numeric_dates_keep_only_unambiguous_parts():
    assert last_seizure_date("Convulsive seizures, last event 2015. Focal seizures, last event 2017.")[0] == "2017"
    assert last_seizure_date("last seizure 03/06/2007")[0] == "2007"
    assert last_seizure_date("last seizure 23/05/2019")[0] == "2019-05-23"


def test_no_date_from_non_seizure_or_unrelated_dates():
    assert last_seizure_dates("Last EEG in 2015 was normal. CT head 1/3/2015 showed gliosis.") == []
    assert last_seizure_dates("Seizure free for 7 months.") == []
    assert last_seizure_dates("has not been seen by neurology since 2010") == []


def test_date_matches_at_gold_precision():
    assert date_matches("2016-07", "2016-07")
    assert date_matches("2016-07-03", "2016-07")
    assert date_matches("2016-07", "2016")
    assert not date_matches("2016", "2016-07")
    assert not date_matches("2016-08", "2016-07")


def test_last_seizure_claim_is_specialist_only_review_when_model_ran():
    by = _claims(_f(2, 2), _f(2, 2))
    c = by[LAST_SEIZURE_PATH]
    assert c.value == "2019-10"
    assert c.validator_verdict == ValidatorVerdict.REVIEW


def test_switches_off_emit_nothing():
    by = _claims(_f(2, 2), _f(6, 6), seizure_free_field=False, last_seizure_field=False)
    assert SEIZURE_FREE_PATH not in by and LAST_SEIZURE_PATH not in by
