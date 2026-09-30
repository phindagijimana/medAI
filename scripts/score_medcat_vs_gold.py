#!/usr/bin/env python3
"""Phase 7 — score MedCAT+Rules predictions vs gold (arm B1').

Scoring convention deliberately matches ``scripts/score_med42_on_pilot.py``
so results are directly comparable across arms.  Additions unique to this
scorer:

* **Corpus-agnostic** — F-S 40 held-out silver labels and Synth-v1 gold
  share the same v0.2.1 shape (``{"phenotype": {...}}`` for F-S,
  bare phenotype for Synth-v1).  The loader auto-detects.
* **All 24 core fields** enumerated up-front (missing from gold ==
  ``PENDING``), so per-field tables are complete regardless of corpus
  populated-coverage.
* **Multiset scoring** for list fields (``current_asms``, ``findings``,
  ``other_seizure_types``, ``ied_findings`` …) — matches the F-S
  clinician-adjudicated gold convention (see
  ``scripts/score_llm_arms_vs_fs_gold.py``).

CLI::

    venv-medcat/bin/python scripts/score_medcat_vs_gold.py \
        --corpus fs_test_40 \
        --predictions-dir data/run_manifests_medcat_rules_fs_test_40/ \
        --gold-dir data/fonferko_shadrach_2024/silver_labels_v0_2_1/ \
        --out-csv eval/results/medcat_rules_fs_test_40.csv

Outputs:

* ``<out-csv>`` — per-field P/R/F1 (long form)
* ``<out-csv>.perdoc.csv`` — per-doc P/R/F1
* ``<out-csv>.summary.md`` — headline table

Multiset F1 shape follows Fonferko-Shadrach:
    tp = size of intersection multiset
    fp = pred - gold
    fn = gold - pred
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Field catalogue — 24 core fields (Phase 3a+3b).  Multiset vs scalar noted.
# ---------------------------------------------------------------------------

# (module, field, kind)
# kind ∈ {scalar, multiset, seizfreq, float_tol1, med_multiset,
#         surgery_multiset, ndt_multiset}
CORE_FIELDS: list[tuple[str, str, str]] = [
    # -- Clinical seizure --
    ("clinical_seizure", "epilepsy_type",             "scalar"),
    ("clinical_seizure", "predominant_seizure_type",  "scalar"),
    ("clinical_seizure", "other_seizure_types",       "multiset"),
    ("clinical_seizure", "awareness",                 "scalar"),
    ("clinical_seizure", "semiology_text",            "scalar_str_present"),
    ("clinical_seizure", "age_at_onset_years",        "float_tol1"),
    ("clinical_seizure", "seizure_frequency",         "seizfreq"),
    ("clinical_seizure", "status_epilepticus_history","scalar"),
    ("clinical_seizure", "etiology_category",         "scalar"),
    ("clinical_seizure", "etiology_specifics",        "scalar"),
    ("clinical_seizure", "focal_motor_onset",         "scalar"),
    ("clinical_seizure", "focal_nonmotor_onset",      "scalar"),
    # -- Medication --
    ("medication", "current_asms",                    "med_multiset"),
    ("medication", "prior_asms",                      "med_multiset"),
    ("medication", "failed_asms",                     "med_multiset"),
    ("medication", "drug_resistance_status",          "scalar"),
    ("medication", "surgery_history",                 "surgery_multiset"),
    ("medication", "non_drug_therapies",              "ndt_multiset"),
    # -- MRI --
    ("mri", "overall_normal",                         "scalar"),
    ("mri", "findings",                               "multiset"),
    ("mri", "hippocampal_sclerosis",                  "scalar"),
    ("mri", "focal_cortical_dysplasia",               "scalar"),
    # -- EEG --
    ("eeg", "background",                             "scalar"),
    ("eeg", "ied_present",                            "scalar"),
]

assert len(CORE_FIELDS) == 24, f"CORE_FIELDS should be 24 not {len(CORE_FIELDS)}"


# ---------------------------------------------------------------------------
# Gold loader (auto-detects F-S wrapper vs Synth-v1 flat phenotype).
# ---------------------------------------------------------------------------


def _load_gold_dir(gold_dir: Path) -> dict[str, dict]:
    """Return ``{doc_id: phenotype_dict}``."""
    out: dict[str, dict] = {}
    for p in sorted(gold_dir.glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        # F-S silver has {"doc_id", "phenotype": {...}}
        if "phenotype" in j and isinstance(j["phenotype"], dict):
            ph = j["phenotype"]
            doc_id = j.get("doc_id") or p.stem
        else:
            ph = j
            doc_id = ph.get("document", {}).get("doc_id", p.stem)
            # LLM-generated silver may set document.doc_id to a placeholder;
            # prefer the file stem in that case.
            if doc_id in (None, "", "not_documented", "unknown"):
                doc_id = p.stem
            # If the doc_id doesn't match the filename (e.g., patient-level
            # target being reused for per-doc scoring), prefer the file stem.
            if doc_id != p.stem:
                doc_id = p.stem
        out[doc_id] = ph
    return out


def _load_predictions_dir(pred_dir: Path) -> dict[str, dict]:
    """Return ``{doc_id: phenotype_dict}`` for prediction JSONs."""
    out: dict[str, dict] = {}
    for p in sorted(pred_dir.glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        doc_id = j.get("document", {}).get("doc_id", p.stem)
        out[doc_id] = j
    return out


# ---------------------------------------------------------------------------
# Field-level extraction helpers
# ---------------------------------------------------------------------------


def _ev_value(mod: dict | None, field: str) -> Any:
    if not isinstance(mod, dict):
        return None
    ev = mod.get(field)
    if not isinstance(ev, dict):
        return None
    return ev.get("value")


def _multiset_ev(mod: dict | None, field: str) -> list[str]:
    """Turn ``list[Evidence[Enum|str]]`` into a lowercase list of values."""
    if not isinstance(mod, dict):
        return []
    lst = mod.get(field) or []
    out = []
    for ev in lst:
        if isinstance(ev, dict):
            v = ev.get("value")
            if v is not None:
                out.append(str(v).strip().lower())
    return out


def _canonicalize_drug_name(name: str) -> str:
    """Normalize a drug name so predictions and gold from different corpora
    (F-S vs synth-v1 vs our own emit convention) compare fairly.

    Uses the same mapping table as ``rules/fields/medication.py``.  Falls
    back to a collapsed alphabetic form for out-of-vocab names.
    """
    try:
        from rules.fields.medication import canonicalize_drug_name  # type: ignore
        return canonicalize_drug_name(name)
    except Exception:
        import re as _re
        return _re.sub(r"[\s\-_]+", "", (name or "").strip().lower())


def _multiset_med(mod: dict | None, field: str) -> list[str]:
    """Extract generic_name from a list of Evidence[Medication]."""
    if not isinstance(mod, dict):
        return []
    lst = mod.get(field) or []
    out = []
    for ev in lst:
        if isinstance(ev, dict):
            v = ev.get("value")
            if isinstance(v, dict):
                name = v.get("generic_name")
                if name:
                    out.append(_canonicalize_drug_name(str(name)))
    return out


def _multiset_surgery(mod: dict | None, field: str) -> list[str]:
    if not isinstance(mod, dict):
        return []
    out = []
    for ev in mod.get(field) or []:
        if isinstance(ev, dict):
            v = ev.get("value")
            if isinstance(v, dict):
                proc = v.get("procedure")
                if proc:
                    out.append(str(proc).strip().lower())
    return out


def _multiset_ndt(mod: dict | None, field: str) -> list[str]:
    if not isinstance(mod, dict):
        return []
    out = []
    for ev in mod.get(field) or []:
        if isinstance(ev, dict):
            v = ev.get("value")
            if isinstance(v, dict):
                th = v.get("therapy")
                if th:
                    out.append(str(th).strip().lower())
    return out


def _seizfreq(mod: dict | None) -> dict:
    """Return normalised {period, count_min, count_max, seizure_free}."""
    ev = (mod or {}).get("seizure_frequency") or {}
    if not isinstance(ev, dict):
        return {"period": None, "count_min": None, "count_max": None,
                "seizure_free": None}
    v = ev.get("value")
    if not isinstance(v, dict):
        return {"period": None, "count_min": None, "count_max": None,
                "seizure_free": None}
    period = v.get("period")
    if period is not None:
        period = str(period).strip().lower()
        if period == "unspecified":
            period = None  # noise
    return {
        "period": period,
        "count_min": v.get("count_min"),
        "count_max": v.get("count_max"),
        "seizure_free": v.get("seizure_free"),
    }


# ---------------------------------------------------------------------------
# Scoring primitives — return (tp, fp, fn) per doc or None if gold missing.
# ---------------------------------------------------------------------------


def _score_scalar(pred, gold) -> tuple[int, int, int] | None:
    """Simple scalar equality. ``None`` gold → no contribution."""
    if gold is None:
        return None
    if pred is None:
        return (0, 0, 1)  # FN
    if str(pred).strip().lower() == str(gold).strip().lower():
        return (1, 0, 0)
    return (0, 1, 1)


def _score_scalar_str_present(pred, gold) -> tuple[int, int, int] | None:
    """For free-text scalars (semiology_text), score presence only:
    gold non-null + pred non-null → HIT (no lexical overlap check)."""
    if gold is None:
        return None
    if pred is None or (isinstance(pred, str) and not pred.strip()):
        return (0, 0, 1)
    return (1, 0, 0)


def _score_float_tol(pred, gold, tol: float = 1.0) -> tuple[int, int, int] | None:
    if gold is None:
        return None
    if pred is None:
        return (0, 0, 1)
    try:
        return (1, 0, 0) if abs(float(pred) - float(gold)) <= tol else (0, 1, 1)
    except (ValueError, TypeError):
        return (0, 1, 1)


def _score_multiset(pred_items: list[str],
                    gold_items: list[str]) -> tuple[int, int, int] | None:
    if not gold_items:
        return None
    p = Counter(pred_items or [])
    g = Counter(gold_items or [])
    tp = sum((p & g).values())
    fp = sum((p - g).values())
    fn = sum((g - p).values())
    return (tp, fp, fn)


def _score_seizfreq(pred: dict, gold: dict) -> dict[str, tuple[int, int, int] | None]:
    """Return per-subfield score dict for seizure_frequency."""
    out = {}
    out["seizure_frequency.period"] = _score_scalar(pred["period"], gold["period"])
    out["seizure_frequency.count_min"] = _score_float_tol(
        pred["count_min"], gold["count_min"], tol=0.0,
    )
    out["seizure_frequency.count_max"] = _score_float_tol(
        pred["count_max"], gold["count_max"], tol=0.0,
    )
    out["seizure_frequency.seizure_free"] = _score_scalar(
        pred["seizure_free"], gold["seizure_free"],
    )
    return out


# ---------------------------------------------------------------------------
# Full per-doc scoring
# ---------------------------------------------------------------------------


def _score_one_doc(pred_ph: dict, gold_ph: dict,
                   only_populated: bool = True,
                   ) -> dict[str, tuple[int, int, int]]:
    """Return dict {field_path: (tp,fp,fn)} for one doc.

    ``only_populated=True`` drops fields for which the gold is None → the
    doc doesn't contribute to that field's F1 (standard convention).
    """
    scores: dict[str, tuple[int, int, int]] = {}

    def _put(name: str, s: tuple[int, int, int] | None):
        if s is None and only_populated:
            return
        if s is None:
            s = (0, 0, 0)
        scores[name] = s

    for module, field, kind in CORE_FIELDS:
        pmod = pred_ph.get(module) or {}
        gmod = gold_ph.get(module) or {}
        fp = f"{module}.{field}"

        if kind == "scalar":
            g = _ev_value(gmod, field)
            p = _ev_value(pmod, field)
            _put(fp, _score_scalar(p, g))
        elif kind == "scalar_str_present":
            g = _ev_value(gmod, field)
            p = _ev_value(pmod, field)
            _put(fp, _score_scalar_str_present(p, g))
        elif kind == "float_tol1":
            g = _ev_value(gmod, field)
            p = _ev_value(pmod, field)
            _put(fp, _score_float_tol(p, g, tol=1.0))
        elif kind == "multiset":
            g_items = _multiset_ev(gmod, field)
            p_items = _multiset_ev(pmod, field)
            _put(fp, _score_multiset(p_items, g_items))
        elif kind == "med_multiset":
            g_items = _multiset_med(gmod, field)
            p_items = _multiset_med(pmod, field)
            _put(fp, _score_multiset(p_items, g_items))
        elif kind == "surgery_multiset":
            g_items = _multiset_surgery(gmod, field)
            p_items = _multiset_surgery(pmod, field)
            _put(fp, _score_multiset(p_items, g_items))
        elif kind == "ndt_multiset":
            g_items = _multiset_ndt(gmod, field)
            p_items = _multiset_ndt(pmod, field)
            _put(fp, _score_multiset(p_items, g_items))
        elif kind == "seizfreq":
            g_sf = _seizfreq(gmod)
            p_sf = _seizfreq(pmod)
            for sf_name, s in _score_seizfreq(p_sf, g_sf).items():
                _put(f"{module}.{sf_name}", s)
        else:  # pragma: no cover
            raise ValueError(f"unknown kind: {kind}")

    return scores


# ---------------------------------------------------------------------------
# Aggregate reporting
# ---------------------------------------------------------------------------


def _f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return round(p, 4), round(r, 4), round(f1, 4)


def _percentile(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    xs = sorted(vals)
    idx = int(round(q * (len(xs) - 1)))
    return xs[idx]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True,
                    choices=["fs_test_40", "synth_v1_eval_100", "mtsamples_neuro_10", "synth_v2_eval_100"])
    ap.add_argument("--predictions-dir", required=True)
    ap.add_argument("--gold-dir", required=True)
    ap.add_argument("--out-csv", required=True,
                    help="Per-field long-form CSV output path.")
    ap.add_argument("--only-populated-fields", type=lambda s: s.lower() != "false",
                    default=True,
                    help="Restrict to fields where gold is non-null (default True).")
    args = ap.parse_args(argv)

    pred_dir = Path(args.predictions_dir)
    gold_dir = Path(args.gold_dir)
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    preds = _load_predictions_dir(pred_dir)
    gold = _load_gold_dir(gold_dir)

    # For synth_v1: gold key is P000505_progress_note, pred is same.
    # For fs_test_40: pred = EA0161, gold = EA0161 (silver has EA0001-200; restrict to 161-200).
    if args.corpus == "fs_test_40":
        holdout = {f"EA{i:04d}" for i in range(161, 201)}
        doc_ids = sorted([d for d in preds if d in holdout and d in gold])
    else:
        doc_ids = sorted([d for d in preds if d in gold])

    print(f"[score] Corpus={args.corpus}  preds={len(preds)}  "
          f"gold={len(gold)}  scored={len(doc_ids)}", flush=True)
    if not doc_ids:
        print("[score] No overlap between predictions and gold. Aborting.",
              file=sys.stderr)
        return 2

    # per-field aggregate: field → (tp, fp, fn); also n_gold_docs (# docs
    # where this field contributed).
    per_field: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # tp, fp, fn, n
    per_doc_f1: dict[str, float] = {}
    per_doc_rows: list[dict] = []

    for doc_id in doc_ids:
        s = _score_one_doc(preds[doc_id], gold[doc_id],
                           only_populated=args.only_populated_fields)
        doc_tp = doc_fp = doc_fn = 0
        for field, (tp, fp, fn) in s.items():
            per_field[field][0] += tp
            per_field[field][1] += fp
            per_field[field][2] += fn
            per_field[field][3] += 1
            doc_tp += tp; doc_fp += fp; doc_fn += fn
        p, r, f1 = _f1(doc_tp, doc_fp, doc_fn)
        per_doc_f1[doc_id] = f1
        per_doc_rows.append({
            "doc_id": doc_id, "tp": doc_tp, "fp": doc_fp, "fn": doc_fn,
            "precision": p, "recall": r, "f1": f1,
        })

    # Micro-F1 (sum tp/fp/fn across all fields, all docs).
    tot_tp = sum(v[0] for v in per_field.values())
    tot_fp = sum(v[1] for v in per_field.values())
    tot_fn = sum(v[2] for v in per_field.values())
    micro_p, micro_r, micro_f1 = _f1(tot_tp, tot_fp, tot_fn)

    # Macro-F1 (mean of per-field F1 across all fields that saw ≥ 1 gold doc).
    per_field_rows = []
    macro_vals = []
    for field, (tp, fp, fn, n) in sorted(per_field.items()):
        p, r, f1 = _f1(tp, fp, fn)
        per_field_rows.append({
            "field": field, "n_docs": n, "tp": tp, "fp": fp, "fn": fn,
            "precision": p, "recall": r, "f1": f1,
        })
        macro_vals.append(f1)
    macro_f1 = round(sum(macro_vals) / len(macro_vals), 4) if macro_vals else 0.0

    # ------------------------------------------------------------------
    # CSVs
    # ------------------------------------------------------------------
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(per_field_rows[0].keys()))
        w.writeheader()
        for r in per_field_rows:
            w.writerow(r)

    perdoc_csv = out_csv.with_suffix(".perdoc.csv")
    with perdoc_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(per_doc_rows[0].keys()))
        w.writeheader()
        for r in per_doc_rows:
            w.writerow(r)

    # ------------------------------------------------------------------
    # Summary markdown
    # ------------------------------------------------------------------
    doc_f1_vals = sorted(per_doc_f1.values())
    p25 = _percentile(doc_f1_vals, 0.25)
    med = _percentile(doc_f1_vals, 0.50)
    p75 = _percentile(doc_f1_vals, 0.75)

    sorted_fields = sorted(per_field_rows, key=lambda r: -r["f1"])
    top3 = sorted_fields[:3]
    bot3 = [r for r in sorted_fields if r["n_docs"] > 0][-3:]

    lines = [
        f"## MedCAT+Rules (arm B1') — {args.corpus}\n",
        f"*Generated by `scripts/score_medcat_vs_gold.py`.*\n",
        f"* Docs scored: **{len(doc_ids)}**",
        f"* Overall micro-F1: **{micro_f1:.4f}** "
        f"(P={micro_p:.4f} R={micro_r:.4f})",
        f"* Overall macro-F1: **{macro_f1:.4f}**",
        f"* Per-doc F1 distribution: median={med:.3f} "
        f"p25={p25:.3f} p75={p75:.3f}",
        "",
        "### Per-field breakdown (24 core fields; some absent from this "
        "corpus' gold)\n",
        "| field | n_docs | TP | FP | FN | P | R | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in per_field_rows:
        lines.append(
            f"| `{r['field']}` | {r['n_docs']} | {r['tp']} | {r['fp']} | "
            f"{r['fn']} | {r['precision']:.3f} | {r['recall']:.3f} | "
            f"{r['f1']:.3f} |"
        )

    lines += [
        "",
        "### Top-3 best-performing fields",
    ]
    for r in top3:
        lines.append(f"* `{r['field']}` — F1={r['f1']:.3f} (n={r['n_docs']})")
    lines += [
        "",
        "### Bottom-3 worst-performing fields (n_docs>0)",
    ]
    for r in bot3:
        lines.append(f"* `{r['field']}` — F1={r['f1']:.3f} (n={r['n_docs']})")

    out_md = out_csv.with_suffix(".summary.md")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # Console
    # ------------------------------------------------------------------
    print()
    print(f"MICRO-F1: {micro_f1:.4f}   MACRO-F1: {macro_f1:.4f}")
    print(f"Per-doc F1: median={med:.3f}  p25={p25:.3f}  p75={p75:.3f}\n")
    print(f"{'field':<50} {'n':>4} {'P':>6} {'R':>6} {'F1':>6}")
    print("-" * 78)
    for r in per_field_rows:
        print(f"{r['field']:<50} {r['n_docs']:>4} "
              f"{r['precision']:>6.3f} {r['recall']:>6.3f} {r['f1']:>6.3f}")
    print(f"\nWrote {out_csv}")
    print(f"Wrote {perdoc_csv}")
    print(f"Wrote {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
