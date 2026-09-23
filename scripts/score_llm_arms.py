#!/usr/bin/env python3
"""Compute per-field P/R/F1 with bootstrap CIs for the M0/M1/M2 arms.

Reads all Med42 manifests produced by SLURM job 89472 (data/run_manifests/),
smart-repairs each raw response, pairs the repaired module against the
matching Fonferko-Shadrach silver label, and scores per-field metrics.

Also computes patient-level bootstrap 95% CIs on:
  - content-validity rate (fraction of docs with ≥1 non-null extracted value)
  - per-field F1

Writes:
  eval/results/llm_arms_perfield.csv       — one row per (arm, module, field)
  eval/results/llm_arms_perfield.json      — same, structured
  eval/results/llm_arms_summary.md         — Markdown tables ready for manuscript
"""

from __future__ import annotations

import json
import math
import random
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema import (
    ClinicalSeizureModule,
    DocumentMetadata,
    DocumentType,
    MedicationModule,
)
from services.smart_repair import try_smart_repair

REPO = Path(__file__).resolve().parent.parent
MANIFESTS = REPO / "data" / "run_manifests"
SILVER = REPO / "data" / "fonferko_shadrach_2024" / "silver_labels_v0_2_1"
OUT_DIR = REPO / "eval" / "results"

MODULE_CLASSES = {
    "clinical_seizure": ClinicalSeizureModule,
    "medication": MedicationModule,
}

CORE_FIELDS = {
    "clinical_seizure": [
        "epilepsy_type", "predominant_seizure_type",
        "age_at_onset_years", "seizure_frequency", "etiology_category",
        "focal_motor_onset",
    ],
    "medication": [
        "drug_resistance_status", "adverse_effects_text",
    ],
}


def _norm(v):
    if v is None:
        return None
    if isinstance(v, dict):
        # value objects — hash on their canonical dict form
        return json.dumps(v, sort_keys=True, default=str)
    if hasattr(v, "value"):
        return v.value
    if isinstance(v, str):
        return v.strip().lower()
    return v


def _get_field_value(module_dict, field_name):
    """Pull the Evidence.value from a module dict for a given field."""
    if not isinstance(module_dict, dict):
        return None
    f = module_dict.get(field_name)
    if not isinstance(f, dict):
        return None
    return f.get("value")


def _multiset_asm_names(med_module_dict):
    """For medication module, extract multiset of ASM generic names across
    current + prior + failed. Used for a list-typed score."""
    if not isinstance(med_module_dict, dict):
        return []
    names = []
    for k in ("current_asms", "prior_asms", "failed_asms"):
        for entry in med_module_dict.get(k, []) or []:
            v = entry.get("value") if isinstance(entry, dict) else None
            if isinstance(v, dict):
                n = v.get("generic_name")
                if n:
                    names.append(str(n).lower())
    return sorted(names)


def _score_pair(pred_val, gold_val):
    """Return (tp, fp, fn, tn) for a single (pred, gold) value pair."""
    if pred_val is None and gold_val is None:
        return (0, 0, 0, 1)  # true negative
    if pred_val is None:
        return (0, 0, 1, 0)  # false negative
    if gold_val is None:
        return (0, 1, 0, 0)  # false positive
    if _norm(pred_val) == _norm(gold_val):
        return (1, 0, 0, 0)  # true positive
    return (0, 1, 1, 0)      # both present but disagree


def _score_multiset(pred_items, gold_items):
    """Return (tp, fp, fn) for multiset comparison."""
    from collections import Counter
    p = Counter(pred_items or [])
    g = Counter(gold_items or [])
    tp = sum((p & g).values())
    fp = sum((p - g).values())
    fn = sum((g - p).values())
    return (tp, fp, fn)


