#!/usr/bin/env python3
"""Convert Fonferko-Shadrach silver labels → LoRA-ready targets + documents.

The F-S silver labels at
`data/fonferko_shadrach_2024/silver_labels_v0_2_1/EA*.json` already carry a
v0.2.1 EpilepsyPhenotype in their `.phenotype` field (produced by
`scripts/silver_label_fonferko.py`). This script:

  1. Extracts each `.phenotype` and re-validates it against the current
     `EpilepsyPhenotype` Pydantic model.
  2. Copies the source letter text alongside it.
  3. Emits both under the same layout the LoRA scaffold expects for
     synth-v1:

        data/fs_corpus/documents/{EA_ID}/progress_note/output.txt
        data/fs_corpus/targets/{EA_ID}/target_phenotype.json

Only labels that revalidate cleanly under the current schema are emitted.
Others are counted and reported at exit so silver-label drift is visible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from schema import EpilepsyPhenotype

FS_ROOT = REPO / "data" / "fonferko_shadrach_2024"
SILVER_DIR = FS_ROOT / "silver_labels_v0_2_1"
LETTERS_DIR = FS_ROOT / "zenodo_8381080" / "Gold1-200_corrected_spelling"

OUT_ROOT = REPO / "data" / "fs_corpus"
OUT_DOCS = OUT_ROOT / "documents"
OUT_TARGETS = OUT_ROOT / "targets"


def _convert_one(silver_path: Path) -> tuple[str, str]:
    """Return (status, detail). status ∈ {ok, skip:<reason>}."""
    ea_id = silver_path.stem
    try:
        silver = json.loads(silver_path.read_text(encoding="utf-8"))
    except Exception as e:
        return "skip:unreadable-silver", str(e)

    phenotype_dict = silver.get("phenotype")
    if not phenotype_dict:
        return "skip:no-phenotype", "silver JSON missing .phenotype"

    try:
        phenotype = EpilepsyPhenotype.model_validate(phenotype_dict)
    except Exception as e:
        return "skip:invalid-under-current-schema", str(e)[:200]

    letter_path = LETTERS_DIR / f"{ea_id}.txt"
    if not letter_path.exists():
        return "skip:no-source-letter", str(letter_path)
    note = letter_path.read_text(encoding="utf-8")
    if not note.strip():
        return "skip:empty-source", str(letter_path)

    out_doc_dir = OUT_DOCS / ea_id / "progress_note"
    out_doc_dir.mkdir(parents=True, exist_ok=True)
    (out_doc_dir / "output.txt").write_text(note, encoding="utf-8")

    out_target_dir = OUT_TARGETS / ea_id
    out_target_dir.mkdir(parents=True, exist_ok=True)
    (out_target_dir / "target_phenotype.json").write_text(
        phenotype.model_dump_json(indent=2), encoding="utf-8",
    )
    return "ok", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", default="EA*.json")
    args = ap.parse_args()

    OUT_DOCS.mkdir(parents=True, exist_ok=True)
    OUT_TARGETS.mkdir(parents=True, exist_ok=True)

    tally: dict[str, int] = {}
    example_skips: dict[str, str] = {}
    for silver_path in sorted(SILVER_DIR.glob(args.pattern)):
        status, detail = _convert_one(silver_path)
        tally[status] = tally.get(status, 0) + 1
        if status.startswith("skip:") and status not in example_skips:
            example_skips[status] = f"{silver_path.stem}: {detail}"

    print(f"Silver labels processed: {sum(tally.values())}")
    for k in sorted(tally):
        print(f"  {k:<45} {tally[k]}")
    if example_skips:
        print("\nOne example per skip reason:")
        for k, v in example_skips.items():
            print(f"  {k}: {v}")
    print(f"\nDocuments written: {OUT_DOCS}")
    print(f"Targets   written: {OUT_TARGETS}")


if __name__ == "__main__":
    main()
