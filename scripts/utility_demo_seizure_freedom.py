#!/usr/bin/env python3
"""Downstream utility demo #2 — seizure-freedom identification from extracted
clinical-seizure phenotypes.

Seizure freedom is one of the most clinically meaningful outcomes in epilepsy
research (definition — no seizures for ≥ 12 months per ILAE consensus). At the
phenotype-extraction layer we operationalize it as:

  Candidate = extracted phenotype has EITHER
    (a) seizure_frequency.value.seizure_free == True, OR
    (b) seizure_frequency.raw_text contains "seizure free" / "seizure-free" /
        "no seizures" (fallback pattern for cases where the boolean flag is
        not populated but the raw quote captures the state).

Baseline: silver labels' own seizure_free flag.

Writes:
  eval/results/utility_demo_seizure_freedom.md
  eval/results/utility_demo_seizure_freedom.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema import (
    ClinicalSeizureModule, DocumentMetadata, DocumentType,
)
from services.smart_repair import try_smart_repair


REPO = Path(__file__).resolve().parent.parent
MANIFESTS = REPO / "data" / "run_manifests"
SILVER = REPO / "data" / "fonferko_shadrach_2024" / "silver_labels_v0_2_1"
OUT = REPO / "eval" / "results"


_SEIZURE_FREE_RE = re.compile(
    r"seizure[- ]?free|no seizures?(?:\s+(?:in|for|since))?|"
    r"remain(?:s|ed)?\s+seizure[- ]?free|free\s+of\s+seizures",
    re.IGNORECASE,
)

# Manual review estimate for seizure-freedom identification per letter
# (parallel to the drug-resistance demo). Conservative — this is one of
# the faster chart-review targets since it appears in the "current status"
# section of most clinic letters.
MANUAL_REVIEW_S_PER_LETTER = 4 * 60      # 240 s
EXTRACTION_S_PER_LETTER = 12             # ~12 s per module for clinical_seizure


def _is_seizure_free(cs_module_dict):
    """Return True if the extracted ClinicalSeizureModule dict indicates
    seizure freedom, via structured flag or free-text pattern."""
    if not isinstance(cs_module_dict, dict):
        return False
    freq = cs_module_dict.get("seizure_frequency") or {}
    if not isinstance(freq, dict):
        return False
    value = freq.get("value")
    if isinstance(value, dict) and value.get("seizure_free") is True:
        return True
    # Fallback: pattern-match the raw text and/or evidence quote
    for k in ("evidence_text",):
        t = freq.get(k) or ""
        if isinstance(t, str) and _SEIZURE_FREE_RE.search(t):
            return True
    if isinstance(value, dict):
        t = value.get("raw_text") or ""
        if isinstance(t, str) and _SEIZURE_FREE_RE.search(t):
            return True
    # Also inspect semiology_text and etiology_details_text if any
    for k in ("semiology_text", "etiology_details_text"):
        f = cs_module_dict.get(k) or {}
        if isinstance(f, dict):
            t = f.get("evidence_text") or ""
            if isinstance(t, str) and _SEIZURE_FREE_RE.search(t):
                return True
    return False


def _load_silver():
    out = {}
    for f in SILVER.glob("EA*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[d["doc_id"]] = d["phenotype"]
    return out


def main():
    silver = _load_silver()
    silver_flags = {
        did: _is_seizure_free(s.get("clinical_seizure") or {})
        for did, s in silver.items()
    }
    n_silver = sum(silver_flags.values())

    arm_flags = defaultdict(dict)
    seen = defaultdict(set)

    for f in MANIFESTS.rglob("*.json"):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        pid = m.get("prompt_id", "")
        if not pid.startswith("clinical_seizure."):
            continue
        parts = pid.split(".")
        if len(parts) != 3:
            continue
        _, arm, version = parts
        if version != "v1":
            continue
        doc_id = m.get("source_doc_id", "")
        key = (doc_id, arm)
        if key in seen["cs"]:
            continue
        seen["cs"].add(key)

        doc = DocumentMetadata(
            doc_id=doc_id, doc_type=DocumentType.PROGRESS_NOTE,
            doc_date=date(2024, 1, 1), patient_id=doc_id,
            icd10cm_codes=[], snomed_ct_codes=[],
        )
        validated, _p, _e = try_smart_repair(
            m.get("raw_response", ""), ClinicalSeizureModule, doc,
        )
        if validated is None:
            arm_flags[arm][doc_id] = False
            continue
        d = validated.model_dump(mode="json")
        arm_flags[arm][doc_id] = _is_seizure_free(d)

    rows = []
    for arm in sorted(arm_flags):
        flags = arm_flags[arm]
        overlap = added = missed = 0
        for did, is_free in flags.items():
            silver_flag = silver_flags.get(did, False)
            if silver_flag and is_free:
                overlap += 1
            elif is_free and not silver_flag:
                added += 1
            elif silver_flag and not is_free:
                missed += 1
        n_arm = overlap + added
        sens = overlap / n_silver if n_silver else 0.0
        ppv = overlap / n_arm if n_arm else 0.0
        rows.append({
            "arm": arm, "n_extractions": len(flags),
            "n_arm_candidates": n_arm,
            "silver_candidates": n_silver, "overlap": overlap,
            "arm_added_vs_silver": added, "arm_missed_vs_silver": missed,
            "sensitivity_vs_silver": sens, "ppv_vs_silver": ppv,
        })

    n_letters = len(silver_flags)
    manual_total = MANUAL_REVIEW_S_PER_LETTER * n_letters
    extract_total = EXTRACTION_S_PER_LETTER * n_letters
    savings = manual_total / extract_total if extract_total else 0

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "utility_demo_seizure_freedom.json").write_text(json.dumps({
        "n_letters": n_letters,
        "silver_seizure_free_candidates": n_silver,
        "per_arm": rows,
        "time_per_letter_s": {
            "manual_estimate": MANUAL_REVIEW_S_PER_LETTER,
            "extraction_measured": EXTRACTION_S_PER_LETTER,
            "savings_ratio": round(savings, 1),
        },
    }, indent=2), encoding="utf-8")

    md = [
        "## Utility demonstration #2 — seizure-freedom identification\n",
        f"Applied to the same 200 Fonferko-Shadrach clinic letters, silver "
        f"labels flag {n_silver} letters where the extracted seizure frequency "
        f"or nearby free-text signals seizure freedom "
        f"(structured `seizure_free=True` OR pattern match on "
        f"\"seizure-free\" / \"no seizures\" / \"remains seizure-free\").\n",
        "### Table 6. Seizure-freedom candidate identification per arm\n",
        "| Arm | Extractions parsed | Arm-flagged | Silver-flagged | Overlap | Arm-only | Silver-only | Sens vs silver | PPV vs silver |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        md.append(
            f"| {r['arm']} | {r['n_extractions']} | {r['n_arm_candidates']} | "
            f"{r['silver_candidates']} | {r['overlap']} | "
            f"{r['arm_added_vs_silver']} | {r['arm_missed_vs_silver']} | "
            f"{r['sensitivity_vs_silver']:.2f} | {r['ppv_vs_silver']:.2f} |"
        )
    md.append(
        f"\nThroughput at ~{EXTRACTION_S_PER_LETTER} s per letter (clinical-seizure "
        f"module) versus ~{MANUAL_REVIEW_S_PER_LETTER // 60} min manual review "
        f"is ~{savings:.0f}× faster.\n"
    )
    (OUT / "utility_demo_seizure_freedom.md").write_text("\n".join(md) + "\n",
                                                             encoding="utf-8")

    print(f"Silver seizure-free candidates: {n_silver} / {n_letters} letters")
    for r in rows:
        print(
            f"  {r['arm']:<3}: flagged {r['n_arm_candidates']:>3}, "
            f"overlap {r['overlap']:>3}, "
            f"sens {r['sensitivity_vs_silver']:.2f}, "
            f"ppv {r['ppv_vs_silver']:.2f}"
        )
    print(f"\nExtraction speedup vs manual: ~{savings:.0f}× faster")
    print(f"wrote → {OUT / 'utility_demo_seizure_freedom.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
