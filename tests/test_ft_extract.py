"""Tuned-adapter inference contract (no GPU)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from services.ft_extract import (
    FT_PROMPT_TEMPLATE, build_ft_prompt, is_degenerate, populated_fields, split_phenotype,
)

REPO = Path(__file__).resolve().parents[1]


def test_prompt_matches_training_script_byte_for_byte():
    src = (REPO / "scripts" / "finetune_lora_epi.py").read_text(encoding="utf-8")
    m = re.search(r"PROMPT_TEMPLATE = \((.*?)\n\)\n", src, flags=re.S)
    assert m, "PROMPT_TEMPLATE not found in finetune_lora_epi.py"
    trained = eval("(" + m.group(1) + ")")  # a parenthesised string-literal concatenation
    assert trained == FT_PROMPT_TEMPLATE


def test_patient_id_line_is_prepended_like_training():
    p = build_ft_prompt("note body", "EA0161")
    assert 'PATIENT_ID: EA0161\n\nnote body' in p and p.endswith("Phenotype JSON:\n")
    assert "PATIENT_ID" not in build_ft_prompt("note body")


def _ev(value, quote):
    return {"value": value, "certainty": "definite", "temporal_status": "current",
            "evidence_text": quote, "source_doc_id": "EA1", "source_doc_type": "progress_note",
            "source_date": "2024-01-01"}


def test_split_phenotype_validates_each_module_independently():
    full = {
        "document": {"doc_id": "EA1"},
        "medication": {"current_asms": [_ev(
            {"generic_name": "lamotrigine", "dose_text": "50 mg", "status": "current"}, "lamotrigine 50 mg")]},
        "clinical_seizure": {"epilepsy_type": _ev("not-a-real-enum-value-%%", "x")},
    }
    mods = split_phenotype("```json\n" + json.dumps(full) + "\n```", doc_id="EA1")
    assert "medication" in mods
    assert populated_fields(mods["medication"]) == 1


def test_schema_echo_is_degenerate():
    echo = '{"$defs": {"Certainty": {"enum": ["definite"]}}, "properties": {}, "title": "X"}'
    assert is_degenerate(split_phenotype(echo, doc_id="EA1"))
    assert split_phenotype("no json here", doc_id="EA1") == {}


def test_one_bad_enum_does_not_discard_the_module():
    from schema import ClinicalSeizureModule
    from services.ft_extract import validate_with_salvage
    good = _ev("generalized", "generalized epilepsy")
    sub = {"epilepsy_type": good, "etiology_category": _ev("undefined", "?")}
    mod, dropped = validate_with_salvage(ClinicalSeizureModule, sub, "EA1")
    assert mod is not None and "etiology_category" in dropped and "epilepsy_type" not in dropped
    d = mod.model_dump(mode="json")
    assert d["epilepsy_type"]["value"] == "generalized"
    assert d["etiology_category"]["value"] is None
