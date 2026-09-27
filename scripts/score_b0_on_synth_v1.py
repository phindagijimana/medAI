#!/usr/bin/env python3
"""Run the B0 rules baseline against the synth-v1 corpus (n=500 patients,
~1000 rendered documents) and score against the Evidence[T] targets in
data/episynth_corpus/v1/targets/{PID}/target_phenotype.json.

Mirrors scripts/score_b0_on_pilot.py — same required-field logic, same
per-doc / aggregate / markdown outputs — but points at the flat synth-v1
layout (documents/{PID}/{doc_type}/output.txt, no arms/conds).

Writes:
  eval/results/b0_on_synth_v1_perdoc.csv    - one row per (doc_type, pid)
  eval/results/b0_on_synth_v1_aggregate.csv - one row per doc_type + ALL
  eval/results/b0_on_synth_v1_summary.md    - human-readable markdown table
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

from schema import DocumentMetadata, DocumentType, EpilepsyPhenotype  # noqa: F401
from services.baseline_rules_clinical_seizure import extract_clinical_seizure
from services.baseline_rules_eeg import extract_eeg

CORPUS_DIR = REPO / "data" / "episynth_corpus" / "v1"
DOCS_DIR = CORPUS_DIR / "documents"
TARGETS_DIR = CORPUS_DIR / "targets"
OUT_DIR = REPO / "eval" / "results"


def _list_synth_docs():
    """Enumerate every rendered document in synth-v1 as (doc_type, pid, path)."""
    out = []
    for p_dir in sorted(DOCS_DIR.iterdir()):
        if not p_dir.is_dir():
            continue
        pid = p_dir.name
        for dt_dir in sorted(p_dir.iterdir()):
            if not dt_dir.is_dir():
                continue
            p = dt_dir / "output.txt"
            if p.exists():
                out.append((dt_dir.name, pid, p))
    return out


def _target_required(target: dict):
    """Return list of (field_path, expected_value, evidence_text) tuples derived
    from the target phenotype. Only populated fields count. Mirrors
    scripts/score_b0_on_pilot.py._target_required."""
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


def _extracted_field(extracted: dict, field_path: str, module: str):
    if not isinstance(extracted, dict):
        return None
    parts = field_path.split(".")
    if parts[0] == module:
        parts = parts[1:]
    obj = extracted
    for part in parts:
        if obj is None or not isinstance(obj, dict):
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


def _run_module_on_text(pid: str, text: str, target: dict):
    doc = DocumentMetadata(
        doc_id=pid, patient_id=pid,
        doc_type=DocumentType.PROGRESS_NOTE, doc_date=date(2026, 9, 25),
    )
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

    docs = _list_synth_docs()
    print(f"Scoring {len(docs)} synth-v1 documents with B0 rules baseline")

    for doc_type, pid, text_path in docs:
        text = text_path.read_text(encoding="utf-8")
        target_path = TARGETS_DIR / pid / "target_phenotype.json"
        if not target_path.exists():
            continue
        target = json.loads(target_path.read_text())

        extracted, reqs = _run_module_on_text(pid, text, target)

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
            if outcome == "HIT":
                n_hit += 1
            elif outcome == "MISS":
                n_miss += 1
            else:
                n_mis += 1

        # Aggregate per doc_type AND an overall "ALL" bucket.
        for bucket in (doc_type, "ALL"):
            per_arm_agg[bucket]["hits"] += n_hit
            per_arm_agg[bucket]["misses"] += n_miss
            per_arm_agg[bucket]["mismatches"] += n_mis
            per_arm_agg[bucket]["docs"] += 1

        per_doc_rows.append({
            "doc_type": doc_type, "patient_id": pid,
            "n_required": len(reqs), "n_hit": n_hit, "n_miss": n_miss,
            "n_value_mismatch": n_mis,
            "field_results": json.dumps(field_results, ensure_ascii=False),
        })

    with (OUT_DIR / "b0_on_synth_v1_perdoc.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(per_doc_rows[0].keys()))
        w.writeheader()
        for r in per_doc_rows:
            w.writerow(r)

    agg_rows = []
    # Order: ALL first, then doc_type buckets alphabetically.
    keys = ["ALL"] + sorted(k for k in per_arm_agg.keys() if k != "ALL")
    for arm_key in keys:
        a = per_arm_agg[arm_key]
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
    with (OUT_DIR / "b0_on_synth_v1_aggregate.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(agg_rows[0].keys()))
        w.writeheader()
        for r in agg_rows:
            w.writerow(r)

    md = [
        "## B0 rules baseline scored against synth-v1 corpus (n=500 patients, ~1000 documents)\n",
        "*Generated by `scripts/score_b0_on_synth_v1.py`. Reference: `target_phenotype.json` per patient in data/episynth_corpus/v1/targets/. Bucketed by doc_type; the `ALL` row is a micro-average over all rendered documents.*\n",
        "| Bucket | n_docs | required | HIT | MISS | value_mismatch | P | R | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in agg_rows:
        md.append(f"| {r['arm']} | {r['n_docs']} | {r['n_required_fields']} | "
                  f"{r['hits']} | {r['misses']} | {r['value_mismatches']} | "
                  f"{r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} |")
    (OUT_DIR / "b0_on_synth_v1_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print()
    print(f"{'bucket':<20} {'docs':>5} {'req':>5} {'HIT':>4} {'MISS':>5} {'MISM':>5}  {'P':>5} {'R':>5} {'F1':>5}")
    print("-" * 75)
    for r in agg_rows:
        print(f"{r['arm']:<20} {r['n_docs']:>5} {r['n_required_fields']:>5} "
              f"{r['hits']:>4} {r['misses']:>5} {r['value_mismatches']:>5}  "
              f"{r['precision']:>5.3f} {r['recall']:>5.3f} {r['f1']:>5.3f}")
    print(f"\nwrote → {OUT_DIR/'b0_on_synth_v1_summary.md'}")


if __name__ == "__main__":
    main()
