"""Verify that a proposed synth-v1 held-out patient set is disjoint from
the LoRA training set.

Background
----------
All LoRA runs (`checkpoints/llama3-med42-8b_lora_epi{,_v2,_v3_fssplit}`) drove
`scripts/finetune_lora_epi.py` with the ``synth+fs`` or ``synth+fs80`` corpus,
a patient-level split at ``val_frac=0.1``, and ``seed=0``. Under
``_split_by_patient(seed=0)`` those 500 synth patients (P000500..P000999) plus
either 200 F-S patients (``synth+fs``) or the first 160 F-S patients
(``synth+fs80``) are grouped by ``patient_id``, sorted, then shuffled with
``random.Random(0)``; the first ``round(0.1 * n_pids)`` shuffled IDs become
the val split — those documents are NEVER included in the training loss.

That val split (51 synth patients under ``synth+fs80``; 50 under ``synth+fs``)
is therefore a legitimate held-out subset of synth-v1 for Phase 6c.

This script:
  1. Recomputes the val split for each historical LoRA run.
  2. Loads a candidate held-out set from
     ``data/eval_corpora/synth_v1_eval_100/manifest.csv``.
  3. By default asserts every proposed patient is in the ``synth+fs80``
     val split (i.e. never trained on by the current ``v3_fssplit``
     adapter). With ``--target=synth+fs`` checks the older split; with
     ``--target=all`` requires membership in every historical split.

Exit code
---------
0 on success. Non-zero on: manifest missing, patient outside synth-v1
range, or patient trained on by the target adapter.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# The historical LoRA runs and their training corpora, from
# `logs/medai_lora_*.out` (`corpus=` line) and `scripts/finetune_lora_epi.py`:
#   142628, 143567, 143696, 147438 : corpus=synth+fs  (200 F-S + 500 synth)
#   154289                         : corpus=synth+fs80 (160 F-S + 500 synth)
#
# All ran with the default `val_frac=0.1`, `val_seed=0`. Any patient present
# in EVERY val split is a truly held-out patient across all our LoRA runs.
LORA_RUNS = [
    ("synth+fs",   200),
    ("synth+fs80", 160),
]
SYNTH_RANGE = (500, 1000)   # P000500..P000999 inclusive
VAL_FRAC = 0.1
VAL_SEED = 0


def _val_pids(n_fs_patients: int) -> set[str]:
    """Reproduce `_split_by_patient` for the given (synth-v1, first-N F-S)."""
    pids = [f"P{i:06d}" for i in range(*SYNTH_RANGE)] \
         + [f"EA{i:04d}" for i in range(1, n_fs_patients + 1)]
    pids = sorted(pids)
    rng = random.Random(VAL_SEED)
    rng.shuffle(pids)
    n_val = max(1, int(round(len(pids) * VAL_FRAC)))
    return set(pids[:n_val])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=str(REPO_ROOT / "data" / "eval_corpora"
                    / "synth_v1_eval_100" / "manifest.csv"),
    )
    parser.add_argument(
        "--print-shared",
        action="store_true",
        help="Print the intersection of val splits across all LoRA runs.",
    )
    parser.add_argument(
        "--target",
        choices=["synth+fs80", "synth+fs", "all"],
        default="synth+fs80",
        help="Which LoRA run's val split to check membership against. "
             "'all' requires membership in every historical split "
             "(strict intersection, very small).",
    )
    args = parser.parse_args(argv)

    # 1. Recompute val splits for every historical LoRA run.
    val_splits = {name: _val_pids(n) for name, n in LORA_RUNS}
    for name, split in val_splits.items():
        synth_only = sorted(p for p in split if p.startswith("P0"))
        print(f"[verify] LoRA run corpus={name:12s} val patients: "
              f"{len(split)} total, {len(synth_only)} synth")

    # 2. Intersection = patients held out from EVERY LoRA run.
    shared = set.intersection(*val_splits.values())
    shared_synth = sorted(p for p in shared if p.startswith("P0"))
    print(f"[verify] Shared val split (across all runs): "
          f"{len(shared)} total, {len(shared_synth)} synth")
    if args.print_shared:
        print("[verify] Shared synth patient IDs (P0*):")
        for p in shared_synth:
            print(f"    {p}")

    # 3. Load candidate held-out manifest.
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"[verify] FAIL: manifest not found at {manifest_path}",
              file=sys.stderr)
        return 2

    candidate: set[str] = set()
    with manifest_path.open() as fh:
        for row in csv.DictReader(fh):
            pid = row.get("patient_id", "").strip()
            if pid:
                candidate.add(pid)
    print(f"[verify] Candidate held-out set: {len(candidate)} patients "
          f"({manifest_path.name})")

    # 4. Assertions.
    lo, hi = SYNTH_RANGE
    out_of_range = [p for p in candidate
                    if not (p.startswith("P0") and lo <= int(p[1:]) < hi)]
    if out_of_range:
        print(f"[verify] FAIL: {len(out_of_range)} candidate IDs outside "
              f"synth-v1 range P{lo:06d}..P{hi-1:06d}: "
              f"{sorted(out_of_range)[:5]}...", file=sys.stderr)
        return 3

    if args.target == "all":
        target_names = list(val_splits.keys())
    else:
        target_names = [args.target]

    fail = False
    for name in target_names:
        split = val_splits[name]
        leaked = sorted(candidate - split)
        if leaked:
            print(f"[verify] FAIL: {len(leaked)} candidate patients were "
                  f"trained on in LoRA run corpus={name}: {leaked[:5]}...",
                  file=sys.stderr)
            fail = True
        else:
            print(f"[verify] OK: all {len(candidate)} candidates held out "
                  f"from corpus={name}")
    if fail:
        return 4

    print(f"[verify] PASS: candidate held-out set is disjoint from LoRA "
          f"training data for target={args.target}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
