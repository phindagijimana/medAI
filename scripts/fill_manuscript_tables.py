#!/usr/bin/env python3
"""Populate the manuscript's PENDING tables from run manifests.

Reads all manifests under data/run_manifests/, groups by arm, computes
schema validity + evidence + per-module numbers, and prints
Markdown-formatted tables ready to paste into
paper_doc/MedAI_EPI_Manuscript_v0.1.md (Tables 5-9).

Usage:
    python scripts/fill_manuscript_tables.py
    python scripts/fill_manuscript_tables.py --out paper_doc/generated_tables.md

Runs entirely on CPU. No dependencies beyond eval/ and Pydantic.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.aggregator import aggregate_manifests, load_gold


REPO = Path(__file__).resolve().parent.parent
MANIFESTS = REPO / "data" / "run_manifests"
GOLD = REPO / "data" / "fonferko_shadrach_2024" / "silver_labels_v0_2_1"


def _table_5_validity(summaries) -> str:
    lines = ["**Table 5. Raw + repaired schema validity by arm.**\n",
             "| Arm | n docs | Raw validity | Repaired validity | Parse failures | Total (final valid) |",
             "|---|---:|---:|---:|---:|---:|"]
    for arm in sorted(summaries):
        s = summaries[arm]
        lines.append(
            f"| {arm} | {s.n_documents} | "
            f"{s.raw_validity_rate:.3f} | "
            f"{s.final_validity_rate - s.raw_validity_rate:+.3f} | "
            f"{s.parse_failures} | {s.final_validity_rate:.3f} |"
        )
    return "\n".join(lines) + "\n"


def _table_7_repair(summaries) -> str:
    all_methods: set[str] = set()
    for s in summaries.values():
        all_methods.update(s.repair_method_counts.keys())
    methods = sorted(all_methods)
    lines = ["**Table 7. Repair-method distribution (counts).**\n",
             "| Arm | " + " | ".join(methods) + " |",
             "|---|" + "|".join(["---:"] * len(methods)) + "|"]
    for arm in sorted(summaries):
        s = summaries[arm]
        row = [arm] + [str(s.repair_method_counts.get(m, 0)) for m in methods]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def _table_8_evidence(summaries) -> str:
    lines = ["**Table 8. Evidence precision + unsupported-claim rate by arm.**\n",
             "| Arm | Total evidence objs | Supported | Unsupported | Missing | Evidence precision | Unsupported-claim rate |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for arm in sorted(summaries):
        s = summaries[arm]
        lines.append(
            f"| {arm} | {s.total_evidence_objects} | "
            f"{s.evidence_supported} | {s.evidence_unsupported} | {s.evidence_missing} | "
            f"{s.evidence_precision:.3f} | {s.unsupported_claim_rate:.3f} |"
        )
    return "\n".join(lines) + "\n"


def _table_6_perfield(summaries) -> str:
    """Per-field metrics across arms and modules."""
    # Gather all (arm, module, field) tuples
    lines = ["**Table 6. Per-field precision / recall / F1 by arm (Fonferko silver-metric).**\n",
             "| Arm | Module | Field | n | P | R | F1 |",
             "|---|---|---|---:|---:|---:|---:|"]
    for arm in sorted(summaries):
        s = summaries[arm]
        for mod_name, ms in sorted(s.modules.items()):
            for fname, fm in sorted(ms.fields.items()):
                lines.append(
                    f"| {arm} | {mod_name} | {fname} | "
                    f"{fm.n_applicable} | {fm.precision:.2f} | "
                    f"{fm.recall:.2f} | {fm.f1:.2f} |"
                )
    return "\n".join(lines) + "\n"


def _table_9_efficiency(summaries) -> str:
    lines = ["**Table 9. Efficiency by arm.**\n",
             "| Arm | n docs | Total tokens | Avg tokens/doc | Total duration (s) | Avg duration/doc (s) |",
             "|---|---:|---:|---:|---:|---:|"]
    for arm in sorted(summaries):
        s = summaries[arm]
        avg_tokens = s.total_tokens_generated / s.n_documents if s.n_documents else 0
        avg_dur = s.total_duration_s / s.n_documents if s.n_documents else 0
        lines.append(
            f"| {arm} | {s.n_documents} | {s.total_tokens_generated} | "
            f"{avg_tokens:.1f} | {s.total_duration_s:.1f} | {avg_dur:.2f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifests", type=Path, default=MANIFESTS)
    ap.add_argument("--gold", type=Path, default=GOLD)
    ap.add_argument("--out", type=Path, default=None,
                    help="Write the generated tables to this file (else stdout)")
    ap.add_argument("--arm-filter", type=str, default=None,
                    help="Comma-separated arms to include (default: all)")
    args = ap.parse_args()

    if not args.manifests.exists():
        print(f"error: manifests dir not found: {args.manifests}", file=sys.stderr)
        return 2

    gold = load_gold(args.gold) if args.gold and args.gold.exists() else {}
    summaries = aggregate_manifests(args.manifests, gold=gold)
    if args.arm_filter:
        keep = set(a.strip() for a in args.arm_filter.split(","))
        summaries = {a: s for a, s in summaries.items() if a in keep}

    if not summaries:
        print("(no matching manifests found)", file=sys.stderr)
        return 1

    tables = [
        _table_5_validity(summaries),
        _table_6_perfield(summaries),
        _table_7_repair(summaries),
        _table_8_evidence(summaries),
        _table_9_efficiency(summaries),
    ]
    output = "\n---\n\n".join(tables)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
        print(f"tables → {args.out}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
