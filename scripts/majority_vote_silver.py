#!/usr/bin/env python3
"""Merge multiple per-tier GPT silver labels into a majority-vote silver.

Purpose: reduce single-labeler noise on MTSamples (or any corpus without
clinician gold) by aggregating N independent GPT extractions per doc.

Inputs are N sibling directories of per-doc silver JSONs, e.g.:

    data/eval_corpora/mtsamples_neuro_preprocessed/silver_per_doc/          (terra)
    data/eval_corpora/mtsamples_neuro_preprocessed/silver_per_doc_luna/
    data/eval_corpora/mtsamples_neuro_preprocessed/silver_per_doc_sol/

Aggregation rules per field:

  Scalar values (str/int/float/bool/enum):
    Mode across tiers, requiring ≥ N/2 (rounded up) agreement.
    Ties → the value the "primary" tier (first --tier arg) provided.
    All disagree → `not_documented` (or None).

  List of Evidence[T] (current_asms, other_seizure_types):
    Keep an item if it appears in ≥ N/2 tier lists.  For medications:
    match on canonicalized generic_name; for seizure types on the enum
    value; for arbitrary strings on lowercased str.

  Evidence[T] scalar wrappers:
    Independent mode-vote on `.value` and `.certainty` and
    `.temporal_status`.  `.evidence_text` taken from the primary tier.

Outputs a merged silver dir + an agreement report CSV:

    data/eval_corpora/mtsamples_neuro_preprocessed/silver_per_doc_majority/
    eval/results/mtsamples_silver_agreement.csv

Usage:

    venv-medcat/bin/python scripts/majority_vote_silver.py \\
        --corpus-root data/eval_corpora/mtsamples_neuro_preprocessed \\
        --tiers silver_per_doc,silver_per_doc_luna,silver_per_doc_sol \\
        --tier-names terra,luna,sol \\
        --out silver_per_doc_majority \\
        --agreement-csv eval/results/mtsamples_silver_agreement.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


# ─── Field enumeration ────────────────────────────────────────────────────
# We flatten the v0.2.1 phenotype into a set of dotted-path fields.  Two
# categories are treated differently:
#
#  * SCALAR fields  → Evidence[T] wrappers over primitives.  Mode-vote
#    on .value; also record whether all tiers agreed.
#  * LIST fields    → list of Evidence[T] of dicts.  Item-level ≥N/2
#    vote on a canonical identifier (generic_name / value etc.).

SCALAR_EVIDENCE_FIELDS = [
    "clinical_seizure.epilepsy_type.value",
    "clinical_seizure.predominant_seizure_type.value",
    "clinical_seizure.age_at_onset_years.value",
    "clinical_seizure.etiology_category.value",
    "clinical_seizure.awareness.value",
    "clinical_seizure.focal_motor_onset.value",
    "clinical_seizure.focal_nonmotor_onset.value",
    "clinical_seizure.seizure_frequency.count_min.value",
    "clinical_seizure.seizure_frequency.count_max.value",
    "clinical_seizure.seizure_frequency.period.value",
    "clinical_seizure.seizure_frequency.seizure_free.value",
    "clinical_seizure.status_epilepticus_history.value",
    "eeg.background.value",
    "eeg.ied_present.value",
    "medication.drug_resistance_status.value",
    "mri.overall_normal.value",
]

LIST_FIELDS = {
    # (module, list_field) → key extractor
    ("medication", "current_asms"):     lambda ev: (ev.get("value") or {}).get("generic_name", "").lower(),
    ("medication", "prior_asms"):       lambda ev: (ev.get("value") or {}).get("generic_name", "").lower(),
    ("medication", "failed_asms"):      lambda ev: (ev.get("value") or {}).get("generic_name", "").lower(),
    ("clinical_seizure", "other_seizure_types"): lambda ev: str(ev.get("value", "")).lower(),
    ("mri", "findings"):                lambda ev: str(ev.get("value", "")).lower(),
    ("eeg", "ictal_events"):            lambda ev: str(ev.get("value", "")).lower(),
}


def _get_by_path(d, path):
    x = d
    for p in path.split("."):
        if not isinstance(x, dict):
            return None
        x = x.get(p)
        if x is None:
            return None
    return x


def _set_by_path(d, path, value):
    parts = path.split(".")
    x = d
    for p in parts[:-1]:
        if p not in x or not isinstance(x[p], dict):
            x[p] = {}
        x = x[p]
    x[parts[-1]] = value


# ─── Voting helpers ───────────────────────────────────────────────────────

def _mode_with_quorum(values, quorum, primary_tier_idx=0):
    """Return (winning_value, agreement_str). None → not_documented / disagree."""
    non_null = [v for v in values if v not in (None, "", "not_documented")]
    if not non_null:
        return None, "all_null"
    c = Counter(non_null)
    top_val, top_count = c.most_common(1)[0]
    if top_count >= quorum:
        # Which tiers voted for the winner?
        agree_idx = [i for i, v in enumerate(values) if v == top_val]
        return top_val, f"{top_count}/{len(values)}_agree(tiers={agree_idx})"
    # Tie / no quorum → keep primary's value if any, else None
    primary_val = values[primary_tier_idx] if primary_tier_idx < len(values) else None
    if primary_val in (None, "", "not_documented"):
        return None, f"disagree(no_quorum)"
    return primary_val, f"disagree(fallback_to_primary)"


def _multiset_vote(lists, key_fn, quorum):
    """Union of items across tier lists, keeping only those in ≥ quorum tiers.

    Returns list of Evidence[T] dicts (from whichever tier first mentioned the item).
    """
    from collections import defaultdict
    presence = defaultdict(list)  # key -> list of (tier_idx, evidence_dict)
    for tier_idx, lst in enumerate(lists or []):
        if not isinstance(lst, list):
            continue
        seen_this_tier = set()
        for ev in lst:
            if not isinstance(ev, dict):
                continue
            k = key_fn(ev)
            if not k or k in seen_this_tier:
                continue
            seen_this_tier.add(k)
            presence[k].append((tier_idx, ev))

    out = []
    for k, tier_hits in presence.items():
        if len(tier_hits) >= quorum:
            _tier, ev = tier_hits[0]  # keep the first tier's evidence
            out.append(ev)
    return out


# ─── Main aggregation ─────────────────────────────────────────────────────

def merge_silvers(silvers: list[dict], tier_names: list[str]) -> tuple[dict, list[dict]]:
    """Produce (merged_phenotype, per_field_agreement_rows)."""
    n = len(silvers)
    quorum = (n // 2) + 1  # majority (2 of 3)

    merged: dict = {"schema_version": "v0.2.1"}
    # copy the document block from the primary tier
    doc = silvers[0].get("document", {}) if silvers else {}
    if doc:
        merged["document"] = dict(doc)

    rows = []

    # Scalar Evidence wrapper fields
    for path in SCALAR_EVIDENCE_FIELDS:
        vals = [_get_by_path(s, path) for s in silvers]
        winner, agreement = _mode_with_quorum(vals, quorum)
        # Also vote on certainty + temporal_status alongside .value
        parent_path = path.rsplit(".", 1)[0]
        cert_vals = [_get_by_path(s, parent_path + ".certainty") for s in silvers]
        temp_vals = [_get_by_path(s, parent_path + ".temporal_status") for s in silvers]
        ev_vals   = [_get_by_path(s, parent_path + ".evidence_text") for s in silvers]
        cert, _ = _mode_with_quorum(cert_vals, quorum)
        temp, _ = _mode_with_quorum(temp_vals, quorum)
        # Emit the merged Evidence wrapper if a winner exists
        if winner is not None:
            _set_by_path(merged, parent_path, {
                "value":            winner,
                "certainty":        cert if cert else "not_documented",
                "temporal_status":  temp if temp else "not_documented",
                "evidence_text":    ev_vals[0] if ev_vals and ev_vals[0] else None,
                "source_doc_id":    None,
                "char_start":       None,
                "char_end":         None,
            })
        rows.append({
            "field": path,
            "tier_values": " || ".join(str(v) for v in vals),
            "winner": winner,
            "agreement": agreement,
        })

    # List fields
    for (module, fld), key_fn in LIST_FIELDS.items():
        lists = [_get_by_path(s, f"{module}.{fld}") for s in silvers]
        merged_list = _multiset_vote(lists, key_fn, quorum)
        if merged_list:
            _set_by_path(merged, f"{module}.{fld}", merged_list)
        # Agreement row: count how many items each tier had, and how many made majority
        tier_counts = [len(l) if isinstance(l, list) else 0 for l in lists]
        rows.append({
            "field": f"{module}.{fld}",
            "tier_values": " || ".join(str(c) for c in tier_counts),
            "winner": f"{len(merged_list)}_items",
            "agreement": f"n_items_after_majority={len(merged_list)}",
        })

    return merged, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-root", required=True,
                    help="Root dir containing the per-tier silver_per_doc*/ dirs.")
    ap.add_argument("--tiers", required=True,
                    help="Comma-separated sibling dir names (in vote order; primary first)")
    ap.add_argument("--tier-names", required=True,
                    help="Comma-separated tier labels for the agreement report")
    ap.add_argument("--out", default="silver_per_doc_majority",
                    help="Output dir name (relative to --corpus-root)")
    ap.add_argument("--agreement-csv", default=None,
                    help="Optional path for the per-field agreement report")
    args = ap.parse_args()

    corpus = Path(args.corpus_root)
    if not corpus.is_absolute():
        corpus = REPO / corpus

    tier_dirs = [corpus / d.strip() for d in args.tiers.split(",")]
    tier_names = [n.strip() for n in args.tier_names.split(",")]
    if len(tier_dirs) != len(tier_names):
        raise SystemExit("--tiers and --tier-names must have matching count")
    for d in tier_dirs:
        if not d.exists():
            raise SystemExit(f"Missing tier dir: {d}")

    out_dir = corpus / args.out
    out_dir.mkdir(exist_ok=True, parents=True)

    # Enumerate all doc IDs present in the primary tier
    primary = tier_dirs[0]
    doc_ids = sorted(p.stem for p in primary.glob("*.json"))
    print(f"[majority-vote] {len(doc_ids)} docs; {len(tier_names)} tiers: {tier_names}")

    all_agreement_rows = []
    n_written = 0
    for did in doc_ids:
        silvers = []
        for tdir in tier_dirs:
            p = tdir / f"{did}.json"
            if not p.exists():
                silvers.append({})
                continue
            try:
                silvers.append(json.loads(p.read_text()))
            except json.JSONDecodeError:
                silvers.append({})
        merged, rows = merge_silvers(silvers, tier_names)
        (out_dir / f"{did}.json").write_text(json.dumps(merged, indent=2, ensure_ascii=False))
        for r in rows:
            r["doc_id"] = did
            all_agreement_rows.append(r)
        n_written += 1

    print(f"[majority-vote] Wrote {n_written} merged silvers → {out_dir}")

    if args.agreement_csv:
        ap_path = Path(args.agreement_csv)
        if not ap_path.is_absolute():
            ap_path = REPO / ap_path
        ap_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = ["doc_id", "field", "tier_values", "winner", "agreement"]
        with ap_path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            for r in all_agreement_rows:
                w.writerow({k: r.get(k, "") for k in fieldnames})
        print(f"[majority-vote] Agreement report → {ap_path}")

    # Summary counts
    winners = Counter()
    for r in all_agreement_rows:
        # Bucket by agreement mode
        if r["agreement"].startswith("all_null"):
            winners["all_null"] += 1
        elif r["agreement"].startswith("disagree"):
            winners["disagree"] += 1
        elif r["agreement"].startswith("n_items_after_majority"):
            winners["list_field"] += 1
        else:
            winners["majority_agree"] += 1
    total = sum(winners.values())
    if total:
        print(f"\n[majority-vote] Agreement summary across {total} field-doc cells:")
        for k in ["majority_agree", "all_null", "disagree", "list_field"]:
            pct = 100 * winners[k] / total
            print(f"  {k:<20}  {winners[k]:5d}  ({pct:5.1f}%)")


if __name__ == "__main__":
    raise SystemExit(main())
