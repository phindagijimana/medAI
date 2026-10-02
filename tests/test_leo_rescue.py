"""leo-v0.5: drug role (maintenance / rescue / acute) and the rescue field path (no GPU)."""

from __future__ import annotations

import pytest

from schema.claim import ReasonCode, ValidatorVerdict
from services.chain_pipeline import ACUTE_FIELD_PATH, RESCUE_FIELD_PATH
from services.med_context import drug_role
from test_leo_v04 import _run, ev


def _role(text: str, drug: str):
    i = text.index(drug)
    return drug_role(text, i, i + len(drug))


@pytest.mark.parametrize("text,drug,role", [
    ("Rescue medication: diazepam rectal gel 10 mg.", "diazepam", "rescue"),
    ("Midazolam buccal 10 mg PRN for seizures longer than 5 minutes.", "Midazolam", "rescue"),
    ("Valtoco (diazepam nasal) 10 mg for clusters.", "diazepam", "rescue"),
    ("Diazepam (Valtoco) nasal 10 mg.", "Diazepam", "rescue"),
    ("Lorazepam 2 mg IV PRN seizure lasting more than 5 minutes.", "Lorazepam", "rescue"),
    ("Clobazam 10 mg BID.", "Clobazam", "maintenance"),
    ("Keppra (levetiracetam) 500 mg BID.", "levetiracetam", "maintenance"),
    ("Increase lamotrigine as needed to 200 mg.", "lamotrigine", "maintenance"),
    ("lorazepam 1 mg PO nightly", "lorazepam", "maintenance"),
    # one-off doses stay acute even when the drug is also prescribed as needed
    ("Levetiracetam 1000 mg IV load PRN.", "Levetiracetam", "acute"),
    ("Lorazepam 4 mg IV was administered at 18:51.", "Lorazepam", "acute"),
])
def test_drug_role(text, drug, role):
    assert _role(text, drug)[0] == role


def test_cue_belongs_to_its_own_drug():
    note = "On clobazam 10 mg BID and midazolam buccal 10 mg PRN."
    assert _role(note, "clobazam")[0] == "maintenance"
    assert _role(note, "midazolam")[0] == "rescue"
    note = "Buccal midazolam 10 mg as needed for prolonged seizures, lamotrigine 100 mg BID."
    assert _role(note, "lamotrigine")[0] == "maintenance"
    note = "Plan: continue lamotrigine 100 mg BID. Rescue: diazepam rectal 10 mg."
    assert _role(note, "lamotrigine")[0] == "maintenance"


NOTE = ("Maintenance: lamotrigine 200 mg BID. "
        "Rescue: midazolam buccal 10 mg PRN for seizures longer than 5 minutes.")


def _spec():
    return {"document": {"doc_id": "x"}, "medication": {"current_asms": [
        ev({"generic_name": "lamotrigine"}, "lamotrigine 200 mg", NOTE),
        ev({"generic_name": "midazolam"}, "midazolam", NOTE)]}}


def _llm():
    return {"document": {"doc_id": "x"}, "medication": {"current_asms": [
        ev({"generic_name": "lamotrigine"}, "lamotrigine 200 mg"),
        ev({"generic_name": "midazolam"}, "midazolam")]}}


def test_rescue_drug_has_its_own_path_and_can_be_accepted():
    stats, claims = _run(NOTE, _spec(), _llm())
    resc = [c for c in claims if c.field_path == RESCUE_FIELD_PATH]
    cur = [c for c in claims if c.field_path == "medication.current_asms"]
    assert len(resc) == 1 and stats.n_rescue_routed == 1
    assert ReasonCode.RESCUE_ROLE in resc[0].reason_codes
    assert resc[0].validator_verdict == ValidatorVerdict.ACCEPT      # both sources agree
    assert [c.value for c in cur] and all("lamotrigine" in str(c.value) for c in cur)


def test_rescue_split_can_be_switched_off():
    stats, claims = _run(NOTE, _spec(), _llm(), rescue_role_split=False)
    assert stats.n_rescue_routed == 0
    assert not [c for c in claims if c.field_path == RESCUE_FIELD_PATH]
    assert len([c for c in claims if c.field_path == "medication.current_asms"]) == 2


def test_acute_wins_over_rescue_path():
    note = "Levetiracetam 1000 mg IV load PRN. Continue lamotrigine 200 mg BID."
    spec = {"document": {"doc_id": "x"}, "medication": {"current_asms": [
        ev({"generic_name": "levetiracetam"}, "Levetiracetam 1000 mg", note)]}}
    stats, claims = _run(note, spec, None)
    assert [c.field_path for c in claims] == [ACUTE_FIELD_PATH]
    assert stats.n_rescue_routed == 0
