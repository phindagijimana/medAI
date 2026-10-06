"""Third model reader (P1C) for remaining closed-vocab phenotype fields. No GPU."""

from __future__ import annotations

import json

import pytest

from services.chain_llm import CombinedReasoner
from services.flat_extract import FLAT_FIELD_PATHS
from services.pheno_extract import (
    PHENO_FIELD_PATHS, _EXAMPLES, build_pheno_prompt, parse_pheno, pheno_answer_model,
)
from test_leo_v04 import ev


def test_parse_pheno_keeps_quoted_vocab():
    raw = json.dumps({
        "awareness": {"value": "impaired", "quote": "impaired awareness"},
        "other_seizure_types": [{"value": "generalized_tonic_clonic", "quote": "rare GTCS"}],
        "etiology_category": {"value": "structural", "quote": "hippocampal sclerosis"},
        "status_epilepticus": {"value": False, "quote": "No status epilepticus"},
        "mri_normal": {"value": False, "quote": "MRI showed left hippocampal sclerosis"},
        "hippocampal_sclerosis": {"value": True, "quote": "left hippocampal sclerosis"},
        "focal_cortical_dysplasia": {"value": None, "quote": None},
        "mri_findings": [{"value": "hippocampal_sclerosis", "quote": "left hippocampal sclerosis"}],
        "lesion": {"lobe": "temporal", "side": "left", "quote": "left hippocampal sclerosis"},
        "prior_asms": [{"name": "carbamazepine", "quote": "stopped carbamazepine"}],
        "failed_asms": [{"name": "carbamazepine", "quote": "stopped carbamazepine"}],
        "non_drug_therapies": [{"type": "ketogenic_diet", "quote": "ketogenic diet"}],
        "seizures_captured": {"value": False, "quote": "EEG did not capture a seizure"},
        "localization": {"lobe": "temporal", "side": "left", "quote": "left temporal onset"},
    })
    p = parse_pheno(raw)
    assert p.parse_ok and p.n_fields_kept >= 10
    cs, mri, med, loc = (p.modules["clinical_seizure"], p.modules["mri"],
                         p.modules["medication"], p.modules["clinical_localization"])
    assert cs["awareness"]["value"] == "impaired"
    assert cs["status_epilepticus_history"]["value"] is False
    assert mri["hippocampal_sclerosis"]["value"] is True
    assert mri["lesion_lobe"]["value"] == "temporal"
    assert med["prior_asms"][0]["value"]["generic_name"] == "carbamazepine"
    assert med["non_drug_therapies"][0]["value"]["therapy_type"] == "ketogenic_diet"
    assert loc["primary_claim"]["value"]["source"] == "clinician_hypothesis"
    dropped = parse_pheno(json.dumps({
        "awareness": {"value": "maybe", "quote": "maybe"},
        "other_seizure_types": [],
        "etiology_category": {"value": "structural", "quote": None},
        "status_epilepticus": {"value": True, "quote": None},
        "mri_normal": {"value": None, "quote": None},
        "hippocampal_sclerosis": {"value": True, "quote": "HS"},
        "focal_cortical_dysplasia": {"value": None, "quote": None},
        "mri_findings": [],
        "lesion": {"lobe": None, "side": None, "quote": None},
        "prior_asms": [],
        "failed_asms": [],
        "non_drug_therapies": [],
        "seizures_captured": {"value": None, "quote": None},
        "localization": {"lobe": "temporal", "side": None, "quote": "temporal"},
    }))
    assert dropped.parse_ok
    assert "awareness" not in (dropped.modules.get("clinical_seizure") or {})
    assert "etiology_category" not in (dropped.modules.get("clinical_seizure") or {})
    assert "primary_claim" not in (dropped.modules.get("clinical_localization") or {})
    assert dropped.n_values_dropped >= 2


def test_parse_pheno_examples_are_verbatim():
    for note, ans in _EXAMPLES:
        p = parse_pheno(json.dumps(ans))
        assert p.parse_ok and p.n_fields_kept > 0
        if ans["awareness"].get("quote"):
            assert ans["awareness"]["quote"] in note
        if ans["hippocampal_sclerosis"].get("quote"):
            assert ans["hippocampal_sclerosis"]["quote"] in note


def test_pheno_answer_model_validates():
    M = pheno_answer_model()
    M.model_validate(json.loads(json.dumps(_EXAMPLES[0][1])))
    with pytest.raises(Exception):
        bad = dict(_EXAMPLES[0][1])
        bad["awareness"] = {"value": "not_a_class", "quote": "x"}
        M.model_validate(bad)


def test_pheno_field_paths_match_the_parser():
    p = parse_pheno(json.dumps(_EXAMPLES[0][1]))
    got = {f"{m}.{f}" for m, mod in p.modules.items() for f in mod}
    assert got <= PHENO_FIELD_PATHS
    assert "mri.hippocampal_sclerosis" in PHENO_FIELD_PATHS
    assert "clinical_seizure.epilepsy_type" not in PHENO_FIELD_PATHS


def test_prompt_asks_for_mri_and_etiology():
    p = build_pheno_prompt("short note")
    assert "hippocampal_sclerosis" in p
    assert "etiology_category" in p
    assert "Do not report plans" in p


def test_combined_reasoner_covers_pheno_fields():
    class Flat:
        last_ok = True
        last_covered_field_paths = FLAT_FIELD_PATHS
        info = type("I", (), {"model": "x", "prompt": "flat"})()

        def __call__(self, *a, **k):
            return {"clinical_seizure": {"epilepsy_type": ev("focal", "focal")}}

    class Ext:
        last_ok = True
        last_covered_field_paths = frozenset()
        info = type("I", (), {"model": "x", "prompt": "ext"})()

        def __call__(self, *a, **k):
            return {}

    class Pheno:
        last_ok = True
        last_covered_field_paths = PHENO_FIELD_PATHS
        info = type("I", (), {"model": "x", "prompt": "pheno"})()

        def __call__(self, *a, **k):
            return {"mri": {"hippocampal_sclerosis": ev(True, "HS")}}

    c = CombinedReasoner(Flat(), Ext(), Pheno())
    out = c("note", "d", "2024-01-01")
    assert out["mri"]["hippocampal_sclerosis"]["value"] is True
    assert "mri.hippocampal_sclerosis" in c.last_covered_field_paths
    assert "clinical_seizure.epilepsy_type" in c.last_covered_field_paths
