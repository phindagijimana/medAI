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

import argparse
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

DEFAULT_MANIFESTS = REPO / "data" / "run_manifests_pilot"
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


def _target_required(target: dict, include_null: bool = False):
    """Return list of (field_path, expected, evidence_text) tuples.

    When include_null=True (lenient scoring), we ALSO emit tuples for
    Evidence entries where the target says value=None + certainty=not_documented.
    A HIT for those requires the model to also emit value=None with
    certainty=not_documented (correct absence prediction).
    """
    reqs = []

    def _add(module, field, ev):
        if not isinstance(ev, dict): return
        val = ev.get("value")
        if val is not None:
            reqs.append((f"{module}.{field}", val, ev.get("evidence_text")))
        elif include_null and ev.get("certainty") == "not_documented":
            reqs.append((f"{module}.{field}", None, None))

    cs = target.get("clinical_seizure") or {}
    _add("clinical_seizure", "epilepsy_type",             cs.get("epilepsy_type"))
    _add("clinical_seizure", "predominant_seizure_type",  cs.get("predominant_seizure_type"))
    _add("clinical_seizure", "age_at_onset_years",        cs.get("age_at_onset_years"))
    _add("clinical_seizure", "etiology_category",         cs.get("etiology_category"))
    # seizure_frequency has nested structure — flatten its scored subfields
    sf_ev = cs.get("seizure_frequency") or {}
    if isinstance(sf_ev, dict):
        sf_val = sf_ev.get("value")
        if sf_val is not None:
            reqs.append(("clinical_seizure.seizure_frequency.period",    sf_val.get("period"),
                         sf_ev.get("evidence_text")))
            reqs.append(("clinical_seizure.seizure_frequency.count_min", sf_val.get("count_min"),
                         sf_ev.get("evidence_text")))
            reqs.append(("clinical_seizure.seizure_frequency.count_max", sf_val.get("count_max"),
                         sf_ev.get("evidence_text")))
        elif include_null and sf_ev.get("certainty") == "not_documented":
            reqs.append(("clinical_seizure.seizure_frequency", None, None))

    med = target.get("medication") or {}
    _add("medication", "drug_resistance_status", med.get("drug_resistance_status"))
    # current_asms is a list of Evidence — score the first ASM's generic_name if present
    asms = med.get("current_asms") or []
    if isinstance(asms, list) and asms and isinstance(asms[0], dict):
        first_asm = asms[0]
        val = first_asm.get("value")
        if isinstance(val, dict) and val.get("generic_name"):
            reqs.append(("medication.current_asms[0].generic_name",
                         val.get("generic_name"), first_asm.get("evidence_text")))

    eeg = target.get("eeg") or {}
    _add("eeg", "background", eeg.get("background"))

    mri = target.get("mri") or {}
    # MRI findings list — first finding value if present
    findings = mri.get("findings") or []
    if isinstance(findings, list) and findings and isinstance(findings[0], dict):
        first = findings[0]
        if first.get("value") is not None:
            reqs.append(("mri.findings[0]", first.get("value"), first.get("evidence_text")))

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
    """Score a single field.

    If expected is None (lenient-only case, target said not_documented):
      - extracted None or value=None → HIT (correct absence)
      - extracted has a value      → VALUE_MISMATCH (over-extraction)

    Otherwise (expected is a real value):
      - extracted None or value=None → MISS
      - value matches expected        → HIT
      - value differs                → VALUE_MISMATCH
    """
    got_val = None
    got_cert = None
    if isinstance(extracted, dict):
        got_val = extracted.get("value")
        got_cert = extracted.get("certainty")
    elif extracted is not None:
        got_val = extracted

    if expected is None:
        # Lenient: correct absence
        if got_val is None:
            return "HIT", None
        # Model claims a value where target said none — treat as over-extraction
        return "VALUE_MISMATCH", got_val

    # Strict case: expected is a real value
    if got_val is None:
        return "MISS", None
    try:
        if isinstance(expected, (int, float)) and isinstance(got_val, (int, float)):
            hit = abs(float(got_val) - float(expected)) < 1e-6
        else:
            hit = str(got_val).strip().lower() == str(expected).strip().lower()
    except Exception:
        hit = False
    return ("HIT" if hit else "VALUE_MISMATCH"), got_val