def _f1(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    return (p, r, 2 * p * r / (p + r) if (p + r) else 0.0)


def _bootstrap_f1_ci(doc_scores, n_resamples=1000, seed=0, alpha=0.05):
    """doc_scores: list of (tp, fp, fn) per doc. Returns (mean_f1, lo, hi)."""
    if not doc_scores:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(doc_scores)
    f1s = []
    for _ in range(n_resamples):
        tp = fp = fn = 0
        for _ in range(n):
            i = rng.randrange(n)
            t, fp_, fn_ = doc_scores[i]
            tp += t; fp += fp_; fn += fn_
        _, _, f1 = _f1(tp, fp, fn)
        f1s.append(f1)
    f1s.sort()
    mean_tp = sum(x[0] for x in doc_scores)
    mean_fp = sum(x[1] for x in doc_scores)
    mean_fn = sum(x[2] for x in doc_scores)
    _, _, mean_f1 = _f1(mean_tp, mean_fp, mean_fn)
    lo = f1s[int(math.floor(alpha / 2 * n_resamples))]
    hi = f1s[int(math.ceil((1 - alpha / 2) * n_resamples)) - 1]
    return (mean_f1, lo, hi)


def _bootstrap_rate_ci(bools, n_resamples=1000, seed=0, alpha=0.05):
    if not bools:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(bools)
    means = []
    for _ in range(n_resamples):
        s = sum(bools[rng.randrange(n)] for _ in range(n))
        means.append(s / n)
    means.sort()
    mean = sum(bools) / n
    lo = means[int(math.floor(alpha / 2 * n_resamples))]
    hi = means[int(math.ceil((1 - alpha / 2) * n_resamples)) - 1]
    return (mean, lo, hi)


def _load_silver():
    silver_by_id = {}
    for f in SILVER.glob("EA*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        silver_by_id[d["doc_id"]] = d["phenotype"]
    return silver_by_id


def main():
    silver = _load_silver()

    # arm/module -> field -> list of (tp,fp,fn) per doc
    perfield = defaultdict(lambda: defaultdict(list))
    # arm/module -> list of 0/1 content-valid per doc
    content_valid = defaultdict(list)
    # arm/module -> list of ASM multiset (tp,fp,fn) per doc
    asm_multiset = defaultdict(list)

    seen = defaultdict(set)  # dedupe by (doc_id, arm, module, version)

    for f in MANIFESTS.rglob("*.json"):
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
        if version != "v1":
            continue  # only v1 — keeps per-doc counts at ≤200
        doc_id = m.get("source_doc_id", "")
        key = (doc_id, arm, module_name)
        if key in seen[module_name]:
            continue
        seen[module_name].add(key)

        # Reconstruct + smart-repair
        try:
            doc_type = DocumentType(m.get("source_doc_type", "progress_note"))
        except Exception:
            doc_type = DocumentType.PROGRESS_NOTE
        doc = DocumentMetadata(
            doc_id=doc_id, doc_type=doc_type,
            doc_date=date(2024, 1, 1), patient_id=doc_id,
            icd10cm_codes=[], snomed_ct_codes=[],
        )
        module_cls = MODULE_CLASSES[module_name]
        validated, _parsed, _err = try_smart_repair(
            m.get("raw_response", ""), module_cls, doc,
        )

        pred_dict = validated.model_dump(mode="json") if validated else {}
        gold_dict = (silver.get(doc_id) or {}).get(module_name) or {}

        # Per-field scoring — core set
        arm_key = f"{arm}/{module_name}"
        for fname in CORE_FIELDS.get(module_name, []):
            pv = _get_field_value(pred_dict, fname)
            gv = _get_field_value(gold_dict, fname)
            tp, fp, fn, tn = _score_pair(pv, gv)
            perfield[arm_key][fname].append((tp, fp, fn))

        # Medication ASM multiset
        if module_name == "medication":
            pv_names = _multiset_asm_names(pred_dict)
            gv_names = _multiset_asm_names(gold_dict)
            asm_multiset[arm_key].append(_score_multiset(pv_names, gv_names))

        # Content-valid: at least one non-null Evidence value in pred
        if validated is None:
            content_valid[arm_key].append(0)
        else:
            has_any = False
            for fname, val in pred_dict.items():
                if isinstance(val, dict) and val.get("value") is not None:
                    has_any = True
                    break
                if isinstance(val, list) and len(val) > 0:
                    has_any = True
                    break
            content_valid[arm_key].append(1 if has_any else 0)

    # -----------------------------------------------------------------
    # Build outputs
    # -----------------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    csv_lines = ["arm,module,field,n,tp,fp,fn,precision,recall,f1,f1_lo95,f1_hi95"]
    json_out = defaultdict(dict)
    for arm_key in sorted(perfield):
        arm, module = arm_key.split("/")
        for fname, scores in sorted(perfield[arm_key].items()):
            tp = sum(s[0] for s in scores)
            fp = sum(s[1] for s in scores)
            fn = sum(s[2] for s in scores)
            p, r, f1 = _f1(tp, fp, fn)
            mean_f1, lo, hi = _bootstrap_f1_ci(scores)
            csv_lines.append(
                f"{arm},{module},{fname},{len(scores)},{tp},{fp},{fn},"
                f"{p:.4f},{r:.4f},{f1:.4f},{lo:.4f},{hi:.4f}"
            )
            json_out[arm_key][fname] = {
                "n": len(scores), "tp": tp, "fp": fp, "fn": fn,
                "precision": p, "recall": r, "f1": f1,
                "f1_ci": {"lo": lo, "hi": hi},
            }
        # ASM multiset for medication arms
        if module == "medication" and asm_multiset.get(arm_key):
            scores = asm_multiset[arm_key]
            tp = sum(s[0] for s in scores)
            fp = sum(s[1] for s in scores)
            fn = sum(s[2] for s in scores)
            p, r, f1 = _f1(tp, fp, fn)
            mean_f1, lo, hi = _bootstrap_f1_ci(scores)
            csv_lines.append(
                f"{arm},{module},asm_names_multiset,{len(scores)},{tp},{fp},{fn},"
                f"{p:.4f},{r:.4f},{f1:.4f},{lo:.4f},{hi:.4f}"
            )
            json_out[arm_key]["asm_names_multiset"] = {
                "n": len(scores), "tp": tp, "fp": fp, "fn": fn,
                "precision": p, "recall": r, "f1": f1,
                "f1_ci": {"lo": lo, "hi": hi},
            }
    (OUT_DIR / "llm_arms_perfield.csv").write_text("\n".join(csv_lines) + "\n",
                                                     encoding="utf-8")
    (OUT_DIR / "llm_arms_perfield.json").write_text(
        json.dumps({k: dict(v) for k, v in json_out.items()}, indent=2),
        encoding="utf-8",
    )

    # Content-validity CIs
    content_rows = []
    for arm_key in sorted(content_valid):
        vals = content_valid[arm_key]
        mean, lo, hi = _bootstrap_rate_ci(vals)
        content_rows.append((arm_key, len(vals), sum(vals), mean, lo, hi))

    # -----------------------------------------------------------------
    # Markdown tables for the manuscript
    # -----------------------------------------------------------------
    md_lines = [
        "# LLM-arm per-field metrics on Fonferko-Shadrach silver labels\n",
        "*Generated by `scripts/score_llm_arms.py`. Bootstrap 95% CIs from 1,000 "
        "patient-level resamples (seed = 0). Silver-vs-smart-repaired-output; "
        "gold subset pending.*\n",
        "## Table 4a. Content-validity rate by arm × module (with 95% CI)\n",
        "| Arm | Module | n docs | Content-valid | Rate | 95% CI |",
        "|---|---|---:|---:|---:|---|",
    ]
    for arm_key, n, valid, mean, lo, hi in content_rows:
        arm, module = arm_key.split("/")
        md_lines.append(
            f"| {arm} | {module} | {n} | {valid} | "
            f"{mean:.3f} | [{lo:.3f}, {hi:.3f}] |"
        )

    md_lines.append("\n## Table 4b. Per-field precision / recall / F1 (with 95% CI on F1)\n")
    md_lines.append("| Arm | Module | Field | n | P | R | F1 | 95% CI on F1 |")
    md_lines.append("|---|---|---|---:|---:|---:|---:|---|")
    for arm_key in sorted(json_out):
        arm, module = arm_key.split("/")
        for fname, s in sorted(json_out[arm_key].items()):
            md_lines.append(
                f"| {arm} | {module} | {fname} | {s['n']} | "
                f"{s['precision']:.2f} | {s['recall']:.2f} | {s['f1']:.2f} | "
                f"[{s['f1_ci']['lo']:.2f}, {s['f1_ci']['hi']:.2f}] |"
            )
    (OUT_DIR / "llm_arms_summary.md").write_text("\n".join(md_lines) + "\n",
                                                    encoding="utf-8")

    # -----------------------------------------------------------------
    # Console summary
    # -----------------------------------------------------------------
    print("=== Content-validity rate by arm × module (with 95% CI) ===")
    print(f"{'arm/module':<32}  {'n':>4}  {'valid':>5}  {'rate':>6}  95% CI")
    for arm_key, n, valid, mean, lo, hi in content_rows:
        print(f"{arm_key:<32}  {n:>4}  {valid:>5}  {mean:>5.3f}   [{lo:.3f}, {hi:.3f}]")
    print(f"\nCSV → {OUT_DIR / 'llm_arms_perfield.csv'}")
    print(f"JSON → {OUT_DIR / 'llm_arms_perfield.json'}")
    print(f"Markdown → {OUT_DIR / 'llm_arms_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
