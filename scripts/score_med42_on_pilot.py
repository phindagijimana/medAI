#!/usr/bin/env python3
"""Score Med42-8B M0/M1/M2 pilot manifests against Phase 6D.2 targets.

Reads manifests written by scripts/run_med42_on_pilot.py into
data/run_manifests_pilot/, applies the production smart_repair chain,
then compares extracted values to target_phenotype.json per patient.

Emits the same shape of outputs as scripts/score_b0_on_pilot.py so
the two extractors are directly comparable:

  eval/results/med42_on_pilot_perdoc.csv
  eval/results/med42_on_pilot_aggregate.csv
  eval/results/med42_on_pilot_summary.md
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from schema import (
    ClinicalSeizureModule, DocumentMetadata, DocumentType, EegModule,
    MedicationModule,
)
from services.smart_repair import try_smart_repair

MANIFESTS = REPO / "data" / "run_manifests_pilot"
TARGETS_DIR = REPO / "data" / "episynth_pilot" / "run_001" / "targets"
OUT_DIR = REPO / "eval" / "results"

MODULE_CLASSES = {
    "clinical_seizure": ClinicalSeizureModule,
    "medication": MedicationModule,
    "eeg": EegModule,
}


def _parse_doc_id(doc_id: str):
    """Manifests use doc_id = "pilot-<arm>-<cond>-<pid>". Split it back."""
    if not doc_id.startswith("pilot-"):
        return None
    parts = doc_id[len("pilot-"):].split("-")
    if len(parts) < 3:
        return None
    # Last part is patient_id (P001…P006); rest is (arm, cond)
    pid = parts[-1]
    # Handle "C0" arms and "gpt-5.6-x/Cy" arms
    if parts[0] == "C0":
        arm, cond = "C0", "C0"
    else:
        # gpt-5.6-luna-C1-P001 → arm="gpt-5.6-luna", cond="C1"
        arm = "-".join(parts[:-2])
        cond = parts[-2]
    return arm, cond, pid


def _target_required(target: dict):
    """Same shape as score_b0_on_pilot.py."""
    reqs = []
    cs = target.get("clinical_seizure") or {}
    ev = cs.get("epilepsy_type") or {}
    if isinstance(ev, dict) and ev.get("value") is not None:
        reqs.append(("clinical_seizure.epilepsy_type", ev["value"], ev.get("evidence_text")))
    ev = cs.get("seizure_frequency") or {}
    if isinstance(ev, dict) and ev.get("value") is not None:
        v = ev["value"]
        reqs.append(("clinical_seizure.seizure_frequency.period", v.get("period"), ev.get("evidence_text")))
        reqs.append(("clinical_seizure.seizure_frequency.count_min", v.get("count_min"), ev.get("evidence_text")))
        reqs.append(("clinical_seizure.seizure_frequency.count_max", v.get("count_max"), ev.get("evidence_text")))
    eeg = target.get("eeg") or {}
    ev = eeg.get("background") or {}
    if isinstance(ev, dict) and ev.get("value") is not None:
        reqs.append(("eeg.background", ev["value"], ev.get("evidence_text")))
    return reqs


def _traverse_module(mod_dict, field_path, module):
    parts = field_path.split(".")
    if parts[0] == module:
        parts = parts[1:]
    obj = mod_dict
    for part in parts:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def _score_field(field_path, expected, extracted):
    if extracted is None:
        return "MISS", None
    v = extracted.get("value") if isinstance(extracted, dict) else extracted
    if v is None:
        return "MISS", None
    try:
        if isinstance(expected, (int, float)) and isinstance(v, (int, float)):
            hit = abs(float(v) - float(expected)) < 1e-6
        else:
            hit = str(v).strip().lower() == str(expected).strip().lower()
    except Exception:
        hit = False
    return ("HIT" if hit else "VALUE_MISMATCH"), v


def _load_all_manifests_by_key():
    """Return {(render_arm, render_cond, pid, extraction_arm, module): parsed_module_dict_or_None}."""
    out = {}
    seen_pairs = set()
    for f in MANIFESTS.rglob("*.json"):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        pid_info = _parse_doc_id(m.get("source_doc_id", ""))
        if not pid_info:
            continue
        render_arm, render_cond, pid = pid_info
        prompt_id = m.get("prompt_id", "")
        parts = prompt_id.split(".")
        if len(parts) != 3:
            continue
        module_name, extraction_arm, _v = parts
        if module_name not in MODULE_CLASSES:
            continue
        key = (render_arm, render_cond, pid, extraction_arm, module_name)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)

        module_cls = MODULE_CLASSES[module_name]
        doc = DocumentMetadata(
            doc_id=m.get("source_doc_id", ""), patient_id=pid,
            doc_type=DocumentType.PROGRESS_NOTE, doc_date=date(2026, 9, 25),
        )
        validated, _p, _e = try_smart_repair(
            m.get("raw_response", ""), module_cls, doc,
        )
        if validated is None:
            out[key] = None
        else:
            out[key] = validated.model_dump(mode="json")
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not MANIFESTS.exists():
        print(f"No manifests at {MANIFESTS}. Run the SLURM job first "
              f"(sbatch scripts/slurm_med42_on_pilot.sh).", file=sys.stderr)
        sys.exit(2)

    manifests = _load_all_manifests_by_key()
    print(f"Manifests loaded: {len(manifests)}")

    per_doc_rows = []
    # aggregate: (render_arm, render_cond, extraction_arm) → counters
    per_agg = defaultdict(lambda: {"hits": 0, "misses": 0, "mismatches": 0, "docs": 0})

    # Enumerate expected (render_arm, render_cond, pid, extraction_arm) space
    from collections import defaultdict as _dd
    per_key_docs = _dd(list)
    for (render_arm, render_cond, pid, extraction_arm, module_name), m_dict in manifests.items():
        per_key_docs[(render_arm, render_cond, pid, extraction_arm)].append((module_name, m_dict))

    for (render_arm, render_cond, pid, extraction_arm), modules in per_key_docs.items():
        target_path = TARGETS_DIR / pid / "target_phenotype.json"
        if not target_path.exists():
            continue
        target = json.loads(target_path.read_text())
        reqs = _target_required(target)

        # Merge module dicts for lookup
        combined = {}
        for module_name, m_dict in modules:
            combined[module_name] = m_dict or {}

        n_hit = n_miss = n_mis = 0
        for field_path, expected, _ev in reqs:
            module = field_path.split(".")[0]
            ex_field = _traverse_module(combined.get(module, {}), field_path, module)
            outcome, got = _score_field(field_path, expected, ex_field)
            if outcome == "HIT": n_hit += 1
            elif outcome == "MISS": n_miss += 1
            else: n_mis += 1

        arm_key = f"{render_arm}/{render_cond}/{extraction_arm}"
        per_agg[arm_key]["hits"] += n_hit
        per_agg[arm_key]["misses"] += n_miss
        per_agg[arm_key]["mismatches"] += n_mis
        per_agg[arm_key]["docs"] += 1

        per_doc_rows.append({
            "render_arm": render_arm, "render_condition": render_cond,
            "extraction_arm": extraction_arm, "patient_id": pid,
            "n_required": len(reqs), "n_hit": n_hit,
            "n_miss": n_miss, "n_value_mismatch": n_mis,
        })

    if not per_doc_rows:
        print("No matching pilot manifests found. Did the SLURM job complete?",
              file=sys.stderr)
        sys.exit(3)

    with (OUT_DIR / "med42_on_pilot_perdoc.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(per_doc_rows[0].keys()))
        w.writeheader()
        for r in per_doc_rows:
            w.writerow(r)

    agg_rows = []
    for arm_key, a in sorted(per_agg.items()):
        total = a["hits"] + a["misses"] + a["mismatches"]
        recall = a["hits"] / total if total else 0.0
        precision = a["hits"] / (a["hits"] + a["mismatches"]) if (a["hits"] + a["mismatches"]) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        agg_rows.append({
            "arm_key": arm_key, "n_docs": a["docs"],
            "n_required_fields": total, "hits": a["hits"],
            "misses": a["misses"], "value_mismatches": a["mismatches"],
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        })

    with (OUT_DIR / "med42_on_pilot_aggregate.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(agg_rows[0].keys()))
        w.writeheader()
        for r in agg_rows:
            w.writerow(r)

    md = [
        "## Med42-8B M0/M1/M2 scored against Phase 6D.2 pilot corpus\n",
        "*Generated by `scripts/score_med42_on_pilot.py` on manifests in `data/run_manifests_pilot/`.*\n",
        "| render_arm / cond / extract_arm | n_docs | required | HIT | MISS | mismatch | P | R | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in agg_rows:
        md.append(f"| {r['arm_key']} | {r['n_docs']} | {r['n_required_fields']} | "
                  f"{r['hits']} | {r['misses']} | {r['value_mismatches']} | "
                  f"{r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} |")
    (OUT_DIR / "med42_on_pilot_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print()
    print(f"{'arm_key':<40} {'docs':>5} {'req':>5} {'HIT':>4} {'MISS':>5} {'MISM':>5}  {'P':>5} {'R':>5} {'F1':>5}")
    print("-" * 95)
    for r in agg_rows:
        print(f"{r['arm_key']:<40} {r['n_docs']:>5} {r['n_required_fields']:>5} "
              f"{r['hits']:>4} {r['misses']:>5} {r['value_mismatches']:>5}  "
              f"{r['precision']:>5.3f} {r['recall']:>5.3f} {r['f1']:>5.3f}")
    print(f"\nwrote → {OUT_DIR/'med42_on_pilot_summary.md'}")


if __name__ == "__main__":
    main()
