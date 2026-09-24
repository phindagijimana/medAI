#!/usr/bin/env python3
"""Downstream cohort-question demonstration.

Answers three clinically meaningful joint queries on the Fonferko-Shadrach
n=200 letters, computed once from Fonferko native gold and once from
MedAI-EPI extractions (M1, the strongest LLM arm on §Table 4b-gold), then
reports the delta. Demonstrates that the extracted phenotypes support the
same cohort-level inferences the gold labels do — the higher-order claim
the paper's "utility" story rests on.

Questions:
    Q1  Age-at-onset distribution: median [IQR] across all patients where
        an onset age is reported.
    Q2  Polytherapy prevalence: fraction of patients on ≥ 2 concurrent ASMs.
    Q3  Temporal-lobe involvement: fraction of patients whose diagnosis
        mentions "temporal lobe" (structural or localizing anatomy).

For each Q, we compute the answer three ways:
    (a) From F-S native gold (reference)
    (b) From MedAI-EPI M1 extractions (smart-repaired, one manifest per doc)
    (c) From MedAI-EPI silver labels (for comparison to Table 4b-silver)

Bootstrap 95% CIs on each metric are computed at the document level
(1000 resamples, seed=0).

Writes:
    eval/results/cohort_demo.md
    eval/results/cohort_demo.json
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics
import sys
from collections import defaultdict
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
SILVER = REPO / "data" / "fonferko_shadrach_2024" / "silver_labels_v0_2_1"
OUT = REPO / "eval" / "results"


# ---------------------------------------------------------------------------
# Load F-S native gold — build per-doc dicts of the three query answers.
# ---------------------------------------------------------------------------


_TL_RE = re.compile(r"temporal[- ]lobe|hippocamp|mesial temporal", re.I)


def _load_fs_gold_per_doc():
    """Return {doc_id: {onset_years, current_asm_names, mentions_temporal}}"""
    out = {}
    for f in sorted(FS_GOLD_DIR.glob("*.json")):
        entities = json.loads(f.read_text(encoding="utf-8"))
        d = {
            "onset_years": None,
            "current_asm_names": set(),
            "mentions_temporal": False,
        }
        for ent in entities:
            e = ent.get("entity")
            a = ent.get("attributes", {}) or {}
            txt = (ent.get("text") or "").replace("-", " ").lower()
            if e == "Prescription":
                drug = (a.get("DrugName") or "").strip().lower()
                if drug:
                    d["current_asm_names"].add(drug)
            elif e == "Onset":
                age = a.get("Age") or a.get("AgeLower")
                unit = (a.get("AgeUnit") or "years").lower()
                if age and d["onset_years"] is None:
                    try:
                        v = float(age)
                        if unit.startswith("month"):
                            v = v / 12.0
                        d["onset_years"] = v
                    except (ValueError, TypeError):
                        pass
            elif e == "Diagnosis":
                if _TL_RE.search(txt):
                    d["mentions_temporal"] = True
        out[f.stem] = d
    return out


# ---------------------------------------------------------------------------
# Load M1 extractions from manifests (medication + clinical_seizure only)
# ---------------------------------------------------------------------------


MODULE_CLASSES = {
    "clinical_seizure": ClinicalSeizureModule,
    "medication": MedicationModule,
}


def _load_m1_extractions_per_doc():
    """Return {doc_id: {onset_years, current_asm_names, mentions_temporal}}
    derived from M1 manifests, smart-repaired."""
    per_doc = defaultdict(lambda: {
        "onset_years": None,
        "current_asm_names": set(),
        "mentions_temporal": False,
    })
    seen = set()
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
        if module_name not in MODULE_CLASSES or version != "v1" or arm != "M1":
            continue
        doc_id = m.get("source_doc_id", "")
        key = (doc_id, module_name)
        if key in seen:
            continue
        seen.add(key)

        doc = DocumentMetadata(
            doc_id=doc_id, doc_type=DocumentType.PROGRESS_NOTE,
            doc_date=date(2024, 1, 1), patient_id=doc_id,
            icd10cm_codes=[], snomed_ct_codes=[],
        )
        validated, _p, _e = try_smart_repair(
            m.get("raw_response", ""), MODULE_CLASSES[module_name], doc,
        )
        if validated is None:
            continue
        d = validated.model_dump(mode="json")
        if module_name == "medication":
            for ev in (d.get("current_asms") or []):
                v = ev.get("value") if isinstance(ev, dict) else None
                if isinstance(v, dict):
                    nm = (v.get("generic_name") or "").strip().lower()
                    if nm:
                        per_doc[doc_id]["current_asm_names"].add(nm)
        elif module_name == "clinical_seizure":
            ev = d.get("age_at_onset_years") or {}
            v = ev.get("value") if isinstance(ev, dict) else None
            if isinstance(v, (int, float)) and per_doc[doc_id]["onset_years"] is None:
                per_doc[doc_id]["onset_years"] = float(v)
            for f_ in ("epilepsy_type", "predominant_seizure_type",
                       "semiology_text", "etiology_details_text"):
                ev = d.get(f_) or {}
                if isinstance(ev, dict):
                    t = ev.get("evidence_text") or ""
                    if isinstance(t, str) and _TL_RE.search(t):
                        per_doc[doc_id]["mentions_temporal"] = True
    return per_doc


# ---------------------------------------------------------------------------
# Load MedAI-EPI silver labels
# ---------------------------------------------------------------------------


def _load_silver_per_doc():
    out = {}
    for f in sorted(SILVER.glob("EA*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        phen = rec.get("phenotype", {})
        cs = phen.get("clinical_seizure") or {}
        med = phen.get("medication") or {}
        d = {
            "onset_years": None,
            "current_asm_names": set(),
            "mentions_temporal": False,
        }
        ev = cs.get("age_at_onset_years") or {}
        v = ev.get("value") if isinstance(ev, dict) else None
        if isinstance(v, (int, float)):
            d["onset_years"] = float(v)
        for evm in (med.get("current_asms") or []):
            val = evm.get("value") if isinstance(evm, dict) else None
            if isinstance(val, dict):
                nm = (val.get("generic_name") or "").strip().lower()
                if nm:
                    d["current_asm_names"].add(nm)
        for f_ in ("epilepsy_type", "predominant_seizure_type",
                   "semiology_text", "etiology_details_text"):
            ev = cs.get(f_) or {}
            if isinstance(ev, dict):
                t = ev.get("evidence_text") or ""
                if isinstance(t, str) and _TL_RE.search(t):
                    d["mentions_temporal"] = True
        out[rec["doc_id"]] = d
    return out


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def _median_iqr(values, n_resamples=1000, seed=0, alpha=0.05):
    """Return (median, q1, q3, ci_median_lo, ci_median_hi) with a bootstrap
    CI on the median."""
    vs = sorted(v for v in values if v is not None)
    if not vs:
        return (None, None, None, None, None)
    med = statistics.median(vs)
    q1 = vs[max(0, int(0.25 * len(vs)) - 1)]
    q3 = vs[min(len(vs) - 1, int(0.75 * len(vs)))]
    rng = random.Random(seed)
    n = len(vs)
    boots = []
    for _ in range(n_resamples):
        s = sorted(vs[rng.randrange(n)] for _ in range(n))
        boots.append(statistics.median(s))
    boots.sort()
    lo = boots[int(math.floor(alpha / 2 * n_resamples))]
    hi = boots[int(math.ceil((1 - alpha / 2) * n_resamples)) - 1]
    return (med, q1, q3, lo, hi)


def _rate_ci(flags, n_resamples=1000, seed=0, alpha=0.05):
    """Bootstrap 95% CI on the proportion of True flags."""
    if not flags:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(flags)
    rate = sum(flags) / n
    boots = []
    for _ in range(n_resamples):
        s = sum(flags[rng.randrange(n)] for _ in range(n))
        boots.append(s / n)
    boots.sort()
    lo = boots[int(math.floor(alpha / 2 * n_resamples))]
    hi = boots[int(math.ceil((1 - alpha / 2) * n_resamples)) - 1]
    return (rate, lo, hi)


def _q1_answer(per_doc):
    """Q1: age-at-onset median [IQR]."""
    ages = [d["onset_years"] for d in per_doc.values() if d["onset_years"] is not None]
    return _median_iqr(ages)


def _q2_answer(per_doc):
    """Q2: fraction of patients with ≥2 ASMs."""
    flags = [len(d["current_asm_names"]) >= 2 for d in per_doc.values()]
    return _rate_ci(flags), len(flags)


def _q3_answer(per_doc):
    """Q3: fraction of patients whose docs mention temporal-lobe involvement."""
    flags = [d["mentions_temporal"] for d in per_doc.values()]
    return _rate_ci(flags), len(flags)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    gold = _load_fs_gold_per_doc()
    m1 = _load_m1_extractions_per_doc()
    silver = _load_silver_per_doc()

    # Restrict all three to the same 200 F-S doc IDs.
    doc_ids = sorted(gold.keys())
    def _sub(d):
        return {did: d.get(did, {"onset_years": None, "current_asm_names": set(),
                                  "mentions_temporal": False}) for did in doc_ids}
    gold_s = _sub(gold)
    m1_s = _sub(m1)
    silver_s = _sub(silver)

    print(f"Cohort size: {len(doc_ids)} letters\n")

    rows = []

    # Q1: age-at-onset median [IQR]
    for src_name, per_doc in [("Gold (F-S)", gold_s),
                               ("MedAI-EPI M1", m1_s),
                               ("Silver", silver_s)]:
        med, q1, q3, lo, hi = _q1_answer(per_doc)
        n_reported = sum(1 for d in per_doc.values() if d["onset_years"] is not None)
        rows.append({
            "question": "Q1 age-at-onset median [IQR]",
            "source": src_name,
            "n_reported": n_reported,
            "n_total": len(per_doc),
            "median": med, "q1": q1, "q3": q3,
            "median_ci_lo": lo, "median_ci_hi": hi,
        })

    # Q2: fraction on ≥2 ASMs
    for src_name, per_doc in [("Gold (F-S)", gold_s),
                               ("MedAI-EPI M1", m1_s),
                               ("Silver", silver_s)]:
        (rate, lo, hi), n = _q2_answer(per_doc)
        rows.append({
            "question": "Q2 fraction ≥2 concurrent ASMs",
            "source": src_name,
            "rate": rate, "rate_ci_lo": lo, "rate_ci_hi": hi,
            "n": n,
        })

    # Q3: temporal-lobe involvement
    for src_name, per_doc in [("Gold (F-S)", gold_s),
                               ("MedAI-EPI M1", m1_s),
                               ("Silver", silver_s)]:
        (rate, lo, hi), n = _q3_answer(per_doc)
        rows.append({
            "question": "Q3 fraction with temporal-lobe involvement",
            "source": src_name,
            "rate": rate, "rate_ci_lo": lo, "rate_ci_hi": hi,
            "n": n,
        })

    # Print
    md = [
        "## Table 7. Cohort-question demonstration — extracted phenotypes support the same population inferences as F-S gold\n",
        "*Generated by `scripts/cohort_demo.py` on 200 Fonferko-Shadrach letters. "
        "MedAI-EPI M1 = few-shot Med42-8B, smart-repaired. Silver = derived from "
        "our v0.2.1 silver-labeling pipeline. CIs are patient-level bootstrap "
        "(1000 resamples, seed=0).*\n",
    ]

    # Q1
    md.append("**Q1 — Age-at-onset, median [IQR] (95% CI on median)**\n")
    md.append("| Source | n reported / n total | Median [IQR] | 95% CI on median |")
    md.append("|---|---:|---:|---|")
    for r in rows[:3]:
        if r["median"] is None:
            md.append(f"| {r['source']} | {r['n_reported']}/{r['n_total']} | — | — |")
        else:
            md.append(f"| {r['source']} | {r['n_reported']}/{r['n_total']} | "
                      f"{r['median']:.1f} [{r['q1']:.1f}–{r['q3']:.1f}] | "
                      f"[{r['median_ci_lo']:.1f}, {r['median_ci_hi']:.1f}] |")

    # Q2
    md.append("\n**Q2 — Fraction of patients on ≥ 2 concurrent ASMs (95% CI)**\n")
    md.append("| Source | n | Rate | 95% CI |")
    md.append("|---|---:|---:|---|")
    for r in rows[3:6]:
        md.append(f"| {r['source']} | {r['n']} | {r['rate']:.3f} | "
                  f"[{r['rate_ci_lo']:.3f}, {r['rate_ci_hi']:.3f}] |")

    # Q3
    md.append("\n**Q3 — Fraction with temporal-lobe involvement (95% CI)**\n")
    md.append("| Source | n | Rate | 95% CI |")
    md.append("|---|---:|---:|---|")
    for r in rows[6:9]:
        md.append(f"| {r['source']} | {r['n']} | {r['rate']:.3f} | "
                  f"[{r['rate_ci_lo']:.3f}, {r['rate_ci_hi']:.3f}] |")

    md_str = "\n".join(md) + "\n"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cohort_demo.md").write_text(md_str, encoding="utf-8")
    (OUT / "cohort_demo.json").write_text(json.dumps(rows, indent=2, default=str),
                                           encoding="utf-8")
    print(md_str)
    print(f"wrote → {OUT / 'cohort_demo.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
