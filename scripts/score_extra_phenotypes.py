#!/usr/bin/env python3
"""Accuracy of the EpExtra specialist (rules; no LLM, CPU) on the phenotypes beyond the five core ones,
wherever the synthetic reference record says something.

Reference: the synthetic patient target files.  Document: all of one patient's notes joined.  Prediction:
the specialist's claims (no LLM).  Only these phenotypes have a reference to compare with:

    etiology_category, drug_resistance          (30 patients)
    mri_normal, hippocampal_sclerosis,
    focal_cortical_dysplasia, mri_findings      (the 17 patients who have an MRI report)

The reference has no entries for detailed EEG findings, semiology, focal onset features or surgery, so nothing
can be scored for them here (prior / failed / rescue drugs, etiology specifics and coarse EEG are scored by
scripts/score_plan_phenotypes.py, which reads the generation plans and the F-S gold).  For surgery history the script only counts patients
where the rules report a procedure although the reference lists none (a false-alarm count, with examples).

    venv-medcat/bin/python scripts/score_extra_phenotypes.py            # -> eval/results/leo_extra_phenotypes.{json,md}

Synthetic data only: these are not accuracy on real notes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

SCALARS = {"etiology_category": "clinical_seizure.etiology_category",
           "drug_resistance": "medication.drug_resistance_status"}
BOOLS = {"mri_normal": ("mri.overall_normal", "mri", "overall_normal"),
         "hippocampal_sclerosis": ("mri.hippocampal_sclerosis", "mri", "hippocampal_sclerosis"),
         "focal_cortical_dysplasia": ("mri.focal_cortical_dysplasia", "mri", "focal_cortical_dysplasia")}


def _gold(t: dict, mod: str, key: str):
    x = (t.get(mod) or {}).get(key) or {}
    if not isinstance(x, dict) or x.get("certainty") == "not_documented" or x.get("value") is None:
        return None
    return x["value"]


def _gold_findings(t: dict) -> set[str] | None:
    items = (t.get("mri") or {}).get("findings")
    if not items or _gold(t, "mri", "overall_normal") is None:
        return None
    return {str(i.get("value")) for i in items if isinstance(i, dict) and i.get("value")}


def _claims(claims, path: str, asserted_only: bool = False) -> list:
    """Values of the claims at ``path``; ``asserted_only`` drops hedged ones (assertion not 'present')."""
    out = []
    for c in claims:
        if c.field_path == path and c.validator_verdict.value != "reject":
            if asserted_only and c.assertion.value != "present":
                continue
            v = c.value
            out.append(v.model_dump() if hasattr(v, "model_dump") else v)
    return out


def _mode(vals: list):
    if not vals:
        return None
    top = Counter(map(repr, vals)).most_common(1)[0][0]
    return next(v for v in vals if repr(v) == top)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="eval/results/leo_extra_phenotypes")
    ap.add_argument("--patients", type=int, default=0)
    args = ap.parse_args(argv)

    from scripts.leo_gpu_validate import patient_documents
    from services import synth_eval as se
    from services.leo_runtime import LeoRuntime

    rt = LeoRuntime(backend=None, use_llm=False)
    docs = patient_documents(args.patients)
    S = {k: Counter() for k in (*SCALARS, *BOOLS)}
    conf: dict[str, Counter] = {k: Counter() for k in SCALARS}
    tp = fp = fn = 0
    ex_surgery, wrong = [], {k: [] for k in (*SCALARS, *BOOLS)}
    surg_with, surg_n = 0, 0
    for i, (p, corpus, visits, text) in enumerate(docs, 1):
        t = json.loads(se.target_path(corpus, p).read_text(encoding="utf-8"))
        _, claims = rt.pipeline.extract(text, document_id=p, doc_date="2024-01-01", return_claims=True)
        for name, path in SCALARS.items():
            mod, key = path.split(".")
            g = _gold(t, mod, key)
            vals = _claims(claims, path)
            pred = _mode(vals)
            s = S[name]
            if g is None:
                continue
            s["n"] += 1
            s["found"] += pred is not None
            ok = pred is not None and pred == g
            s["correct"] += ok
            conf[name][(g, pred if pred is not None else "none")] += 1
            if not ok:
                wrong[name].append({"patient": p, "reference": g, "rules": pred})
        for name, (path, mod, key) in BOOLS.items():
            g = _gold(t, mod, key)
            if g is None:
                continue
            vals = [v for v in _claims(claims, path, asserted_only=True) if isinstance(v, bool)]
            hedged = [v for v in _claims(claims, path) if isinstance(v, bool)]
            pred = True if any(vals) else (False if vals else None)
            s = S[name]
            s["n"] += 1
            s["found"] += pred is not None
            s["hedged_only"] += (pred is None and bool(hedged))
            s["correct"] += pred == g
            s["ref_true"] += bool(g)
            s["tp"] += (pred is True and g is True)
            s["fp"] += (pred is True and g is False)
            s["fn"] += (pred is not True and g is True)
            if pred is not None and pred != g:
                wrong[name].append({"patient": p, "reference": g, "rules": pred})
        gf = _gold_findings(t)
        if gf is not None:
            pf = {str(v) for v in _claims(claims, "mri.findings")}
            tp += len(gf & pf)
            fp += len(pf - gf)
            fn += len(gf - pf)
        sc = [c for c in claims if c.field_path == "medication.surgery_history" and c.validator_verdict.value != "reject"]
        if not (t.get("medication") or {}).get("surgery_history"):
            surg_n += 1
            if sc:
                surg_with += 1
                if len(ex_surgery) < 5:
                    ex_surgery.append({"patient": p, "n_claims": len(sc),
                                       "evidence": [getattr(c.mention, "text", "")[:80] for c in sc[:3]]})
        print(f"[{i}/{len(docs)}] {p}", flush=True)

    def rate(a, b):
        return round(a / b, 3) if b else None
    out = {"n_patients": len(docs), "document": "one patient's notes joined", "system": "EpExtra specialist, no LLM",
           "scalars": {k: {**dict(S[k]), "accuracy": rate(S[k]["correct"], S[k]["n"]),
                           "accuracy_when_answered": rate(S[k]["correct"], S[k]["found"]),
                           "confusion": {f"{a} -> {b}": n for (a, b), n in conf[k].items()},
                           "wrong": wrong[k]} for k in SCALARS},
           "bools": {k: {**dict(S[k]), "accuracy": rate(S[k]["correct"], S[k]["n"]),
                         "accuracy_when_answered": rate(S[k]["correct"], S[k]["found"]),
                         "precision_true": rate(S[k]["tp"], S[k]["tp"] + S[k]["fp"]),
                         "recall_true": rate(S[k]["tp"], S[k]["tp"] + S[k]["fn"]), "wrong": wrong[k]} for k in BOOLS},
           "mri_findings": {"tp": tp, "fp": fp, "fn": fn, "precision": rate(tp, tp + fp), "recall": rate(tp, tp + fn),
                            "f1": rate(2 * tp, 2 * tp + fp + fn)},
           "surgery_history": {"patients_with_no_reference_surgery": surg_n, "patients_where_rules_report_surgery": surg_with,
                               "examples": ex_surgery},
           "not_scoreable": ["EEG study type, background, ictal onset (the F-S letters give only normal/abnormal)",
                             "seizure semiology", "focal motor / non-motor onset", "surgery history (reference lists none)"],
           "scored_elsewhere": "prior/failed/rescue drugs, etiology specifics and coarse EEG: scripts/score_plan_phenotypes.py"}
    path = REPO / f"{args.out}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    md = [f"# Specialist on the extra phenotypes (synthetic, {len(docs)} patients, notes joined, no LLM)\n",
          "| Phenotype | Reference present | Rules gave a value | Correct | Accuracy (all) | Accuracy (when answered) |",
          "|---|---|---|---|---|---|"]
    for k, v in {**out["scalars"], **out["bools"]}.items():
        md.append(f"| {k} | {v.get('n', 0)} | {v.get('found', 0)} | {v.get('correct', 0)} | {v['accuracy']} | "
                  f"{v['accuracy_when_answered']} |")
    md += ["", "A yes/no finding the note never mentions gets no value from the rules (absence is not inferred), while the "
           "reference says False; those count against 'all' and not against 'when answered'. Hedged findings are not counted "
           "as asserted."]
    m = out["mri_findings"]
    md += ["", f"MRI findings (list, micro): precision {m['precision']}, recall {m['recall']}, F1 {m['f1']}",
           f"Surgery: rules report a procedure for {surg_with} of {surg_n} patients whose reference lists none.", "",
           "Not scoreable (the reference has no entry): " + "; ".join(out["not_scoreable"]) + ".",
           "Prior / failed / rescue drugs, etiology specifics and coarse EEG are scored by scripts/score_plan_phenotypes.py "
           "(eval/results/leo_plan_phenotypes.md)."]
    (REPO / f"{args.out}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
