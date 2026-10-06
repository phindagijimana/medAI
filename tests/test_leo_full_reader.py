"""Fourth model reader (F1C) for leftover schema fields. No GPU."""

from __future__ import annotations

import json

import pytest

from services.full_extract import (
    FULL_FIELD_PATHS, _EXAMPLES, build_full_prompt, full_answer_model, parse_full,
)
from services.pheno_extract import PHENO_FIELD_PATHS


def test_parse_full_keeps_quoted_fields():
    p = parse_full(json.dumps(_EXAMPLES[0][1]))
    assert p.parse_ok and p.n_fields_kept >= 8
    cs, med, mri, eeg, integ = (p.modules["clinical_seizure"], p.modules["medication"],
                                p.modules["mri"], p.modules["eeg"], p.modules["integrated"])
    assert "epigastric" in cs["semiology_text"]["value"]
    assert cs["etiology_specifics"]["value"]["causative_gene"] == "SCN1A"
    assert med["drug_resistance_status"]["value"] == "drug_resistant"
    assert mri["field_strength_tesla"]["value"] == 3.0
    assert mri["mri_negative_for_epilepsy"]["value"] is True
    assert eeg["seizures_captured_count"]["value"] == 2
    assert integ["concordance"]["value"] == "discordant"
    got = {f"{m}.{f}" for m, mod in p.modules.items() for f in mod}
    assert got <= FULL_FIELD_PATHS
    assert got.isdisjoint(PHENO_FIELD_PATHS)


def test_parse_full_drops_unquoted_and_requires_both_sides_for_alt():
    dropped = parse_full(json.dumps({
        "semiology": {"value": "automatisms", "quote": None},
        "etiology_details": {"value": None, "quote": None},
        "adverse_effects": {"value": None, "quote": None},
        "drug_resistance": {"value": "not_a_status", "quote": "x"},
        "other_frequencies": [],
        "seizures_captured_count": {"value": None, "quote": None},
        "mri_negative": {"value": None, "quote": None},
        "field_strength_tesla": {"value": 1.2, "quote": "1.2T"},
        "etiology_specifics": {"gene": None, "variant": None, "antibody": None,
                               "pathogen": None, "metabolic": None, "tumor": None, "quote": None},
        "alternative_localization": [{"lobe": "frontal", "side": None, "quote": "frontal"}],
        "concordance": {"value": None, "quote": None},
        "concordance_notes": {"value": None, "quote": None},
    }))
    assert dropped.parse_ok
    assert "semiology_text" not in (dropped.modules.get("clinical_seizure") or {})
    assert "alternative_claims" not in (dropped.modules.get("clinical_localization") or {})
    assert dropped.n_values_dropped >= 2


def test_parse_full_examples_are_verbatim():
    for note, ans in _EXAMPLES:
        p = parse_full(json.dumps(ans))
        assert p.parse_ok
        if ans["semiology"].get("quote"):
            assert ans["semiology"]["quote"] in note


def test_full_answer_model_validates():
    M = full_answer_model()
    M.model_validate(_EXAMPLES[0][1])
    with pytest.raises(Exception):
        bad = dict(_EXAMPLES[0][1])
        bad["drug_resistance"] = {"value": "maybe", "quote": "x"}
        M.model_validate(bad)


def test_full_prompt_covers_leftovers():
    p = build_full_prompt("short note")
    assert "semiology" in p and "concordance" in p and "etiology_specifics" in p
    assert "Do not report plans" in p
