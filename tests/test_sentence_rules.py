"""Sentence-level reading in the surgery, MRI and drug-resistance rules (plain text patterns, no model)."""

from types import SimpleNamespace

import pytest

from rules import sentence_context as sc
from rules.compound import _stated_drug_response
from rules.fields.mri import MriFcdRule, MriHippocampalSclerosisRule, MriOverallNormalRule
from rules.fields.surgery import SurgeryHistoryRule
from schema.enums import DrugResistanceStatus

META = {"doc_id": "d", "doc_type": "progress_note", "doc_date": "2024-01-01"}


def _surgery(text):
    out = SurgeryHistoryRule().apply([], SimpleNamespace(text=text), META) or []
    return sorted(e.value.surgery_type.value for e in out)


@pytest.mark.parametrize("text", [
    "Past Surgical History:\n- No epilepsy surgery documented.",
    "There is no documentation available here regarding prior epilepsy surgery, vagus nerve stimulation, or deep brain stimulation.",
    "Prior epilepsy surgery or neuromodulation is not documented.",
    "Likewise, no new device implantation, resection, laser ablation, or neuromodulation procedure is documented.",
    "Future options could include resective treatment or neuromodulation with VNS, RNS, or DBS.",
    "Candidacy for resection, laser ablation, RNS, or DBS will be discussed.",
    "At present, I would not pursue EMU admission, VNS, RNS, or DBS.",
    "If not previously completed, consider referral for comprehensive epilepsy surgery evaluation.",
])
def test_surgery_options_and_absence_are_not_history(text):
    assert _surgery(text) == []


@pytest.mark.parametrize("text,expected", [
    ("She is s/p VNS implant in 2018 with benefit.", ["neurostimulation_vns"]),
    ("Underwent anterior temporal lobectomy in 2015.", ["resection"]),
    ("Past Surgical History: VNS 2018", ["neurostimulation_vns"]),
    ("VNS in place since 2019; considering resection.", ["neurostimulation_vns"]),
    ("He had prior epilepsy surgery in 2012.", ["unknown"]),
    ("No seizures since VNS in 2018.", ["neurostimulation_vns"]),
])
def test_surgery_that_happened_is_kept(text, expected):
    assert _surgery(text) == expected


def _mri(rule, text):
    ev = rule.apply([], SimpleNamespace(text=text), META)
    return None if ev is None else (ev.value, ev.certainty.value)


def test_negated_mri_findings_are_false_and_hedged_ones_are_not_true_with_certainty():
    t = "MRI brain was reported as normal. No identified lesion, including MTS or another focal abnormality."
    assert _mri(MriHippocampalSclerosisRule(), t)[0] is False
    assert _mri(MriOverallNormalRule(), t)[0] is True
    t2 = "MRI showed no focal cortical dysplasia."
    assert _mri(MriFcdRule(), t2)[0] is False
    hedged = "MRI was normal, but another report described a probable abnormality consistent with MTS."
    assert _mri(MriHippocampalSclerosisRule(), hedged) == (True, "possible")
    assert _mri(MriOverallNormalRule(), hedged)[0] is True          # a hedged finding does not make the MRI abnormal
    assert _mri(MriFcdRule(), "MRI demonstrated focal cortical dysplasia.")[0] is True
    assert _mri(MriFcdRule(), "Brain MRI was reviewed.") is None   # absence is not stated: no value


@pytest.mark.parametrize("text,status", [
    ("Drug-resistant epilepsy on three agents.", DrugResistanceStatus.DRUG_RESISTANT),
    ("Assessment: drug-responsive epilepsy.", DrugResistanceStatus.DRUG_RESPONSIVE),
    ("Not drug-resistant at present.", None),
    ("The information does not establish drug-resistant epilepsy.", None),
    ("Criteria for drug-resistant epilepsy have not been met.", None),
    ("Reassess if seizures become drug resistant.", None),
])
def test_drug_resistance_statements_are_read_in_their_sentence(text, status):
    got = _stated_drug_response(text)
    assert (got[1] if got else None) == status


def test_the_later_statement_wins():
    got = _stated_drug_response("Drug-resistant epilepsy in 2019.\n\nNow drug-responsive after surgery.")
    assert got[1] == DrugResistanceStatus.DRUG_RESPONSIVE


def test_sentence_helpers():
    t = "He is seizure free. VNS was placed in 2018; no records of settings."
    i = t.index("VNS")
    assert not sc.negated(t, i, i + 3)          # the second clause is a separate sentence
    assert not sc.option_only(t, i, i + 3)
