#!/usr/bin/env python3
"""Per-field HIT/MISS heatmap for base Med42 on the 60-doc pilot.

Reads the R1 per-doc CSV and produces a compact "which fields did base Med42
get right?" table grouped by extraction arm and by required field. Answers a
common reviewer question: "on which specific fields does the base model fail?"
Feeds §Results — Med42-8B under M0/M1/M2 prompting.

We re-derive per-field HIT/MISS from the manifests (the per-doc CSV only
records aggregate n_hit / n_miss / n_value_mismatch). So we open each
manifest, walk the parsed module, and compare to the target field-by-field.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(REPO))

from schema import (
    ClinicalSeizureModule, DocumentMetadata, DocumentType, EegModule,
    MedicationModule,
)
from services.smart_repair import try_smart_repair

MANIFESTS = REPO / "data" / "run_manifests_pilot"
TARGETS = REPO / "data" / "episynth_pilot" / "run_001" / "targets"
OUT_DIR = REPO / "eval" / "results"

MODULE_CLASSES = {
    "clinical_seizure": ClinicalSeizureModule,
    "medication": MedicationModule,
    "eeg": EegModule,
}


def _parse_doc_id(doc_id: str):
    if not doc_id.startswith("pilot-"):
        return None
    parts = doc_id[len("pilot-"):].split("-")
    if len(parts) < 3: return None
    pid = parts[-1]
    if parts[0] == "C0":
        return "C0", "C0", pid
    return "-".join(parts[:-2]), parts[-2], pid


def _required_fields(target: dict):
    """Return list of (field_path, expected_value) for scoring."""
    fields = []
    cs = target.get("clinical_seizure") or {}
    for key in ("epilepsy_type",):
        ev = cs.get(key) or {}
        if isinstance(ev, dict) and ev.get("value") is not None:
            fields.append((f"clinical_seizure.{key}", ev["value"]))
    sf = cs.get("seizure_frequency") or {}
    if isinstance(sf, dict) and sf.get("value") is not None:
        v = sf["value"]
        for sub in ("period", "count_min", "count_max"):
            fields.append((f"clinical_seizure.seizure_frequency.{sub}", v.get(sub)))
    eeg = target.get("eeg") or {}
    bg = eeg.get("background") or {}
    if isinstance(bg, dict) and bg.get("value") is not None:
        fields.append(("eeg.background", bg["value"]))
    return fields


def _walk(obj, path):
    for p in path.split("."):
        if not isinstance(obj, dict): return None
        obj = obj.get(p)
    return obj


def main() -> None:
    # per (extract_arm, field_path) → Counter of outcomes
    by_arm_field = defaultdict(Counter)
    doc_count_by_field = Counter()
    seen = set()

    for f in MANIFESTS.rglob("*.json"):
        m = json.loads(f.read_text())
        info = _parse_doc_id(m.get("source_doc_id", ""))
        if not info: continue
        _, _, pid = info
        prompt_id = m.get("prompt_id", "")
        parts = prompt_id.split(".")
        if len(parts) != 3: continue
        module_name, extraction_arm, _v = parts
        module_cls = MODULE_CLASSES.get(module_name)
        if module_cls is None: continue
        # Include the RENDER arm/cond in the key so each pilot cell counts.
        render = _parse_doc_id(m.get("source_doc_id", ""))
        render_key = f"{render[0]}/{render[1]}" if render else "?"
        key = (pid, render_key, extraction_arm, module_name)
        if key in seen: continue
        seen.add(key)

        target_path = TARGETS / pid / "target_phenotype.json"
        if not target_path.exists(): continue
        target = json.loads(target_path.read_text())

        doc = DocumentMetadata(
            doc_id=m.get("source_doc_id", ""), patient_id=pid,
            doc_type=DocumentType.PROGRESS_NOTE, doc_date=date(2026, 9, 25),
        )
        validated, _p, _e = try_smart_repair(m.get("raw_response", ""), module_cls, doc)
        parsed = validated.model_dump(mode="json") if validated else None

        for field_path, expected in _required_fields(target):
            # Only fields belonging to the current module
            fmodule = field_path.split(".")[0]
            if fmodule != module_name: continue
            # `parsed` is the module dump directly — strip the leading module.
            inner_path = field_path[len(fmodule) + 1:]
            got = _walk(parsed or {}, inner_path)
            got_val = got.get("value") if isinstance(got, dict) else got
            if got_val is None:
                outcome = "MISS"
            elif str(got_val).strip().lower() == str(expected).strip().lower():
                outcome = "HIT"
            else:
                outcome = "MISMATCH"
            by_arm_field[(extraction_arm, field_path)][outcome] += 1
            doc_count_by_field[field_path] += 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Group by field, columns = M0/M1/M2 (HIT count)
    all_fields = sorted({field for (_, field) in by_arm_field.keys()})
    rows = []
    for field in all_fields:
        row = {"field": field}
        for arm in ("M0", "M1", "M2"):
            c = by_arm_field[(arm, field)]
            n = c["HIT"] + c["MISS"] + c["MISMATCH"]
            hits = c["HIT"]
            row[f"{arm}_hit"] = hits
            row[f"{arm}_total"] = n
            row[f"{arm}_hit_pct"] = round(100 * hits / n, 1) if n else 0.0
        rows.append(row)

    with (OUT_DIR / "med42_pilot_field_heatmap.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows: w.writerow(r)

    md = [
        "## Base-Med42 per-field HIT rate on 60-doc pilot (Table 5c candidate)\n",
        "*Each row: one required field across the strict-scored set. "
        "Columns: HIT count / total docs where the field was applicable.*\n",
        "| Field | M0 HIT | M1 HIT | M2 HIT | note |",
        "|---|---|---|---|---|",
    ]
    interp = {
        "clinical_seizure.epilepsy_type":
            "closed enum, high content signal — most likely to hit",
        "clinical_seizure.seizure_frequency.count_min":
            "numeric — requires exact value match",
        "clinical_seizure.seizure_frequency.count_max":
            "numeric — requires exact value match",
        "clinical_seizure.seizure_frequency.period":
            "closed enum day/week/month/year",
        "eeg.background":
            "EEG applicable to P005/P006 only (n=2 docs per arm)",
    }
    for r in rows:
        cell = lambda arm: f"{r[arm+'_hit']}/{r[arm+'_total']}"
        md.append(f"| `{r['field']}` | {cell('M0')} | {cell('M1')} | {cell('M2')} | "
                  f"{interp.get(r['field'], '')} |")
    (OUT_DIR / "med42_pilot_field_heatmap.md").write_text("\n".join(md) + "\n")
    for r in rows:
        print(f"  {r['field']:<50}  M0={r['M0_hit']}/{r['M0_total']}  "
              f"M1={r['M1_hit']}/{r['M1_total']}  M2={r['M2_hit']}/{r['M2_total']}")
    print(f"\nwrote {OUT_DIR/'med42_pilot_field_heatmap.md'}")


if __name__ == "__main__":
    main()
