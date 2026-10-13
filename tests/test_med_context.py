"""CMED context dimensions and CASI status from EpExtra's medication cues (sentences written for the test)."""

from __future__ import annotations

from rules.med_context import casi_status, cmed_context, drug_spans


def _ctx(text: str, drug: str):
    s, e = drug_spans(text, drug)[0]
    return cmed_context(text, s, e)


def test_action_dimension():
    assert _ctx("Lamotrigine was stopped because of a rash.", "Lamotrigine").action == "Stop"
    assert _ctx("We will increase levetiracetam to 1000 mg twice daily.", "levetiracetam").action == "Increase"
    assert _ctx("Please reduce carbamazepine to 200 mg.", "carbamazepine").action == "Decrease"
    assert _ctx("Please start lacosamide 50 mg bd.", "lacosamide").action == "Start"
    assert _ctx("She was switched to zonisamide.", "zonisamide").action == "OtherChange"
    assert _ctx("A loading dose of phenytoin was given.", "phenytoin").action == "UniqueDose"
    c = _ctx("She takes lamotrigine 100 mg twice daily.", "lamotrigine")
    assert c.action == "" and c.disposition == "NoDisposition" and c.temporality == "Present"


def test_temporality_certainty_negation_actor():
    assert _ctx("Lamotrigine to start next week.", "Lamotrigine").temporality == "Future"
    assert _ctx("She was previously on valproate.", "valproate").temporality == "Past"
    assert _ctx("If seizures recur we could add clobazam.", "clobazam").certainty == "Conditional"
    assert _ctx("Perampanel may be an option.", "Perampanel").certainty == "Hypothetical"
    assert _ctx("She declined topiramate.", "topiramate").negation == "Negated"
    assert _ctx("She stopped levetiracetam herself.", "levetiracetam").actor == "Patient"
    assert _ctx("I would recommend increasing lamotrigine.", "lamotrigine").actor == "Physician"


def test_casi_status_per_drug():
    note = ("She remains on lamotrigine 200 mg bd. Levetiracetam was discontinued because of mood change. "
            "We discussed perampanel as a possible future option. She declined topiramate.")
    assert casi_status(note, "lamotrigine") == "active"
    assert casi_status(note, "levetiracetam") == "discontinued"
    assert casi_status(note, "perampanel") == "neither"
    assert casi_status(note, "topiramate") == "neither"
    assert casi_status(note, "clobazam") is None


def test_casi_status_restart_after_stop_is_active():
    note = "Carbamazepine was stopped in 2019. She is now taking carbamazepine again, 200 mg bd."
    assert casi_status(note, "carbamazepine") == "active"


def test_casi_parser_handles_both_column_layouts():
    from scripts.score_casi_medication_status import gold_pairs
    text = "She remains on lisinopril. Metformin was discontinued. Consider aspirin."
    three = {"snippet": text, "active_medications": '["lisinopril"]', "discontinued_medications": '["Metformin"]',
             "neither_medications": '["aspirin"]'}
    one = {"snippet": text, "label": '{"active": ["lisinopril"], "discontinued": ["Metformin"], "neither": ["aspirin"]}'}
    want = {("lisinopril", "active"), ("Metformin", "discontinued"), ("aspirin", "neither")}
    for row in (three, one):
        t, pairs = gold_pairs(row)
        assert t == text and set(pairs) == want
        assert {(n, casi_status(t, n)) for n, _ in pairs} == want


def test_drug_spans_whole_word():
    assert drug_spans("Keppra and keppra XR", "keppra") == [(0, 6), (11, 17)]
    assert drug_spans("Depakote", "Depak") == []
