#!/usr/bin/env python3
"""Compute per-field P/R/F1 with bootstrap CIs, scored DIRECTLY against
Fonferko-Shadrach's native clinician-adjudicated gold annotations
(Zenodo 8356494) rather than against our derived silver labels.

Scope of scored fields is defined in `docs/FONFERKO_GOLD_SCOPE.md`.

Reads all Med42 manifests in `data/run_manifests/`, smart-repairs each raw
response, and scores against F-S gold on the 8 shared fields:

  - MedicationModule.current_asms                 → Prescription.DrugName (multiset F1)
  - ClinicalSeizureModule.seizure_frequency       → SeizureFrequency
      (period, count_min, count_max — each scored separately)
  - ClinicalSeizureModule.epilepsy_type           → Diagnosis+DiagCategory=Epilepsy
  - ClinicalSeizureModule.predominant_seizure_type→ Diagnosis+DiagCategory ∈ {MultipleSeizures, SingleSeizure}
  - ClinicalSeizureModule.age_at_onset_years      → Onset.Age

Writes:
  eval/results/llm_arms_vs_fs_gold.csv
  eval/results/llm_arms_vs_fs_gold.json
  eval/results/llm_arms_vs_fs_gold.summary.md
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema import (
    ClinicalSeizureModule, DocumentMetadata, DocumentType,
    MedicationModule,
)
from services.smart_repair import try_smart_repair


REPO = Path(__file__).resolve().parent.parent
MANIFESTS = REPO / "data" / "run_manifests"
FS_GOLD_DIR = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8356494" / "Json"
OUT = REPO / "eval" / "results"


# ---------------------------------------------------------------------------
# F-S gold normalization
# ---------------------------------------------------------------------------


# Diagnosis text → ILAE 2017 top-level epilepsy_type. Keyword-based; only
# used when DiagCategory == "Epilepsy". Ordered — first hit wins.
_EPILEPSY_TYPE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"generali[sz]ed", re.I), "generalized"),
    (re.compile(r"combined.*focal.*generali[sz]ed|combined generali[sz]ed and focal", re.I), "combined_focal_generalized"),
    (re.compile(r"focal|temporal|frontal|parietal|occipital|insular", re.I), "focal"),
]

# Diagnosis text → ILAE 2017 basic seizure type. Only used when DiagCategory ∈
# {MultipleSeizures, SingleSeizure}.
_SEIZURE_TYPE_RULES: list[tuple[re.Pattern, str]] = [
    # Absence variants first (before generic "generalised")
    (re.compile(r"absence", re.I), "absence_typical"),
    # Bilateral / secondarily generalized (focal → bilateral)
    (re.compile(r"secondar(?:ily|y).*generali[sz]ed|focal.*bilateral.*tonic.*clonic|bilateral.*tonic.*clonic", re.I),
     "focal_to_bilateral_tonic_clonic"),
    # Generalized tonic-clonic
    (re.compile(r"generali[sz]ed.*tonic.*clonic|GTCS|primary.*generali[sz]ed", re.I),
     "generalized_tonic_clonic"),
    # Myoclonic
    (re.compile(r"myoclonic", re.I), "myoclonic"),
    # Atonic / drop attacks
    (re.compile(r"atonic|drop.*attack", re.I), "atonic"),
    # Focal aware / impaired-awareness
    (re.compile(r"focal.*(loss.*awareness|impaired.*awareness|complex.*partial)", re.I),
     "focal_impaired_awareness"),
    (re.compile(r"focal.*aware|simple.*partial", re.I),
     "focal_aware"),
    # Focal with unspecified awareness
    (re.compile(r"focal", re.I), "focal_unknown_awareness"),
]

_TIME_PERIOD_MAP = {"day": "day", "week": "week", "month": "month",
                    "year": "year"}


def _norm_diag_epilepsy(txt: str) -> str | None:
    for rx, tag in _EPILEPSY_TYPE_RULES:
        if rx.search(txt):
            return tag
    return "unknown"


def _norm_diag_seizure(txt: str) -> str | None:
    for rx, tag in _SEIZURE_TYPE_RULES:
        if rx.search(txt):
            return tag
    return None


def _load_fs_gold_for_doc(doc_id: str) -> dict:
    """Return a normalized dict of scored fields for one F-S gold doc.

    Fields whose gold is absent are set to None (treated as no-reference —
    the doc doesn't contribute to F1 for that field)."""
    f = FS_GOLD_DIR / f"{doc_id}.json"
    if not f.exists():
        return {}
    entities = json.loads(f.read_text(encoding="utf-8"))

    out = {
        "current_asms": [],           # multiset of drug names
        "seizure_period": None,
        "seizure_count_min": None,
        "seizure_count_max": None,
        "epilepsy_type": None,
        "predominant_seizure_type": None,
        "age_at_onset_years": None,
    }

    for ent in entities:
        e = ent.get("entity")
        a = ent.get("attributes", {}) or {}
        txt = (ent.get("text") or "").replace("-", " ").lower()
        neg = (a.get("Negation") or "").lower()
        if neg == "negated":
            continue

        if e == "Prescription":
            drug = (a.get("DrugName") or "").strip().lower()
            if drug:
                out["current_asms"].append(drug)

        elif e == "SeizureFrequency":
            tp = (a.get("TimePeriod") or "").strip().lower()
            if tp in _TIME_PERIOD_MAP and out["seizure_period"] is None:
                out["seizure_period"] = _TIME_PERIOD_MAP[tp]
            try:
                lo = a.get("LowerNumberOfSeizures")
                hi = a.get("UpperNumberOfSeizures")
                if lo and out["seizure_count_min"] is None:
                    out["seizure_count_min"] = float(lo)
                if hi and out["seizure_count_max"] is None:
                    out["seizure_count_max"] = float(hi)
            except (ValueError, TypeError):
                pass

        elif e == "Diagnosis":
            dc = a.get("DiagCategory", "").lower()
            if dc == "epilepsy":
                if out["epilepsy_type"] is None:
                    out["epilepsy_type"] = _norm_diag_epilepsy(txt)
            elif dc in ("multipleseizures", "singleseizure"):
                if out["predominant_seizure_type"] is None:
                    st = _norm_diag_seizure(txt)
                    if st:
                        out["predominant_seizure_type"] = st

        elif e == "Onset":
            try:
                age = a.get("Age") or a.get("AgeLower")
                unit = (a.get("AgeUnit") or "years").lower()
                if age and out["age_at_onset_years"] is None:
                    v = float(age)
                    if unit.startswith("month"):
                        v = v / 12.0
                    out["age_at_onset_years"] = v
            except (ValueError, TypeError):
                pass

    return out


# ---------------------------------------------------------------------------
# Scoring primitives (reused pattern from score_llm_arms.py)
# ---------------------------------------------------------------------------


def _score_scalar(pred, gold, tolerance=None):
    """(tp, fp, fn, tn) for a single (pred, gold) scalar pair.
    Skipped when gold is None (returns None → no contribution)."""
    if gold is None:
        return None
    if pred is None and gold is None:
        return (0, 0, 0, 1)
    if pred is None:
        return (0, 0, 1, 0)
    if tolerance is not None:
        try:
            if abs(float(pred) - float(gold)) <= tolerance:
                return (1, 0, 0, 0)
        except (ValueError, TypeError):
            pass
        return (0, 1, 1, 0)
    if str(pred).strip().lower() == str(gold).strip().lower():
        return (1, 0, 0, 0)
    return (0, 1, 1, 0)


def _score_multiset(pred_items, gold_items):
    if not gold_items:
        return None
    p = Counter([x.strip().lower() for x in (pred_items or []) if x])
    g = Counter([x.strip().lower() for x in (gold_items or []) if x])
    tp = sum((p & g).values())
    fp = sum((p - g).values())
    fn = sum((g - p).values())
    return (tp, fp, fn, 0)


def _f1(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    return (p, r, 2 * p * r / (p + r) if (p + r) else 0.0)


def _bootstrap_f1_ci(doc_scores, n_resamples=1000, seed=0, alpha=0.05):
    if not doc_scores:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(doc_scores)
    f1s = []
    for _ in range(n_resamples):
        tp = fp = fn = 0
        for _ in range(n):
            i = rng.randrange(n)
            t, fp_, fn_, _tn = doc_scores[i]
            tp += t; fp += fp_; fn += fn_
        _, _, f1 = _f1(tp, fp, fn)
        f1s.append(f1)
    f1s.sort()
    mean_tp = sum(x[0] for x in doc_scores)
    mean_fp = sum(x[1] for x in doc_scores)
    mean_fn = sum(x[2] for x in doc_scores)
    _, mean_r, mean_f1 = _f1(mean_tp, mean_fp, mean_fn)
    mean_p, _, _ = _f1(mean_tp, mean_fp, mean_fn)
    lo = f1s[int(math.floor(alpha / 2 * n_resamples))]
    hi = f1s[int(math.ceil((1 - alpha / 2) * n_resamples)) - 1]
    return (mean_p, mean_r, mean_f1, lo, hi)


# ---------------------------------------------------------------------------
# Model output extraction (via smart_repair)
# ---------------------------------------------------------------------------


MODULE_CLASSES = {
    "clinical_seizure": ClinicalSeizureModule,
    "medication": MedicationModule,
}


def _extract_pred(manifest: dict) -> tuple[str | None, str | None, dict | None]:
    """Return (module_name, arm, module_dict) for one manifest."""
    pid = manifest.get("prompt_id", "")
    parts = pid.split(".")
    if len(parts) != 3:
        return (None, None, None)
    module_name, arm, version = parts
    if module_name not in MODULE_CLASSES or version != "v1":
        return (None, None, None)
    doc_id = manifest.get("source_doc_id", "")
    doc = DocumentMetadata(
        doc_id=doc_id, doc_type=DocumentType.PROGRESS_NOTE,
        doc_date=date(2024, 1, 1), patient_id=doc_id,
        icd10cm_codes=[], snomed_ct_codes=[],
    )
    validated, _p, _e = try_smart_repair(
        manifest.get("raw_response", ""), MODULE_CLASSES[module_name], doc,
    )
    if validated is None:
        return (module_name, arm, None)
    return (module_name, arm, validated.model_dump(mode="json"))


def _pred_current_asms(mod: dict) -> list[str]:
    out = []
    for ev in (mod.get("current_asms") or []):
        v = ev.get("value") if isinstance(ev, dict) else None
        if isinstance(v, dict):
            name = (v.get("generic_name") or "").strip().lower()
            if name:
                out.append(name)
    return out


def _pred_ev_value(mod: dict, field: str):
    ev = mod.get(field) or {}
    if not isinstance(ev, dict):
        return None
    v = ev.get("value")
    return v


def _pred_seizfreq(mod: dict) -> dict:
    ev = mod.get("seizure_frequency") or {}
    v = ev.get("value") if isinstance(ev, dict) else None
    if not isinstance(v, dict):
        return {"period": None, "count_min": None, "count_max": None}
    return {
        "period": (v.get("period") or "").strip().lower() or None,
        "count_min": v.get("count_min"),
        "count_max": v.get("count_max"),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


SCORED_FIELDS = [
    ("medication",       "current_asms",            "multiset"),
    ("clinical_seizure", "seizure_frequency.period",   "scalar"),
    ("clinical_seizure", "seizure_frequency.count_min","tol1"),
    ("clinical_seizure", "seizure_frequency.count_max","tol1"),
    ("clinical_seizure", "epilepsy_type",              "scalar"),
    ("clinical_seizure", "predominant_seizure_type",   "scalar"),
    ("clinical_seizure", "age_at_onset_years",         "tol1"),
]


def _held_out_pids() -> set[str]:
    """Return the 40 F-S patient IDs reserved as held-out test.

    Single source of truth: scripts/finetune_lora_epi.py::_fs_pairs_train_test.
    If the split contract changes there, this reflects it automatically.
    """
    # Late import — the finetune script has heavier deps than this scorer
    # otherwise imports, so we pay the cost only when the flag is set.
    sys.path.insert(0, str(REPO))
    from scripts.finetune_lora_epi import _fs_pairs_train_test  # noqa: WPS433
    _train, test_pids = _fs_pairs_train_test(seed=0)
    return set(test_pids)


def main():
    ap = argparse.ArgumentParser(description="Score LLM arms on F-S native gold.")
    ap.add_argument(
        "--manifests-dir", default=None,
        help="Manifest root (default data/run_manifests — the Med42 F-S sweep).",
    )
    ap.add_argument(
        "--suffix", default="",
        help="Suffix for output filenames (e.g. 'gpt_fs' or 'deepseek_fs').",
    )
    ap.add_argument(
        "--patient-subset", default=None,
        help="Comma-separated F-S pids (e.g. 'EA0161,EA0162,...') to restrict "
             "scoring to. Overrides --held-out-only if both are set.",
    )
    ap.add_argument(
        "--held-out-only", action="store_true",
        help="Score only the 40 held-out test pids from "
             "_fs_pairs_train_test(seed=0). Use with manifests from "
             "run_med42_on_fs_test.py to compute genuine test-set F1.",
    )
    args = ap.parse_args()
    manifests_root = Path(args.manifests_dir) if args.manifests_dir else MANIFESTS
    if not manifests_root.exists():
        raise SystemExit(f"Manifests directory does not exist: {manifests_root}")

    subset: set[str] | None = None
    if args.patient_subset:
        subset = {p.strip() for p in args.patient_subset.split(",") if p.strip()}
        print(f"--patient-subset: restricting scoring to {len(subset)} pid(s).")
    elif args.held_out_only:
        subset = _held_out_pids()
        print(f"--held-out-only: restricting scoring to {len(subset)} "
              f"held-out F-S pid(s).")

    suffix = ("_" + args.suffix) if args.suffix else ""

    # Collect all manifests, dedup per (doc, arm, module) via seen set.
    per_arm_module_doc = defaultdict(dict)   # (arm, module) -> {doc_id: pred_dict}
    for f in manifests_root.rglob("*.json"):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        module_name, arm, pred = _extract_pred(m)
        if module_name is None:
            continue
        doc_id = m.get("source_doc_id", "")
        # Some runs prefix the F-S letter id (e.g. "fs-gpt-gpt-5.6-terra-EA0001")
        # to keep manifest ids distinct across sweeps; the gold key is the bare
        # "EA*" tail — extract it via a substring match so scoring works either
        # way.
        match = re.search(r"(EA\d{4})", doc_id)
        if match:
            doc_id = match.group(1)
        if doc_id not in per_arm_module_doc[(arm, module_name)]:
            per_arm_module_doc[(arm, module_name)][doc_id] = pred

    # Prepare per-arm scores across all letters that have F-S gold
    fs_doc_ids = sorted([f.stem for f in FS_GOLD_DIR.glob("*.json")])
    if subset is not None:
        fs_doc_ids = [d for d in fs_doc_ids if d in subset]
        print(f"F-S gold letters after subset filter: {len(fs_doc_ids)} "
              f"(of {len(subset)} requested)")
    else:
        print(f"F-S gold letters available: {len(fs_doc_ids)}")

    all_gold = {d: _load_fs_gold_for_doc(d) for d in fs_doc_ids}

    # per (arm, module, field) → list[(tp,fp,fn,tn) or None]
    scores: dict[tuple, list] = defaultdict(list)
    n_docs_covered: dict[tuple, int] = defaultdict(int)

    arms = sorted({a for (a, _m) in per_arm_module_doc.keys()})

    for arm in arms:
        for module_name in ("medication", "clinical_seizure"):
            preds = per_arm_module_doc.get((arm, module_name), {})
            for doc_id in fs_doc_ids:
                gold = all_gold[doc_id]
                pred = preds.get(doc_id)

                # medication.current_asms → multiset
                if module_name == "medication":
                    p_asms = _pred_current_asms(pred) if pred else []
                    s = _score_multiset(p_asms, gold.get("current_asms"))
                    if s is not None:
                        scores[(arm, "medication", "current_asms")].append(s)
                        n_docs_covered[(arm, "medication", "current_asms")] += 1
                    continue

                # clinical_seizure fields
                sf = _pred_seizfreq(pred) if pred else {"period": None, "count_min": None, "count_max": None}

                s = _score_scalar(sf["period"], gold.get("seizure_period"))
                if s is not None:
                    scores[(arm, "clinical_seizure", "seizure_frequency.period")].append(s)
                    n_docs_covered[(arm, "clinical_seizure", "seizure_frequency.period")] += 1

                s = _score_scalar(sf["count_min"], gold.get("seizure_count_min"), tolerance=0)
                if s is not None:
                    scores[(arm, "clinical_seizure", "seizure_frequency.count_min")].append(s)
                    n_docs_covered[(arm, "clinical_seizure", "seizure_frequency.count_min")] += 1

                s = _score_scalar(sf["count_max"], gold.get("seizure_count_max"), tolerance=0)
                if s is not None:
                    scores[(arm, "clinical_seizure", "seizure_frequency.count_max")].append(s)
                    n_docs_covered[(arm, "clinical_seizure", "seizure_frequency.count_max")] += 1

                p_et = _pred_ev_value(pred, "epilepsy_type") if pred else None
                s = _score_scalar(p_et, gold.get("epilepsy_type"))
                if s is not None:
                    scores[(arm, "clinical_seizure", "epilepsy_type")].append(s)
                    n_docs_covered[(arm, "clinical_seizure", "epilepsy_type")] += 1

                p_st = _pred_ev_value(pred, "predominant_seizure_type") if pred else None
                s = _score_scalar(p_st, gold.get("predominant_seizure_type"))
                if s is not None:
                    scores[(arm, "clinical_seizure", "predominant_seizure_type")].append(s)
                    n_docs_covered[(arm, "clinical_seizure", "predominant_seizure_type")] += 1

                p_age = _pred_ev_value(pred, "age_at_onset_years") if pred else None
                s = _score_scalar(p_age, gold.get("age_at_onset_years"), tolerance=1.0)
                if s is not None:
                    scores[(arm, "clinical_seizure", "age_at_onset_years")].append(s)
                    n_docs_covered[(arm, "clinical_seizure", "age_at_onset_years")] += 1

    # ---------- Report ----------
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for (arm, module, field), docs in sorted(scores.items()):
        p, r, f1, lo, hi = _bootstrap_f1_ci(docs)
        rows.append({
            "arm": arm, "module": module, "field": field,
            "n_docs_with_gold": n_docs_covered[(arm, module, field)],
            "precision": round(p, 3),
            "recall": round(r, 3),
            "f1": round(f1, 3),
            "f1_ci_lo": round(lo, 3),
            "f1_ci_hi": round(hi, 3),
        })

    (OUT / f"llm_arms_vs_fs_gold{suffix}.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8",
    )
    with (OUT / f"llm_arms_vs_fs_gold{suffix}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else
                           ["arm","module","field","n_docs_with_gold","precision","recall","f1","f1_ci_lo","f1_ci_hi"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    md = [
        "## Table 4b-vs-gold. Per-field P/R/F1 with bootstrap 95% CIs — scored directly against Fonferko-Shadrach 2019/2024 native gold\n",
        "*Generated by `scripts/score_llm_arms_vs_fs_gold.py` on 200 F-S clinic letters. "
        "Model output = Med42-8B smart-repaired. Reference = F-S clinician-adjudicated "
        "gold annotations (Zenodo 8356494). Fields absent from F-S gold are out of scope "
        "(see `docs/FONFERKO_GOLD_SCOPE.md`).*\n",
        "| Arm | Module | Field | n (gold) | Precision | Recall | F1 | 95% CI |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        md.append(
            f"| {r['arm']} | {r['module']} | {r['field']} | {r['n_docs_with_gold']} | "
            f"{r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} | "
            f"[{r['f1_ci_lo']:.3f}, {r['f1_ci_hi']:.3f}] |"
        )
    (OUT / f"llm_arms_vs_fs_gold{suffix}.summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # Console
    print(f"\n{'arm':>3} {'module':<18} {'field':<32}  {'n':>4}  {'P':>5} {'R':>5} {'F1':>5}  95% CI")
    for r in rows:
        print(f"{r['arm']:>3} {r['module']:<18} {r['field']:<32}  {r['n_docs_with_gold']:>4}  "
              f"{r['precision']:>5.3f} {r['recall']:>5.3f} {r['f1']:>5.3f}  "
              f"[{r['f1_ci_lo']:.3f}, {r['f1_ci_hi']:.3f}]")
    print(f"\nwrote → {OUT / ('llm_arms_vs_fs_gold' + suffix + '.summary.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
