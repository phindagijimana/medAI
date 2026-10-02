"""Flat prompt family for the base model (no GPU)."""

from __future__ import annotations

import json

from services.flat_extract import build_flat_prompt, parse_flat
from services.chain_llm import flatten

GOOD = json.dumps({
    "epilepsy_type": {"value": "Focal", "quote": "focal epilepsy"},
    "predominant_seizure_type": {"value": "focal-impaired-awareness", "quote": "complex partial seizures"},
    "age_at_onset_years": {"value": "12", "quote": "since age 12"},
    "seizure_frequency": {"count_min": 2, "count_max": None, "period": "Month", "seizure_free": False,
                          "quote": "2 per month"},
    "current_asms": [{"name": "Lamotrigine", "dose": "100 mg", "quote": "lamotrigine 100 mg"},
                     {"name": "", "dose": None, "quote": "x"}],
})


def test_prompt_arms_differ_only_by_examples():
    l0, l1 = build_flat_prompt("NOTE", "L0"), build_flat_prompt("NOTE", "L1")
    assert l0.endswith('"""\nNOTE\n"""\nJSON:\n') or 'NOTE' in l0
    assert "Example note" not in l0 and l1.count("Example note") == 2
    assert l1.endswith("JSON:\n")


def test_prompt_never_contains_fs_letter_text():
    p = build_flat_prompt("x", "L1")
    assert "EA0" not in p and "Fonferko" not in p


def test_parse_normalises_and_keeps_only_quoted_in_vocab_values():
    r = parse_flat("```json\n" + GOOD + "\n```")
    cs, med = r.modules["clinical_seizure"], r.modules["medication"]
    assert cs["epilepsy_type"]["value"] == "focal"
    assert cs["predominant_seizure_type"]["value"] == "focal_impaired_awareness"
    assert cs["age_at_onset_years"]["value"] == 12.0
    sf = cs["seizure_frequency"]["value"]
    assert sf["period"] == "month" and sf["count_min"] == 2 and sf["count_max"] == 2
    assert [e["value"]["generic_name"] for e in med["current_asms"]] == ["lamotrigine"]
    assert r.n_values_dropped == 1   # the nameless drug


def test_out_of_vocab_and_unquoted_values_are_dropped():
    bad = json.dumps({"epilepsy_type": {"value": "partial", "quote": "partial"},
                      "predominant_seizure_type": {"value": "generalized_tonic_clonic", "quote": None}})
    r = parse_flat(bad)
    assert r.modules == {} and r.n_values_dropped == 2


def test_non_json_is_reported_not_raised():
    r = parse_flat("I am sorry, I cannot help")
    assert not r.parse_ok and r.modules == {}


def test_flat_output_feeds_the_fuser():
    items = flatten(parse_flat(GOOD).modules)
    assert {i.field_path for i in items} >= {"clinical_seizure.epilepsy_type", "medication.current_asms"}


def test_constrained_arms_share_prompt_and_schema_parses_through_parse_flat():
    from services.flat_extract import build_flat_prompt, flat_answer_model, parse_flat
    note = "Age 8 at onset. Takes lamotrigine 100 mg twice daily."
    assert build_flat_prompt(note, "L1C") == build_flat_prompt(note, "L1")
    ans = flat_answer_model().model_validate({
        "epilepsy_type": {"value": "focal", "quote": "focal"},
        "predominant_seizure_type": {},
        "age_at_onset_years": {"value": 8, "quote": "Age 8 at onset"},
        "seizure_frequency": {},
        "current_asms": [{"name": "lamotrigine", "dose": "100 mg", "quote": "lamotrigine 100 mg twice daily"}],
    })
    pheno = parse_flat(ans.model_dump_json())
    assert pheno.parse_ok and pheno.n_fields_kept == 3 and pheno.n_values_dropped == 0
    assert len(flatten(pheno.modules)) >= 3
