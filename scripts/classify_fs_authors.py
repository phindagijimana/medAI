#!/usr/bin/env python3
"""Count F-S letter authors from the signature block (``services.note_author``).

The Fonferko-Shadrach letters are mostly unsigned, so they cannot support Ojemann-style
epileptologist vs general-neurologist stratification. This script records that fact.

    venv-medcat/bin/python scripts/classify_fs_authors.py --out eval/results/fs_author_types
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.score_leo_vs_fs_gold import FS_TEXT_DIR, HELD_OUT  # noqa: E402
from services.note_author import note_author  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="eval/results/fs_author_types")
    args = ap.parse_args()
    held = set(HELD_OUT)
    rows = []
    for i in range(1, 201):
        pid = f"EA{i:04d}"
        text = (FS_TEXT_DIR / f"{pid}.txt").read_text(encoding="utf-8", errors="ignore")
        rows.append({"pid": pid, "split": "held_out" if pid in held else "dev", "author": note_author(text)})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {split: dict(Counter(r["author"] for r in rows if r["split"] == split))
               for split in ("dev", "held_out")}
    out.with_suffix(".json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    L = ["# F-S letter author type (signature only)", "",
         "Most letters have no signature, so LEO cannot report Ojemann-style author strata on this corpus.", "",
         "| split | unknown | epileptologist | specialist_nurse | trainee | other |",
         "|---|---:|---:|---:|---:|---:|"]
    for split, c in summary.items():
        L.append(f"| {split} | {c.get('unknown', 0)} | {c.get('epileptologist', 0)} | "
                 f"{c.get('specialist_nurse', 0)} | {c.get('trainee', 0)} | {c.get('other', 0)} |")
    out.with_suffix(".md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