def _load_all_manifests_by_key(manifests_dir: Path):
    """Return {(render_arm, render_cond, pid, extraction_arm, module): (parsed_module_dict_or_None, variant_tag)}.

    variant_tag encodes model + decoding provenance so tuned / constrained
    runs can be summarized in separate rows: "" (base unconstrained),
    "lora" (tuned), "constr" (constrained), "lora+constr" (both).
    """
    out = {}
    seen_pairs = set()
    for f in manifests_dir.rglob("*.json"):
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
        model_name = str(m.get("model_name", ""))
        constrained = bool((m.get("decoding") or {}).get("constrained", False))
        tags = []
        if "+lora:" in model_name:
            tags.append("lora")
        if constrained:
            tags.append("constr")
        variant_tag = "+".join(tags)
        parsed = None if validated is None else validated.model_dump(mode="json")
        out[key] = (parsed, variant_tag)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifests-dir", default=str(DEFAULT_MANIFESTS),
                    help="Where to look for per-inference JSON manifests.")
    ap.add_argument("--suffix", default="",
                    help="Suffix for output filenames "
                         "(e.g. 'tuned', 'tuned_constrained').")
    ap.add_argument("--lenient", action="store_true",
                    help="Lenient scoring: correctly-emitted "
                         "not_documented Evidence counts as HIT.")
    args = ap.parse_args()

    manifests_dir = Path(args.manifests_dir)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not manifests_dir.exists():
        print(f"No manifests at {manifests_dir}. Run the SLURM job first "
              f"(sbatch scripts/slurm_med42_on_pilot.sh).", file=sys.stderr)
        sys.exit(2)

    manifests = _load_all_manifests_by_key(manifests_dir)
    print(f"Manifests loaded: {len(manifests)} from {manifests_dir}")

    per_doc_rows = []
    # aggregate: arm_key → counters
    per_agg = defaultdict(lambda: {"hits": 0, "misses": 0, "mismatches": 0, "docs": 0})
    # per-field × variant breakdown: (variant_label, field_path) → counters
    per_field = defaultdict(lambda: {"hits": 0, "misses": 0, "mismatches": 0})

    # Enumerate expected (render_arm, render_cond, pid, extraction_arm) space,
    # bucketed by variant so tuned / constrained runs get their own aggregate rows.
    from collections import defaultdict as _dd
    per_key_docs = _dd(list)
    variant_by_group: dict = {}
    for (render_arm, render_cond, pid, extraction_arm, module_name), (m_dict, variant_tag) in manifests.items():
        grp = (render_arm, render_cond, pid, extraction_arm, variant_tag)
        per_key_docs[grp].append((module_name, m_dict))
        variant_by_group[grp] = variant_tag

    for (render_arm, render_cond, pid, extraction_arm, variant_tag), modules in per_key_docs.items():
        target_path = TARGETS_DIR / pid / "target_phenotype.json"
        if not target_path.exists():
            continue
        target = json.loads(target_path.read_text())
        reqs = _target_required(target, include_null=args.lenient)

        # Merge module dicts for lookup
        combined = {}
        for module_name, m_dict in modules:
            combined[module_name] = m_dict or {}

        variant_label = variant_tag or "base"
        n_hit = n_miss = n_mis = 0
        for field_path, expected, _ev in reqs:
            module = field_path.split(".")[0]
            ex_field = _traverse_module(combined.get(module, {}), field_path, module)
            outcome, got = _score_field(field_path, expected, ex_field)
            if outcome == "HIT": n_hit += 1
            elif outcome == "MISS": n_miss += 1
            else: n_mis += 1
            # Per-field breakdown for §Results table
            key = (variant_label, field_path)
            if outcome == "HIT": per_field[key]["hits"] += 1
            elif outcome == "MISS": per_field[key]["misses"] += 1
            else: per_field[key]["mismatches"] += 1

        arm_key = f"{render_arm}/{render_cond}/{extraction_arm}/{variant_label}"
        per_agg[arm_key]["hits"] += n_hit
        per_agg[arm_key]["misses"] += n_miss
        per_agg[arm_key]["mismatches"] += n_mis
        per_agg[arm_key]["docs"] += 1

        per_doc_rows.append({
            "render_arm": render_arm, "render_condition": render_cond,
            "extraction_arm": extraction_arm, "variant": variant_label,
            "patient_id": pid,
            "n_required": len(reqs), "n_hit": n_hit,
            "n_miss": n_miss, "n_value_mismatch": n_mis,
        })

    if not per_doc_rows:
        print("No matching pilot manifests found. Did the SLURM job complete?",
              file=sys.stderr)
        sys.exit(3)

    # Append "_lenient" to filename tag so strict + lenient runs coexist.
    tag = f"_{args.suffix}" if args.suffix else ""
    if args.lenient:
        tag = f"{tag}_lenient"
    with (OUT_DIR / f"med42_on_pilot_perdoc{tag}.csv").open("w", newline="", encoding="utf-8") as fh:
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

    with (OUT_DIR / f"med42_on_pilot_aggregate{tag}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(agg_rows[0].keys()))
        w.writeheader()
        for r in agg_rows:
            w.writerow(r)

    # Per-field × variant breakdown for §Results narrative on which
    # fields the model gets right vs which it fails on.
    field_rows = []
    for (variant, field), c in sorted(per_field.items()):
        total = c["hits"] + c["misses"] + c["mismatches"]
        recall = c["hits"] / total if total else 0.0
        precision = c["hits"] / (c["hits"] + c["mismatches"]) if (c["hits"] + c["mismatches"]) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        field_rows.append({
            "variant": variant, "field": field,
            "n": total, "hits": c["hits"], "misses": c["misses"],
            "mismatches": c["mismatches"],
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        })
    if field_rows:
        with (OUT_DIR / f"med42_on_pilot_perfield{tag}.csv").open(
                "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(field_rows[0].keys()))
            w.writeheader()
            for r in field_rows:
                w.writerow(r)
        pf_md = [
            f"## Per-field F1 breakdown — pilot corpus{(' — ' + args.suffix) if args.suffix else ''}"
            f"{' (lenient)' if args.lenient else ''}\n",
            f"*Aggregated across all render-arm / cond / extraction-arm cells "
            f"per variant. Manifests: `{manifests_dir}`.*\n",
            "| variant | field | n | HIT | MISS | mismatch | P | R | F1 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in field_rows:
            pf_md.append(f"| {r['variant']} | `{r['field']}` | {r['n']} | "
                         f"{r['hits']} | {r['misses']} | {r['mismatches']} | "
                         f"{r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} |")
        (OUT_DIR / f"med42_on_pilot_perfield{tag}.md").write_text("\n".join(pf_md) + "\n")

    md = [
        f"## Med42-8B scored against Phase 6D.2 pilot corpus{(' — ' + args.suffix) if args.suffix else ''}\n",
        f"*Generated by `scripts/score_med42_on_pilot.py` on manifests in `{manifests_dir}`.*\n",
        "| render_arm / cond / extract_arm / variant | n_docs | required | HIT | MISS | mismatch | P | R | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in agg_rows:
        md.append(f"| {r['arm_key']} | {r['n_docs']} | {r['n_required_fields']} | "
                  f"{r['hits']} | {r['misses']} | {r['value_mismatches']} | "
                  f"{r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} |")
    (OUT_DIR / f"med42_on_pilot_summary{tag}.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print()
    print(f"{'arm_key':<40} {'docs':>5} {'req':>5} {'HIT':>4} {'MISS':>5} {'MISM':>5}  {'P':>5} {'R':>5} {'F1':>5}")
    print("-" * 95)
    for r in agg_rows:
        print(f"{r['arm_key']:<40} {r['n_docs']:>5} {r['n_required_fields']:>5} "
              f"{r['hits']:>4} {r['misses']:>5} {r['value_mismatches']:>5}  "
              f"{r['precision']:>5.3f} {r['recall']:>5.3f} {r['f1']:>5.3f}")
    print(f"\nwrote → {OUT_DIR/f'med42_on_pilot_summary{tag}.md'}")


if __name__ == "__main__":
    main()
