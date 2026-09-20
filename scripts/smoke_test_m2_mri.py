#!/usr/bin/env python3
"""Smoke test for the M0/M1/M2 extraction pipeline on the MRI module.

Uses a MockBackend that returns hand-crafted JSON responses so we exercise
the full validation/repair path without needing Med42 loaded on GPU.

Runs three scenarios that each stress a different part of the pipeline:
  1. clean JSON — raw_valid=True, no repair
  2. code-fence-wrapped JSON — raw_valid=False, repaired via strip_code_fence
  3. prose preamble + JSON — raw_valid=False, repaired via regex_json_extraction

Also runs one negative scenario: unparseable garbage → final_valid=False.

Every run's manifest is written under data/run_manifests/<date>/ so the tree
looks like what a real eval sweep would produce.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

# Make repo root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema import DocumentMetadata, DocumentType, MriModule, SCHEMA_VERSION
from services.extract import (
    DecodingConfig,
    ExtractionResult,
    ModelBackend,
    evidence_boilerplate,
    extract_module,
)
from services.prompt_registry import MRI_M0_V1, MRI_M1_V1, MRI_M2_V1


# ---------------------------------------------------------------------------
# Build the JSON payload the model *should* emit for a right-HS MRI report,
# used as canned response for the mock backend.
# ---------------------------------------------------------------------------

TEST_DOC = DocumentMetadata(
    doc_id="SYN-MRI-0001",
    doc_type=DocumentType.MRI_REPORT,
    doc_date=date(2025, 6, 14),
    patient_id="SYN-P-0001",
)

SOURCE_TEXT = (
    "MRI BRAIN 3T without contrast.\n"
    "TECHNIQUE: standard epilepsy protocol.\n"
    "FINDINGS: There is marked T2/FLAIR hyperintensity and volume loss of the "
    "right hippocampus consistent with right hippocampal sclerosis. No focal "
    "cortical dysplasia is identified elsewhere. Ventricles are otherwise "
    "unremarkable. No other epilepsy-relevant lesion.\n"
    "IMPRESSION: Right hippocampal sclerosis."
)


def _ev(value, evidence_text, certainty="definite", temporal="current"):
    return {
        "value": value,
        "certainty": certainty,
        "temporal_status": temporal,
        "evidence_text": evidence_text,
        **evidence_boilerplate(TEST_DOC),
    }


CANONICAL_JSON = {
    "overall_normal": _ev(False, "right hippocampal sclerosis"),
    "findings": [
        _ev("hippocampal_sclerosis", "right hippocampal sclerosis"),
    ],
    "lesion_lobe": _ev("temporal", "right hippocampus"),
    "lesion_laterality": _ev("right", "right hippocampus"),
    "hippocampal_sclerosis": _ev(True, "right hippocampal sclerosis"),
    "focal_cortical_dysplasia": _ev(
        False, "No focal cortical dysplasia is identified elsewhere", certainty="negated"
    ),
    "mri_negative_for_epilepsy": _ev(False, "right hippocampal sclerosis"),
    "field_strength_tesla": _ev(3.0, "MRI BRAIN 3T"),
}


# ---------------------------------------------------------------------------
# Mock backend — deterministic canned response chosen per prompt content.
# ---------------------------------------------------------------------------


class MockBackend:
    model_name = "mock/MockMed42-Test"
    model_cache_dir = "/tmp/mock"

    def __init__(self, mode: str):
        self.mode = mode

    def generate(self, prompt: str, decoding: DecodingConfig) -> tuple[str, int | None]:
        canonical = json.dumps(CANONICAL_JSON)
        if self.mode == "clean":
            return canonical, len(canonical) // 4
        if self.mode == "code_fence":
            return f"```json\n{json.dumps(CANONICAL_JSON, indent=2)}\n```", None
        if self.mode == "prose_wrap":
            return (
                "Here is the extracted MRI phenotype for this report:\n\n"
                f"{json.dumps(CANONICAL_JSON, indent=2)}\n\n"
                "Please review with a qualified clinician."
            ), None
        if self.mode == "garbage":
            return "I cannot extract this data. There is no MRI report here.", None
        if self.mode == "invalid_enum":
            bad = dict(CANONICAL_JSON)
            bad_lobe = dict(bad["lesion_lobe"])
            bad_lobe["value"] = "hippocampus"  # not a valid LobarLocalization enum
            bad["lesion_lobe"] = bad_lobe
            return json.dumps(bad), None
        raise ValueError(f"unknown mock mode {self.mode!r}")


# ---------------------------------------------------------------------------
# Run each scenario across M0/M1/M2 and report
# ---------------------------------------------------------------------------


def _run(scenario: str, mode: str, prompt) -> ExtractionResult:
    result = extract_module(
        module_cls=MriModule,
        prompt=prompt,
        source_text=SOURCE_TEXT,
        source_doc_meta=TEST_DOC,
        model_backend=MockBackend(mode),
        schema_version=SCHEMA_VERSION,
    )
    result.manifest.write()
    m = result.manifest
    print(
        f"  {scenario:<20}  arm={m.arm:<3}  "
        f"raw_valid={str(m.raw_valid):<5}  "
        f"final_valid={str(m.final_valid):<5}  "
        f"repair={m.repair_method or '-':<25}  "
        f"attempts={m.repair_attempts}  "
        f"dur={m.duration_s:.3f}s"
    )
    return result


def main() -> int:
    print(f"Schema version: {SCHEMA_VERSION}")
    print(f"Prompts loaded: {[p.prompt_id for p in (MRI_M0_V1, MRI_M1_V1, MRI_M2_V1)]}\n")

    prompt_by_arm = {"M0": MRI_M0_V1, "M1": MRI_M1_V1, "M2": MRI_M2_V1}

    print("Positive scenarios (should end final_valid=True):")
    for arm in ("M0", "M1", "M2"):
        for scenario, mode in (
            ("clean-JSON",   "clean"),
            ("code-fence",   "code_fence"),
            ("prose-wrap",   "prose_wrap"),
        ):
            r = _run(scenario, mode, prompt_by_arm[arm])
            assert r.manifest.final_valid, f"expected valid for {scenario} / {arm}"

    print("\nNegative scenarios (should end final_valid=False):")
    for scenario, mode in (("garbage", "garbage"), ("invalid-enum", "invalid_enum")):
        r = _run(scenario, mode, MRI_M2_V1)
        assert not r.manifest.final_valid, f"expected invalid for {scenario}"

    # Distinguish M2 raw-valid-with-schema-injected from M0 raw-valid: they
    # both handle clean JSON but M2's prompt is much longer.
    r_m0 = _run("clean/M0-check", "clean", MRI_M0_V1)
    r_m2 = _run("clean/M2-check", "clean", MRI_M2_V1)
    prompt_m2 = MRI_M2_V1.render(SOURCE_TEXT, module_schema=MriModule.model_json_schema())
    prompt_m0 = MRI_M0_V1.render(SOURCE_TEXT, module_schema=None)
    print(f"\nPrompt sizes — M0: {len(prompt_m0)} chars  M2: {len(prompt_m2)} chars")
    assert len(prompt_m2) > len(prompt_m0), "M2 prompt should be longer than M0"

    # Verify manifest fields we care about
    m = r_m2.manifest
    assert m.schema_version == SCHEMA_VERSION
    assert m.prompt_id == "mri.M2.v1"
    assert m.fewshot_ids == ["mri.fewshot.synthetic-01.v1"]
    assert m.arm == "M2"
    assert m.source_doc_id == TEST_DOC.doc_id
    assert m.parsed_value is not None
    assert m.parsed_value["hippocampal_sclerosis"]["value"] is True

    print("\nALL SMOKE CHECKS PASSED")
    manifests_written = list((Path(__file__).resolve().parent.parent / "data" / "run_manifests").rglob("*.json"))
    print(f"Manifests written: {len(manifests_written)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
