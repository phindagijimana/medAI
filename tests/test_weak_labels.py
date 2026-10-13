"""Weak labels wrap existing EpExtra rules and abstain when the rule is silent."""

from rules.weak_labels import weak_labels


def test_weak_labels_emit_and_abstain():
    hit = weak_labels("She has focal epilepsy. EEG: frequent left temporal sharp waves.")
    assert hit["clinical_seizure.epilepsy_type"] == "focal"
    assert hit["eeg.ied_present"] is True
    assert "clinical_seizure.pnes_status" not in hit
    pnes = weak_labels("These events are psychogenic non-epileptic seizures, not epilepsy.")
    assert pnes["clinical_seizure.pnes_status"] == "pnes_only"
    empty = weak_labels("Seen in clinic. Blood pressure was normal.")
    assert empty == {}
