"""PNES flag (rules.pnes) and the review routing it drives."""

from __future__ import annotations

from schema.claim import ReasonCode, ValidatorVerdict
from rules.pnes import PNES_PATH, pnes_status
from test_seizure_free import _claims, _f

BASE = "Seizure type and frequency: focal seizures with altered awareness, about 2 per month. "


def _value(text):
    hit = pnes_status(text)
    return hit and hit[:2]


def test_pnes_only():
    assert _value("Diagnosis: Dissociative seizures. She has about 2 per month.") == ("pnes_only", "definite")
    assert _value("I do not think that these are epileptic seizures and are more likely to be dissociative seizures."
                  ) == ("pnes_only", "probable")
    assert _value("She does not need to take her epilim for epilepsy as she has non epileptic seizures."
                  )[0] == "pnes_only"


def test_dual_diagnosis():
    assert _value("Diagnosis: Juvenile myoclonic epilepsy. Dissociative seizures.")[0] == "pnes_and_epilepsy"
    assert _value("Diagnosis:\n complex partial seizures\nPsychogenic nonepileptic attack disorder\n"
                  )[0] == "pnes_and_epilepsy"
    assert _value("She has a combination of epileptic and nonepileptic events.")[0] == "pnes_and_epilepsy"


def test_hedged_and_negated():
    assert _value("I wonder if these could be non epileptic rather than epileptic seizures.")[0] == "pnes_possible"
    assert _value("We should keep in mind the possibility of non epileptic attacks.")[0] == "pnes_possible"
    assert _value("There is no evidence of dissociative seizures. Focal epilepsy.") is None


def test_letterhead_is_not_an_epilepsy_diagnosis():
    assert _value("The epilepsy service\nDiagnosis: Dissociative seizures.")[0] == "pnes_only"


def test_no_pnes_term():
    assert pnes_status("Focal epilepsy, 2 seizures per month. Functional status good.") is None


def test_pnes_only_sends_agreed_frequency_to_review():
    by = _claims(_f(2, 2), _f(2, 2), note=BASE + "Diagnosis: Dissociative seizures.")
    freq = by["clinical_seizure.seizure_frequency"]
    assert freq.validator_verdict == ValidatorVerdict.REVIEW
    assert ReasonCode.PNES_DOCUMENTED in freq.reason_codes
    assert by[PNES_PATH].value == "pnes_only"


def test_possible_pnes_changes_no_routing():
    by = _claims(_f(2, 2), _f(2, 2), note=BASE + "I wonder if these could be dissociative seizures.")
    assert by["clinical_seizure.seizure_frequency"].validator_verdict == ValidatorVerdict.ACCEPT
    assert by[PNES_PATH].value == "pnes_possible"


def test_switch_off():
    by = _claims(_f(2, 2), _f(2, 2), note=BASE + "Diagnosis: Dissociative seizures.", pnes_check=False)
    assert PNES_PATH not in by
    assert by["clinical_seizure.seizure_frequency"].validator_verdict == ValidatorVerdict.ACCEPT
