""""unknown" epilepsy type: one definition for the model prompt v2 and for EpExtra."""

from __future__ import annotations

import json

from rules.fields.epilepsy_type import _stated_epilepsy
from schema.enums import UNKNOWN_EPILEPSY_TYPE_DEFINITION
from services.chain_llm import FieldItem, fuse
from services.flat_extract import build_flat_prompt, flat_answer_model, parse_flat

ANSWER = json.dumps({
    "epilepsy_type": {"value": "unknown", "quote": "epilepsy"},
    "predominant_seizure_type": {"value": None, "quote": None},
    "age_at_onset_years": {"value": None, "quote": None},
    "seizure_frequency": {"count_min": None, "count_max": None, "period": None,
                          "seizure_free": None, "quote": None},
    "current_asms": [],
})


def test_v1_prompt_has_no_unknown_and_v2_states_the_shared_definition():
    v1 = build_flat_prompt("NOTE", "L1", version="v1")
    v2 = build_flat_prompt("NOTE", "L1", version="v2")
    assert "'unknown'" not in v1 and UNKNOWN_EPILEPSY_TYPE_DEFINITION not in v1
    assert "'unknown'" in v2 and UNKNOWN_EPILEPSY_TYPE_DEFINITION in v2
    assert build_flat_prompt("NOTE", "L1C", version="v2") == v2


def test_parser_follows_the_version_the_answer_was_made_under():
    assert "clinical_seizure" not in parse_flat(ANSWER, "v1").modules
    assert parse_flat(ANSWER, "v1").n_values_dropped == 1
    assert parse_flat(ANSWER, "v2").modules["clinical_seizure"]["epilepsy_type"]["value"] == "unknown"


def test_constrained_schema_per_version():
    v1, v2 = flat_answer_model("v1"), flat_answer_model("v2")
    ok = {"epilepsy_type": {"value": "unknown", "quote": "epilepsy"},
          "predominant_seizure_type": {}, "age_at_onset_years": {}, "seizure_frequency": {},
          "current_asms": []}
    assert v2.model_validate(ok).epilepsy_type.value == "unknown"
    try:
        v1.model_validate(ok)
    except Exception:
        pass
    else:
        raise AssertionError("v1 schema must not allow 'unknown'")


def _item(path, value, module="clinical_seizure"):
    return FieldItem(path, module, {"value": value, "evidence_text": "epilepsy"}, False)


def test_fusion_keeps_unknown_epilepsy_type_but_still_drops_other_unknowns():
    et, st = "clinical_seizure.epilepsy_type", "clinical_seizure.predominant_seizure_type"
    f = fuse([_item(et, "unknown")], [_item(et, "unknown")])
    assert [s.status for s in f.specialist] == ["agree"]
    f = fuse([_item(et, "focal")], [_item(et, "unknown")])
    assert [s.status for s in f.specialist] == ["disagree"]
    f = fuse([_item(st, "focal_aware")], [_item(st, "unknown")])
    assert [s.status for s in f.specialist] == ["specialist_only"]


def test_epextra_stated_epilepsy_skips_services_relatives_and_doubt():
    assert _stated_epilepsy("Diagnosis: Epilepsy\nMedication: lamotrigine").group(0) == "Epilepsy"
    assert _stated_epilepsy("She will see the epilepsy nurses in clinic.") is None
    assert _stated_epilepsy("His mother has epilepsy.") is None
    assert _stated_epilepsy("Diagnosis: ?epilepsy, possibly syncope") is None
    assert _stated_epilepsy("There is no evidence of epilepsy.") is None
