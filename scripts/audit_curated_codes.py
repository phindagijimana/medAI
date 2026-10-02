#!/usr/bin/env python3
"""Report curated ontology codes that disagree with the pinned releases.

    venv/bin/python scripts/audit_curated_codes.py
    venv/bin/python scripts/audit_curated_codes.py --review-csv data/ontologies/curated_code_review.csv
    venv/bin/python scripts/audit_curated_codes.py --write-known-issues   # after fixing entries

tests/test_curated_codes.py fails on any issue not listed in
data/curated/curated_code_known_issues.json, so fixed entries should be
removed from that file (``--write-known-issues``) and new ones never added.

``--review-csv`` writes a clinician worklist with suggested replacement SCTIDs:
active SNOMED concepts that have a description exactly matching the entry's
label or one of its own synonyms.  The file quotes SNOMED CT names, so it is
written under data/ontologies/ (gitignored, UMLS licence).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from services.curated_code_audit import KNOWN_ISSUES, _curated_maps, _umls_added, audit  # noqa: E402


def _suggestions(wanted: dict[tuple[str, str], set[str]]) -> dict[tuple[str, str], list[str]]:
    """(group, key) → ["SCTID FSN", ...] for active concepts whose description matches."""
    from services.ontology_loaders import (
        _rf2_file, _snomed_active, _snomed_descriptions, release_path, semantic_tag,
    )
    root = release_path("snomed")
    active = _snomed_active(root)
    by_name: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for gk, names in wanted.items():
        for n in names:
            by_name[n.lower()].add(gk)
    hits: dict[tuple[str, str], set[str]] = defaultdict(set)
    with _rf2_file(root, "Snapshot/Terminology/sct2_Description_Snapshot-en_*.txt").open(encoding="utf-8") as f:
        next(f)
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if cols[2] == "1" and active.get(cols[4]):
                for gk in by_name.get(cols[7].lower(), ()):
                    hits[gk].add(cols[4])
    names = _snomed_descriptions(root, {c for cs in hits.values() for c in cs})
    return {
        gk: sorted(f"{c} {names[c]['fsn']}" for c in cs if semantic_tag(names[c]["fsn"]) != "situation")
        for gk, cs in hits.items()
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review-csv", type=Path)
    ap.add_argument("--write-known-issues", action="store_true",
                    help=f"freeze the current issues into {KNOWN_ISSUES.relative_to(REPO)}")
    args = ap.parse_args()
    issues = sorted(audit(), key=lambda i: (i.kind, i.group, i.key))
    for i in issues:
        print(f"{i.kind:24s} {i.group:24s} {i.key:32s} {i.code:>12s}  {i.detail}")
    print()
    for kind, n in Counter(i.kind for i in issues).most_common():
        print(f"{n:5d} {kind}")

    if args.write_known_issues:
        KNOWN_ISSUES.write_text(json.dumps(
            [[i.group, i.key, i.kind, i.code] for i in issues], indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {KNOWN_ISSUES.relative_to(REPO)} ({len(issues)} issues)")

    if args.review_csv:
        maps, added = _curated_maps(), _umls_added()
        wanted = {}
        for i in issues:
            if i.kind.startswith("sctid_"):
                e = maps[i.group][i.key]
                stale = set(added.get((i.group, i.key), []))
                wanted[(i.group, i.key)] = {e.label, i.key.replace("_", " "),
                                            *(s for s in e.synonyms if s not in stale)}
        sugg = _suggestions(wanted)
        args.review_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.review_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["group", "key", "label", "issue", "code", "detail", "suggested_sctids",
                        "reviewer_decision", "reviewer_sctid"])
            for i in issues:
                e = maps[i.group][i.key]
                w.writerow([i.group, i.key, e.label, i.kind, i.code, i.detail,
                            " | ".join(sugg.get((i.group, i.key), [])), "", ""])
        print(f"\nwrote {args.review_csv} ({sum(1 for s in sugg.values() if s)} entries with suggestions)")


if __name__ == "__main__":
    main()
