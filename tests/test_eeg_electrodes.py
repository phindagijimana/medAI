"""Scalp electrode names give the lobe and side of an EEG finding (Cui et al. 2014, PEEP)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from rules.eeg_electrodes import electrode_lobe, electrode_location, electrode_side, find_electrodes
from rules.fields.eeg import _collect_ieds
from rules.fields.eeg_extra import EegIctalOnsetLateralityRule, EegIctalOnsetLobeRule
from schema.enums import DocumentType, Laterality, LobarLocalization

_META = {"doc_id": "electrodes", "doc_type": DocumentType.PROGRESS_NOTE, "doc_date": date(2020, 1, 1)}


def _doc(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


def test_10_20_mapping():
    assert electrode_side("7") == Laterality.LEFT
    assert electrode_side("8") == Laterality.RIGHT
    assert electrode_side("z") == Laterality.MIDLINE
    assert electrode_lobe("Fp", "1") == LobarLocalization.FRONTAL
    assert electrode_lobe("F", "3") == LobarLocalization.FRONTAL
    assert electrode_lobe("T", "4") == LobarLocalization.TEMPORAL       # old name of T8
    assert electrode_lobe("T", "6") == LobarLocalization.TEMPORAL       # old name of P8
    assert electrode_lobe("P", "8") == LobarLocalization.TEMPORAL       # posterior temporal
    assert electrode_lobe("P", "4") == LobarLocalization.PARIETAL
    assert electrode_lobe("O", "1") == LobarLocalization.OCCIPITAL
    assert electrode_lobe("C", "3") is None                              # central: no schema lobe


def test_location_from_electrodes():
    text = "Sharp waves maximal at T8 and P8."
    s = text.index("Sharp")
    assert electrode_location(text, s, s + 11) == (Laterality.RIGHT, LobarLocalization.TEMPORAL)
    text = "Spikes with phase reversal at F3."
    assert electrode_location(text, 0, 6) == (Laterality.LEFT, LobarLocalization.FRONTAL)
    text = "Spikes seen at F7 and F8 independently."
    assert electrode_location(text, 0, 6) == (Laterality.BILATERAL, LobarLocalization.FRONTAL)
    text = "Sharp waves at F7 and T7."
    assert electrode_location(text, 0, 11) == (Laterality.LEFT, None)  # two lobes: lobe left empty


def test_lone_name_without_eeg_cue_is_not_an_electrode():
    text = "TSH normal, T4 12 pmol/L."
    assert find_electrodes(text, 0, len(text)) == []
    assert find_electrodes("Disc bulge at C5 level.", 0, 23) == []     # "at" alone is not an EEG cue
    assert find_electrodes("max at T4", 0, 9)
    assert find_electrodes("phase reversal at C3", 0, 20)


def test_ied_rule_uses_electrodes_only_when_no_word():
    hits = _collect_ieds([], _doc("EEG: frequent sharp waves, maximal at T8."))
    assert hits and hits[0][4] == Laterality.RIGHT and hits[0][5] == LobarLocalization.TEMPORAL
    hits = _collect_ieds([], _doc("EEG: left frontal sharp waves, maximal at T8."))
    assert hits[0][4] == Laterality.LEFT and hits[0][5] == LobarLocalization.FRONTAL


def test_generalized_discharge_gets_no_lobe_from_electrodes():
    text = ("EEG. Interictal findings: Occasional bursts of bilaterally synchronous, generalized "
            "spike-and-wave and polyspike-and-wave discharges were present, maximal over the "
            "bifrontal regions at Fp1/Fp2 and F3/F4, with a broad bilateral field.")
    hits = _collect_ieds([], _doc(text))
    assert hits and all(h[5] is None for h in hits)


def test_ictal_onset_from_electrodes():
    doc = _doc("Video EEG captured two seizures. Ictal onset with rhythmic theta at F4 and Fp2.")
    lobe = EegIctalOnsetLobeRule().apply([], doc, _META)
    side = EegIctalOnsetLateralityRule().apply([], doc, _META)
    assert lobe.value == LobarLocalization.FRONTAL
    assert side.value == Laterality.RIGHT
