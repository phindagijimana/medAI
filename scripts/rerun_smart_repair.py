#!/usr/bin/env python3
"""Re-parse all Med42 manifests with the smart-repair chain.

Reads every manifest under data/run_manifests/, runs the raw_response
through `services.smart_repair.try_smart_repair`, and reports:

  - raw_validity (as originally logged)
  - smart_repair_validity (new)
  - per-module + per-arm breakdown
  - a small sample of repair patterns

Writes an augmented aggregate summary to
`eval/results/smart_repair_summary.json`.

Runs entirely on CPU; no GPU / Med42 needed.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema import (
    ClinicalSeizureModule,
    DocumentMetadata,
    DocumentType,
    EegModule,
    MedicationModule,
    MriModule,
)
from services.smart_repair import try_smart_repair

REPO = Path(__file__).resolve().parent.parent
MANIFESTS_ROOT = REPO / "data" / "run_manifests"
OUT = REPO / "eval" / "results" / "smart_repair_summary.json"

MODULE_CLASSES = {
    "clinical_seizure": ClinicalSeizureModule,
    "medication": MedicationModule,
    "mri": MriModule,
    "eeg": EegModule,
}


def _has_meaningful_content(m) -> bool:
    """True if the module has ANY field with a non-null value or a non-empty list.
    A degenerate "all not_documented" repair returns False."""
    from pydantic import BaseModel
    d = m.model_dump(mode="json") if isinstance(m, BaseModel) else m
    for k, v in d.items():
        # list field (findings, current_asms, etc.)
        if isinstance(v, list) and len(v) > 0:
            return True
        # single Evidence dict
        if isinstance(v, dict) and v.get("value") is not None:
            return True
    return False


def _doc_from_manifest(m: dict) -> DocumentMetadata:
    """Reconstruct a DocumentMetadata from a manifest's source_* fields."""
    doc_id = m.get("source_doc_id", "unknown")
    dtype = m.get("source_doc_type", "progress_note")
    try:
        doc_type = DocumentType(dtype)
    except Exception:
        doc_type = DocumentType.PROGRESS_NOTE
    return DocumentMetadata(
        doc_id=doc_id, doc_type=doc_type,
        doc_date=date(2024, 1, 1), patient_id=doc_id,
        icd10cm_codes=[], snomed_ct_codes=[],
    )


def main() -> int:
    stats: dict[str, dict] = defaultdict(lambda: {
        "n": 0, "raw_valid": 0, "smart_valid": 0,
        # smart_valid_with_content: pydantic-valid AND at least one non-null value
        "smart_valid_with_content": 0,
        "raw_tokens_sum": 0, "raw_tokens_count": 0,
        "error_kinds": defaultdict(int),
    })
    sample_repairs: list[dict] = []

    for f in sorted(MANIFESTS_ROOT.rglob("*.json")):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        pid = m.get("prompt_id", "")
        parts = pid.split(".")
        if len(parts) != 3:
            continue
        module_name, arm, version = parts
        if module_name not in MODULE_CLASSES:
            continue

        key = f"{module_name}/{arm}/{version}"
        s = stats[key]
        s["n"] += 1
        if m.get("raw_valid"):
            s["raw_valid"] += 1
        if m.get("raw_response_tokens"):
            s["raw_tokens_sum"] += m["raw_response_tokens"]
            s["raw_tokens_count"] += 1

        # Smart-repair pass
        raw = m.get("raw_response") or ""
        module_cls = MODULE_CLASSES[module_name]
        doc = _doc_from_manifest(m)
        validated, parsed, err = try_smart_repair(raw, module_cls, doc)
        if validated is not None:
            s["smart_valid"] += 1
            # Content check: did the repair recover any actual field values?
            has_content = _has_meaningful_content(validated)
            if has_content:
                s["smart_valid_with_content"] += 1
            if len(sample_repairs) < 5 and not m.get("raw_valid") and has_content:
                sample_repairs.append({
                    "doc_id": m["source_doc_id"], "prompt_id": pid,
                    "raw_first_200": raw[:200],
                    "wrapped_field_sample": {
                        k: v for k, v in list(validated.model_dump(mode="json").items())[:2]
                    },
                })
        else:
            # Extract the top error kind
            kind = "unknown"
            if err:
                first_line = err.splitlines()[0] if err else ""
                kind = first_line[:60]
            s["error_kinds"][kind] += 1

    # Print table + save
    print(f"{'arm':<40}  {'n':>4}  {'raw%':>6}  {'smart%':>7}  {'w/content%':>10}  {'avg_tok':>8}")
    print("-" * 92)
    for key in sorted(stats):
        s = stats[key]
        raw_pct = 100 * s["raw_valid"] / s["n"] if s["n"] else 0
        smart_pct = 100 * s["smart_valid"] / s["n"] if s["n"] else 0
        content_pct = 100 * s["smart_valid_with_content"] / s["n"] if s["n"] else 0
        avg_tok = s["raw_tokens_sum"] / s["raw_tokens_count"] if s["raw_tokens_count"] else 0
        print(f"{key:<40}  {s['n']:>4}  {raw_pct:>5.1f}%  {smart_pct:>6.1f}%  {content_pct:>9.1f}%  {avg_tok:>8.0f}")

    # Serializable output
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "per_arm": {k: {kk: (dict(vv) if isinstance(vv, defaultdict) else vv)
                        for kk, vv in v.items()} for k, v in stats.items()},
        "sample_repairs": sample_repairs,
    }, indent=2), encoding="utf-8")
    print(f"\nsaved → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
