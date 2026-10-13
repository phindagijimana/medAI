#!/usr/bin/env python3
"""Emit Trove-style weak labels from EpExtra rules for a directory of notes.

Each line is ``{"doc_id", "labels": {field_path: value}}``. Abstentions are omitted. This is the input
a label model would use (Fries et al., Nat Commun 2021); it does not train one.

    venv-medcat/bin/python scripts/emit_weak_labels.py --dir data/notes --out data/weak_labels.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from rules.weak_labels import LABELING_FUNCTIONS, weak_labels  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", default="data/weak_labels.jsonl")
    ap.add_argument("--fields", default="", help="comma-separated field paths; default all")
    args = ap.parse_args()
    fields = [x.strip() for x in args.fields.split(",") if x.strip()] or None
    if fields:
        unknown = set(fields) - set(LABELING_FUNCTIONS)
        if unknown:
            raise SystemExit(f"unknown fields: {sorted(unknown)}")
    rows = []
    for path in sorted(Path(args.dir).glob("*.txt")):
        labels = weak_labels(path.read_text(encoding="utf-8", errors="ignore"), fields)
        rows.append({"doc_id": path.stem, "labels": labels})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    n = sum(1 for r in rows if r["labels"])
    print(f"wrote {len(rows)} notes, {n} with at least one label, to {out}")


if __name__ == "__main__":
    main()
