"""EpExtra current ASMs: current at the visit, abbreviations, misspellings."""

from __future__ import annotations

import re

from rules.asm_surface import fuzzy_drug, surface_matches
from rules.fields.medication import _extract_medications, canonicalize_drug_name
from services.medcat_extractor import LinkedEntity

META = {"doc_id": "x", "doc_type": "progress_note", "doc_date": "2026-01-01"}


def _ents(text: str, *drugs: str) -> list[LinkedEntity]:
    out = []
    for d in drugs:
        for m in re.finditer(re.escape(d), text):
            out.append(LinkedEntity(
                text=d, cui="X", sctid=None, label=d, enum_class="Medication",
                enum_value=d.lower(), char_start=m.start(), char_end=m.end(),
                confidence=1.0, linker_tier="custom"))
    return sorted(out, key=lambda e: e.char_start)


def _current(text: str, *drugs: str) -> list[str]:
    cur, _p, _f = _extract_medications(_ents(text, *drugs), type("D", (), {"text": text})(), META)
    return sorted(ev.value.generic_name for ev in cur)


def test_weak_past_cue_does_not_remove_a_listed_drug():
    text = ("Medication: Lamotrigine 100mg b.d.\n\n"
            "He has tried higher doses of lamotrigine in the past but this caused tiredness.")
    assert _current(text, "Lamotrigine", "lamotrigine") == ["lamotrigine"]


def test_planned_start_is_not_current():
    text = ("Medication: Lamotrigine 100mg b.d.\nLevetiracetam to start\n\n"
            "I would be grateful if you could start Levetiracetam.")
    assert _current(text, "Lamotrigine", "Levetiracetam") == ["lamotrigine"]
    text = "Controlled on phenobarbitone 100mg. Please can you start lamotrigine 25mg once a day."
    assert _current(text, "phenobarbitone", "lamotrigine") == ["phenobarbital"]


def test_bare_mention_after_a_plan_talks_about_the_plan():
    text = ("She is now taking lamotrigine 150mg bd. If this is not successful I would suggest "
            "introducing zonisamide 25mg od. Zonisamide can cause weight loss.")
    assert _current(text, "lamotrigine", "zonisamide", "Zonisamide") == ["lamotrigine"]


def test_taper_and_switch_keep_both_drugs_current():
    text = ("Topiramate 150mg twice a day\nLamotrigine 25mg once a day\n"
            "He is in the process of switching from topiramate to lamotrigine. "
            "Please reduce the topiramate by 25mg every fortnight.")
    assert _current(text, "Topiramate", "Lamotrigine", "topiramate", "lamotrigine") == [
        "lamotrigine", "topiramate"]


def test_explicit_stop_after_last_current_mention_removes_drug():
    text = "Takes carbamazepine 400mg bd. Carbamazepine was stopped last month because of rash."
    assert _current(text, "carbamazepine", "Carbamazepine") == []
    text = "Switched from carbamazepine to lamotrigine in 2019."
    assert _current(text, "carbamazepine", "lamotrigine") == ["lamotrigine"]


def test_bare_mention_of_a_stopped_drug_does_not_bring_it_back():
    text = ("Prior medications:\n- Perampanel - discontinued due to mood side effects.\n"
            "Prior ASM effects reviewed; perampanel caused sedation.")
    assert _current(text, "Perampanel", "perampanel") == []
    text = "Perampanel was stopped in 2020. She restarted and is now taking perampanel 4 mg."
    assert _current(text, "Perampanel", "perampanel") == ["perampanel"]


def test_if_cluster_not_prescribed_is_not_current():
    """EA0001–160 style plan: do not list a hypothetical cluster drug as current."""
    text = "If she has a cluster, use nasal midazolam. Not prescribed yet."
    assert _current(text, "midazolam") == []
    text = ("In the first instance I would suggest increasing the eslicarbazepine. "
            "She can also use clobazam as required for seizure clusters.")
    assert "clobazam" not in _current(text, "eslicarbazepine", "clobazam")


def test_prescribed_cluster_rescue_the_patient_takes_stays_current():
    text = ("He is taking levetiracetam 1500mg bd as well as lamotrigine 200mg bd "
            "and clobazam for seizure clusters (he takes this infrequently).")
    assert _current(text, "levetiracetam", "lamotrigine", "clobazam") == [
        "clobazam", "lamotrigine", "levetiracetam"]


def test_may_be_considered_is_not_current():
    text = "Takes lamotrigine 100mg bd. Zonisamide may be considered if seizures persist."
    assert _current(text, "lamotrigine", "Zonisamide") == ["lamotrigine"]


def test_one_entry_per_drug():
    text = "Carbamazepine 400mg bd. Continue carbamazepine. Carbamazepine level was normal."
    assert _current(text, "Carbamazepine", "carbamazepine") == ["carbamazepine"]


def test_abbreviations_whole_uppercase_tokens():
    text = "On LEV 1000 mg bid and LTG 200 mg bid; prior CBZ. Level of evidence low."
    hits = {(s.surface, s.canon) for s in surface_matches(text, canonicalize_drug_name)}
    assert ("LEV", "levetiracetam") in hits and ("LTG", "lamotrigine") in hits
    assert ("CBZ", "carbamazepine") in hits
    assert not any(s == "Level" for s, _ in hits)


def test_ambiguous_abbreviation_needs_a_dose():
    assert not surface_matches("Fees were 40 GBP per visit; PER protocol.", canonicalize_drug_name)
    hits = surface_matches("GBP 300 mg tds for pain.", canonicalize_drug_name)
    assert [(s.surface, s.canon) for s in hits] == [("GBP", "gabapentin")]


def test_misspellings_within_one_or_two_letters():
    assert canonicalize_drug_name(fuzzy_drug("volproate")) == "sodiumvalproate"
    assert fuzzy_drug("Pregablin") == "pregabalin"
    assert fuzzy_drug("levetiracvetam") == "levetiracetam"
    assert fuzzy_drug("carbmazapine") == "carbamazepine"


def test_misspelling_guards():
    if _has_words():
        assert fuzzy_drug("lyrical") is None  # Lyrica is one letter away
    assert fuzzy_drug("tablets") is None
    assert fuzzy_drug("Keppr") is None  # under 7 letters


def test_misspelled_drug_counts_as_current_but_not_for_a_relative():
    text = "Medication: Zonismaide 100mg bd. His mother takes lamotrigne for her epilepsy."
    assert _current(text) == ["zonisamide"]


def _has_words() -> bool:
    from rules.asm_surface import _english_words
    return bool(_english_words())
