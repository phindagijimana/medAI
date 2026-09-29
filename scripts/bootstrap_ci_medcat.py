"""Bootstrap 95 % CI for MedCAT+Rules (arm B1') micro-F1 on F-S 40 held-out.

Method
------
Per-doc CSV has (tp, fp, fn) per document. Micro-F1 is computed by summing
counts across documents. To get a bootstrap CI on micro-F1, we resample
documents with replacement N times, recompute micro-F1 on each resample,
and report the 2.5th and 97.5th percentiles (nonparametric percentile
bootstrap).

Usage
-----
    venv-medcat/bin/python scripts/bootstrap_ci_medcat.py \\
        --perdoc eval/results/medcat_iterations/iter3_fs_test_40.perdoc.csv \\
        --n-boot 1000 --seed 0

Outputs
-------
- F1 point estimate (from the observed counts)
- 95 % CI [p2.5, p97.5] over the bootstrap distribution
- Standard error of F1 across bootstrap resamples
"""
from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path


def _f1(tp: int, fp: int, fn: int) -> float:
    if tp == 0 and (fp > 0 or fn > 0):
        return 0.0
    if tp == 0:
        return 0.0
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def load_perdoc(path: Path) -> list[tuple[int, int, int]]:
    rows: list[tuple[int, int, int]] = []
    with path.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append((int(row["tp"]), int(row["fp"]), int(row["fn"])))
    return rows


def bootstrap_ci(
    counts: list[tuple[int, int, int]],
    n_boot: int = 1000,
    seed: int = 0,
) -> dict:
    rng = random.Random(seed)
    n = len(counts)
    # Observed micro-F1
    tp = sum(c[0] for c in counts)
    fp = sum(c[1] for c in counts)
    fn = sum(c[2] for c in counts)
    obs = _f1(tp, fp, fn)

    boot_f1s: list[float] = []
    for _ in range(n_boot):
        # Resample docs with replacement.
        idx = [rng.randrange(0, n) for _ in range(n)]
        btp = sum(counts[i][0] for i in idx)
        bfp = sum(counts[i][1] for i in idx)
        bfn = sum(counts[i][2] for i in idx)
        boot_f1s.append(_f1(btp, bfp, bfn))

    boot_f1s.sort()
    lo_idx = int(0.025 * n_boot)
    hi_idx = int(0.975 * n_boot)
    lo = boot_f1s[lo_idx]
    hi = boot_f1s[hi_idx]

    mean = sum(boot_f1s) / n_boot
    var = sum((x - mean) ** 2 for x in boot_f1s) / (n_boot - 1)
    se = math.sqrt(var)

    return {
        "n_docs": n,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "f1_observed": obs,
        "f1_boot_mean": mean,
        "f1_boot_se": se,
        "ci95_lo": lo,
        "ci95_hi": hi,
        "n_boot": n_boot,
        "seed": seed,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--perdoc",
        type=Path,
        required=True,
        help="Per-doc CSV with columns doc_id,tp,fp,fn,precision,recall,f1",
    )
    p.add_argument("--n-boot", type=int, default=1000)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    counts = load_perdoc(args.perdoc)
    res = bootstrap_ci(counts, n_boot=args.n_boot, seed=args.seed)

    print(f"Per-doc CSV : {args.perdoc}")
    print(f"n docs      : {res['n_docs']}")
    print(f"TP/FP/FN    : {res['tp']}/{res['fp']}/{res['fn']}")
    print(f"F1 (obs)    : {res['f1_observed']:.4f}")
    print(f"Bootstrap   : n={res['n_boot']}, seed={res['seed']}")
    print(
        f"  mean      : {res['f1_boot_mean']:.4f}   "
        f"SE = {res['f1_boot_se']:.4f}"
    )
    print(
        f"  95 % CI   : [{res['ci95_lo']:.4f}, {res['ci95_hi']:.4f}]"
    )


if __name__ == "__main__":
    main()
