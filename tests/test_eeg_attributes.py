"""IED attributes (frequency band, recurrence, dispersal) and EEG-report section scope."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from rules.eeg_attributes import band_from_hz, ied_attributes
from rules.eeg_sections import in_finding_section, is_eeg_report, section_at
from rules.fields.eeg import IedFindingsRule, IedPresentRule, _collect_ieds
from rules.fields.eeg_extra import EegIctalOnsetLobeRule
from schema.enums import DocumentType, FrequencyBand, IedDispersal, IedRecurrence, LobarLocalization

_META = {"doc_id": "eeg-attr", "doc_type": DocumentType.EEG_REPORT, "doc_date": date(2020, 1, 1)}
_REPORT = (
    "CLINICAL HISTORY: Prior EEG showed left temporal spikes.\n"
    "MEDICATIONS: Keppra.\n"
    "INTRODUCTION: Digital EEG using the 10-20 system.\n"
    "DESCRIPTION OF THE RECORD: Frequent right temporal sharp waves at 6 Hz.\n"
    "IMPRESSION: Frequent right temporal sharp waves.\n"
    "CLINICAL CORRELATION: Consistent with temporal lobe epilepsy.\n"
)


def _doc(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


def test_band_from_hz():
    assert band_from_hz(2.5) == FrequencyBand.DELTA
    assert band_from_hz(6) == FrequencyBand.THETA
    assert band_from_hz(10) == FrequencyBand.ALPHA
    assert band_from_hz(18) == FrequencyBand.BETA
    assert band_from_hz(40) == FrequencyBand.GAMMA
    assert band_from_hz(None) is None


def test_attributes_from_words_and_hz():
    text = "EEG: occasional left temporal theta sharp waves, focal."
    s = text.index("sharp")
    band, rec, disp = ied_attributes(text, s, s + 11, hz=None)
    assert band == FrequencyBand.THETA
    assert rec == IedRecurrence.OCCASIONAL
    assert disp == IedDispersal.FOCAL
    text = "EEG: abundant 3 Hz spike-and-wave, generalized."
    s = text.index("spike")
    band, rec, disp = ied_attributes(text, s, s + 15, hz=3.0)
    assert band == FrequencyBand.DELTA
    assert rec == IedRecurrence.ABUNDANT
    assert disp == IedDispersal.GENERALIZED


def test_clinic_letter_is_not_an_eeg_report():
    letter = ("Dear colleague, Investigations: EEG showed left temporal sharp waves. "
              "Impression: focal epilepsy.")
    assert not is_eeg_report(letter)
    assert in_finding_section(letter, letter.index("sharp"))
    hits = _collect_ieds([], _doc(letter))
    assert hits and hits[0][5] == LobarLocalization.TEMPORAL


def test_eeg_report_skips_history_keeps_description():
    assert is_eeg_report(_REPORT)
    assert section_at(_REPORT, _REPORT.index("Prior EEG")) == "clinical history"
    assert not in_finding_section(_REPORT, _REPORT.index("left temporal spikes"))
    assert in_finding_section(_REPORT, _REPORT.index("Frequent right"))
    hits = _collect_ieds([], _doc(_REPORT))
    assert len(hits) == 1
    assert hits[0][4].value == "right" and hits[0][5] == LobarLocalization.TEMPORAL
    ev = IedFindingsRule().apply([], _doc(_REPORT), _META)
    assert ev and ev[0].value.recurrence == IedRecurrence.FREQUENT
    assert ev[0].value.frequency_band == FrequencyBand.THETA
    assert IedPresentRule().apply([], _doc(_REPORT), _META).value is True


def test_ictal_onset_in_history_is_ignored_on_eeg_report():
    text = (
        "CLINICAL HISTORY: Prior video-EEG with ictal onset from the left frontal region.\n"
        "INTRODUCTION: 21-channel EEG.\n"
        "DESCRIPTION OF THE RECORD: Background is normal. No seizures recorded.\n"
        "IMPRESSION: Normal EEG.\n"
    )
    assert EegIctalOnsetLobeRule().apply([], _doc(text), _META) is None
    clinic = "Video EEG captured two seizures. Ictal onset from the left frontal region."
    assert EegIctalOnsetLobeRule().apply([], _doc(clinic), _META).value == LobarLocalization.FRONTAL
