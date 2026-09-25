#!/usr/bin/env python3
"""Run the B0 rules baseline against the 60 pilot documents and score
against the Evidence[T] targets produced by scripts/semantic_plan_to_evidence.py.

Per pilot rendering (60 documents), we:
  1. Load the raw output.txt
  2. Detect which module(s) apply (clinical_seizure for clinic letters,
     eeg for EEG reports)
  3. Run the corresponding rules baseline
  4. Compare extracted values to the target phenotype for that patient
  5. Score per required-assertion: HIT / MISS / VALUE_MISMATCH

Writes:
  eval/results/b0_on_pilot_perdoc.csv     - one row per (arm, cond, pid)
  eval/results/b0_on_pilot_aggregate.csv  - one row per (arm, cond)
  eval/results/b0_on_pilot_summary.md     - human-readable markdown table
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

from schema import DocumentMetadata, DocumentType, EpilepsyPhenotype
from services.baseline_rules_clinical_seizure import extract_clinical_seizure
from services.baseline_rules_eeg import extract_eeg

RUN_DIR = REPO / "data" / "episynth_pilot" / "run_001"
TARGETS_DIR = RUN_DIR / "targets"
OUT_DIR = REPO / "eval" / "results"


def _list_pilot_docs():
    """Enumerate every rendered document in the pilot."""
    out = []
    for arm_dir in sorted(RUN_DIR.iterdir()):
        if not arm_dir.is_dir() or arm_dir.name in ("g2", "targets"):
            continue
        if arm_dir.name == "C0":
            for p_dir in sorted(arm_dir.iterdir()):
                p = p_dir / "output.txt"
                if p.exists():
                    out.append(("C0", "C0", p_dir.name, p))
        elif arm_dir.name.startswith("gpt-"):
            for cond_dir in sorted(arm_dir.iterdir()):
                for p_dir in sorted(cond_dir.iterdir()):
                    p = p_dir / "output.txt"
                    if p.exists():
                        out.append((arm_dir.name, cond_dir.name, p_dir.name, p))
    return out


def _extract_field(phen_dict, field_path):
    """Walk clinical_seizure.epilepsy_type-style path in a dict."""
    obj = phen_dict
    for part in field_path.split("."):
        if obj is None:
            return None
        obj = obj.get(part) if isinstance(obj, dict) else None
    return obj


def _target_required(target: dict):
    """Return list of (field_path, expected_value, evidence_text) tuples
    derived from the target phenotype (only populated fields count)."""
    reqs = []
    cs = target.get("clinical_seizure") or {}
    ev = cs.get("epilepsy_type") or {}
    if isinstance(ev, dict) and ev.get("value") is not None:
        reqs.append(("clinical_seizure.epilepsy_type", ev["value"], ev.get("evidence_text")))
    ev = cs.get("seizure_frequency") or {}
    if isinstance(ev, dict) and ev.get("value") is not None:
        v = ev["value"]
        # SeizureFrequency object → compare on period + count_min + count_max
        reqs.append(("clinical_seizure.seizure_frequency.period", v.get("period"), ev.get("evidence_text")))
        reqs.append(("clinical_seizure.seizure_frequency.count_min", v.get("count_min"), ev.get("evidence_text")))
        reqs.append(("clinical_seizure.seizure_frequency.count_max", v.get("count_max"), ev.get("evidence_text")))
    eeg = target.get("eeg") or {}
    ev = eeg.get("background") or {}
    if isinstance(ev, dict) and ev.get("value") is not None:
        reqs.append(("eeg.background", ev["value"], ev.get("evidence_text")))
    return reqs


def _extracted_field(extracted: dict, field_path: str, module: str):
    """Walk the rules-baseline extracted dict for a field."""
    if not isinstance(extracted, dict):
        return None
    # Root of extracted is the module fields (no top-level 'clinical_seizure' key)
    parts = field_path.split(".")
    # Strip module prefix if present
    if parts[0] == module:
        parts = parts[1:]
    obj = extracted
    for part in parts:
        if obj is None or not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def _score_field(field_path, expected, extracted):
    """Compare expected → extracted for one target field."""
    if extracted is None:
        return "MISS", None
    # extracted is usually an Evidence dict — pull `value`
    v = extracted.get("value") if isinstance(extracted, dict) else extracted
    # If the value is a nested dict (SeizureFrequency), traverse
    if isinstance(v, dict) and "." in field_path and field_path.endswith(("period", "count_min", "count_max")):
        # already traversed at target-extraction step
        pass
    # Compare with light normalization
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


def _run_module_on_text(pid: str, text: str, target: dict):
    """Run the appropriate rules baseline; return dict of (field, extracted_value)."""
    doc = DocumentMetadata(
        doc_id=pid, patient_id=pid,
        doc_type=DocumentType.PROGRESS_NOTE, doc_date=date(2026, 9, 25),
    )
    # Decide which modules apply based on which target fields are populated
    outs = {}
    reqs = _target_required(target)
    modules_needed = set()
    for field_path, _, _ in reqs:
        modules_needed.add(field_path.split(".")[0])
    if "clinical_seizure" in modules_needed:
        outs["clinical_seizure"] = extract_clinical_seizure(text, doc)
    if "eeg" in modules_needed:
        outs["eeg"] = extract_eeg(text, doc)
    return outs, reqs


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    per_doc_rows = []
    per_arm_agg = defaultdict(lambda: {"hits": 0, "misses": 0, "mismatches": 0, "docs": 0})

    docs = _list_pilot_docs()
    print(f"Scoring {len(docs)} pilot documents with B0 rules baseline")

    for arm, cond, pid, text_path in docs:
        text = text_path.read_text(encoding="utf-8")
        target_path = TARGETS_DIR / pid / "target_phenotype.json"
        if not target_path.exists():
            continue
        target = json.loads(target_path.read_text())

        extracted, reqs = _run_module_on_text(pid, text, target)

        # Score each required field
        n_hit = n_miss = n_mis = 0
        field_results = []
        for field_path, expected, _ev in reqs:
            module = field_path.split(".")[0]
            ex_field = _extracted_field(extracted.get(module, {}), field_path, module)
            outcome, got = _score_field(field_path, expected, ex_field)
            field_results.append({
                "field": field_path,
                "expected": expected,
                "extracted": got,
                "outcome": outcome,
            })
            if outcome == "HIT": n_hit += 1
            elif outcome == "MISS": n_miss += 1
            else: n_mis += 1

        arm_key = f"{arm}/{cond}" if arm != "C0" else "C0"
        per_arm_agg[arm_key]["hits"] += n_hit
        per_arm_agg[arm_key]["misses"] += n_miss
        per_arm_agg[arm_key]["mismatches"] += n_mis
        per_arm_agg[arm_key]["docs"] += 1

        per_doc_rows.append({
            "arm": arm, "condition": cond, "patient_id": pid,
            "n_required": len(reqs), "n_hit": n_hit, "n_miss": n_miss,
            "n_value_mismatch": n_mis,
            "field_results": json.dumps(field_results, ensure_ascii=False),
        })

    # Per-doc CSV
    with (OUT_DIR / "b0_on_pilot_perdoc.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(per_doc_rows[0].keys()))
        w.writeheader()
        for r in per_doc_rows:
            w.writerow(r)

    # Aggregate CSV
    agg_rows = []
    for arm_key, a in sorted(per_arm_agg.items()):
        total = a["hits"] + a["misses"] + a["mismatches"]
        recall = a["hits"] / total if total else 0.0
        precision = a["hits"] / (a["hits"] + a["mismatches"]) if (a["hits"] + a["mismatches"]) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        agg_rows.append({
            "arm": arm_key, "n_docs": a["docs"],
            "n_required_fields": total, "hits": a["hits"],
            "misses": a["misses"], "value_mismatches": a["mismatches"],
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        })
    with (OUT_DIR / "b0_on_pilot_aggregate.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(agg_rows[0].keys()))
        w.writeheader()
        for r in agg_rows:
            w.writerow(r)

    # Markdown summary
    md = [
        "## B0 rules baseline scored against Phase 6D.2 pilot corpus (n=60 documents)\n",
        "*Generated by `scripts/score_b0_on_pilot.py`. Reference: `target_phenotype.json` per patient, converted from Phase 6D.1 v2 semantic plans.*\n",
        "| Arm | n_docs | required | HIT | MISS | value_mismatch | P | R | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in agg_rows:
        md.append(f"| {r['arm']} | {r['n_docs']} | {r['n_required_fields']} | "
                  f"{r['hits']} | {r['misses']} | {r['value_mismatches']} | "
                  f"{r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} |")
    (OUT_DIR / "b0_on_pilot_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # Console
    print()
    print(f"{'arm':<25} {'docs':>5} {'req':>5} {'HIT':>4} {'MISS':>5} {'MISM':>5}  {'P':>5} {'R':>5} {'F1':>5}")
    print("-" * 80)
    for r in agg_rows:
        print(f"{r['arm']:<25} {r['n_docs']:>5} {r['n_required_fields']:>5} "
              f"{r['hits']:>4} {r['misses']:>5} {r['value_mismatches']:>5}  "
              f"{r['precision']:>5.3f} {r['recall']:>5.3f} {r['f1']:>5.3f}")
    print(f"\nwrote → {OUT_DIR/'b0_on_pilot_summary.md'}")


if __name__ == "__main__":
    main()
