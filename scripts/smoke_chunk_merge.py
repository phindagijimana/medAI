#!/usr/bin/env python3
"""Smoke test for services/chunker.py + services/merge.py + extract_module_long.

Uses a scripted mock backend that emits a different pre-canned Evidence-wrapped
MedicationModule per chunk. Confirms:
    (a) text chunker + merger produces one validated module
    (b) row chunker + merger applies latest-visit-wins across 3 synthetic visits
    (c) merge report surfaces conflicts when scalar Evidence disagree
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema import (
    Certainty, DocumentMetadata, DocumentType, Evidence,
    MedicationModule, TemporalStatus,
)
from schema.enums import DrugResistanceStatus, MedicationStatus
from schema.ontology import Medication
from services.chunker import Chunk, chunk_rows, chunk_text
from services.extract import extract_module_long
from services.prompt_registry import get as get_prompt
from services.run_manifest import DecodingConfig


class ScriptedBackend:
    """A ModelBackend that returns a pre-canned response per invocation."""
    model_name = "scripted-mock"
    model_cache_dir = "/dev/null"

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.i = 0

    def generate(self, prompt: str, decoding: DecodingConfig) -> tuple[str, int | None]:
        r = self.responses[self.i % len(self.responses)]
        self.i += 1
        return r, len(r) // 4


def _module_json(**kwargs) -> str:
    """Build a valid MedicationModule JSON string from a small kwargs shape."""
    src = {
        "source_doc_id": "SMOKE",
        "source_doc_type": DocumentType.PROGRESS_NOTE.value,
        "source_date": "2024-01-01",
    }

    def ev(value, txt, cert="definite"):
        return {
            "value": value, "certainty": cert, "temporal_status": "current",
            "evidence_text": txt, **src,
        }

    def nd():
        return {
            "value": None, "certainty": "not_documented",
            "temporal_status": "unspecified", "evidence_text": None, **src,
        }

    obj = {
        "current_asms": [
            {"value": {"generic_name": name, "status": "current"},
             "certainty": "definite", "temporal_status": "current",
             "evidence_text": txt, **src}
            for name, txt in kwargs.get("meds", [])
        ],
        "prior_asms": [], "failed_asms": [],
        "adverse_effects_text": nd(),
        "drug_resistance_status": (
            ev(kwargs["dr"], kwargs["dr_txt"], kwargs.get("dr_cert", "definite"))
            if "dr" in kwargs else nd()
        ),
        "surgery_history": [], "non_drug_therapies": [],
    }
    return json.dumps(obj)


def scenario_text():
    print("--- (a) Free-text chunk → merge ---")
    note = (
        "HPI:\nOn lamotrigine 25mg BID; monthly focal seizures.\n\n"
        "Assessment:\nDrug-resistant focal epilepsy.\n\n"
        "Plan:\nAdd levetiracetam.\n"
    )
    chunks = chunk_text(note, max_chars=80, overlap_chars=10)
    print(f"chunks: {len(chunks)}")

    # Each chunk gets its own response — respond to whichever chunk the
    # extractor sees first (order is deterministic).
    responses = []
    for c in chunks:
        low = c.text.lower()
        if "drug-resistant" in low:
            responses.append(_module_json(
                meds=[("lamotrigine", "on lamotrigine 25mg BID")],
                dr="drug_resistant", dr_txt="Drug-resistant focal epilepsy",
                dr_cert="definite",
            ))
        elif "levetiracetam" in low:
            responses.append(_module_json(
                meds=[("levetiracetam", "Add levetiracetam")]
            ))
        else:
            responses.append(_module_json(
                meds=[("lamotrigine", "On lamotrigine 25mg BID")]
            ))

    doc = DocumentMetadata(
        doc_id="SMOKE", doc_type=DocumentType.PROGRESS_NOTE,
        doc_date=date(2024, 1, 1), patient_id="P",
    )
    prompt = get_prompt("medication.M2.v1")
    backend = ScriptedBackend(responses)
    result = extract_module_long(
        module_cls=MedicationModule,
        prompt=prompt,
        chunks=chunks,
        source_doc_meta=doc,
        model_backend=backend,
        schema_version="v0.2.1",
        inject_schema=False,
    )
    assert result.module is not None, "merged module failed to validate"
    print(f"  merged current_asms: {[e.value.generic_name for e in result.module.current_asms]}")
    print(f"  drug_resistance: {result.module.drug_resistance_status.value}")
    print(f"  n manifests: {len(result.manifests)}")
    print(f"  n chunks contributed: {result.merge_report.n_chunks_contributed}")
    return result


def scenario_rows():
    print("\n--- (b) Longitudinal row-based chunk → merge ---")
    rows = [
        {"visit_date": "2023-03-01", "visit_id": "v1",
         "text": "Started lamotrigine 25mg BID."},
        {"visit_date": "2023-09-15", "visit_id": "v2",
         "text": "Breakthrough seizure. LTG increased to 75mg BID; added levetiracetam 500mg BID."},
        {"visit_date": "2024-06-01", "visit_id": "v3",
         "text": "Confirmed drug-resistant per ILAE. LTG 75mg BID, LEV 1000mg BID."},
    ]
    chunks = chunk_rows(rows)
    print(f"chunks: {len(chunks)} (should be 3 — one per visit)")

    responses = [
        _module_json(meds=[("lamotrigine", "Started lamotrigine 25mg BID.")]),
        _module_json(meds=[
            ("lamotrigine", "LTG increased to 75mg BID"),
            ("levetiracetam", "added levetiracetam 500mg BID"),
        ]),
        _module_json(
            meds=[
                ("lamotrigine", "LTG 75mg BID"),
                ("levetiracetam", "LEV 1000mg BID"),
            ],
            dr="drug_resistant", dr_txt="Confirmed drug-resistant per ILAE",
            dr_cert="definite",
        ),
    ]
    doc = DocumentMetadata(
        doc_id="SMOKE_LONG", doc_type=DocumentType.PROGRESS_NOTE,
        doc_date=date(2024, 6, 1), patient_id="P",
    )
    prompt = get_prompt("medication.M2.v1")
    backend = ScriptedBackend(responses)
    result = extract_module_long(
        module_cls=MedicationModule,
        prompt=prompt,
        chunks=chunks,
        source_doc_meta=doc,
        model_backend=backend,
        schema_version="v0.2.1",
        inject_schema=False,
    )
    assert result.module is not None
    # Latest visit should be the source of the current-state dose text.
    asm_names = [e.value.generic_name for e in result.module.current_asms]
    ltg = next(e for e in result.module.current_asms if e.value.generic_name == "lamotrigine")
    print(f"  merged current_asms: {asm_names}")
    print(f"  lamotrigine evidence_text (should be v3 quote): {ltg.evidence_text!r}")
    print(f"  drug_resistance: {result.module.drug_resistance_status.value} "
          f"(evidence: {result.module.drug_resistance_status.evidence_text!r})")
    print(f"  dedup counts: {result.merge_report.list_field_dedup_counts}")
    assert "75mg" in ltg.evidence_text, "latest-visit dose should have won"
    return result


def scenario_conflict():
    print("\n--- (c) Free-text scalar conflict → surfaced in merge report ---")
    doc = DocumentMetadata(
        doc_id="SMOKE_CONFL", doc_type=DocumentType.PROGRESS_NOTE,
        doc_date=date(2024, 1, 1), patient_id="P",
    )
    # Chunk 0 (HPI): drug-responsive, DEFINITE
    # Chunk 1 (Plan): drug-resistant, PROBABLE
    r0 = _module_json(dr="drug_responsive", dr_txt="seizure-free 6 mo", dr_cert="definite")
    r1 = _module_json(dr="drug_resistant", dr_txt="meets ILAE criteria", dr_cert="probable")
    chunks = [
        Chunk(text="hpi text", chunk_index=0, section_hint="hpi"),
        Chunk(text="assessment text", chunk_index=1, section_hint="assessment"),
    ]
    prompt = get_prompt("medication.M2.v1")
    backend = ScriptedBackend([r0, r1])
    result = extract_module_long(
        module_cls=MedicationModule, prompt=prompt, chunks=chunks,
        source_doc_meta=doc, model_backend=backend,
        schema_version="v0.2.1", inject_schema=False,
    )
    print(f"  winner: {result.module.drug_resistance_status.value} "
          f"(cert={result.module.drug_resistance_status.certainty.value})")
    print(f"  conflicts: {result.merge_report.field_conflicts}")
    assert "drug_resistance_status" in result.merge_report.field_conflicts, \
        "expected drug_resistance conflict to surface"


def main():
    scenario_text()
    scenario_rows()
    scenario_conflict()
    print("\nOK — chunk-and-merge path validates end-to-end.")


if __name__ == "__main__":
    main()
