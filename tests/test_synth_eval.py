"""Synthetic evaluation set helpers and patient-level aggregation (no GPU)."""

from scripts.score_leo_vs_synth_gold import _vote, aggregate
from services import synth_eval


def test_vote_prefers_majority_then_later_note():
    assert _vote([None, "a", "b", "b"]) == "b"
    assert _vote(["a", "b"]) == "b"          # tie -> later note
    assert _vote([None, None]) is None


def test_aggregate_union_of_drugs_and_joint_frequency_vote():
    notes = [
        {"current_asms": ["lamotrigine"], "epilepsy_type": "focal",
         "seizure_frequency.period": None, "seizure_frequency.count_min": None,
         "seizure_frequency.count_max": None},
        {"current_asms": ["levetiracetam"], "epilepsy_type": "focal",
         "seizure_frequency.period": "month", "seizure_frequency.count_min": 2.0,
         "seizure_frequency.count_max": 2.0},
    ]
    a = aggregate(notes)
    assert a["current_asms"] == ["lamotrigine", "levetiracetam"]
    assert a["epilepsy_type"] == "focal"
    assert (a["seizure_frequency.period"], a["seizure_frequency.count_min"]) == ("month", 2.0)


def test_eval_strata_are_disjoint_from_adapter_training_patients():
    s = synth_eval.eval_patients()
    assert len(s["polish_val"]) == 10 and len(s["synth_v3"]) == 20
    assert all(p.startswith("P004") for p in s["polish_val"])
    assert all(p.startswith("P003") for p in s["synth_v3"])
