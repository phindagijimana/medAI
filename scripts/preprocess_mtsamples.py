#!/usr/bin/env python3
"""MTSamples-specific preprocessing shim.

Delegates to the corpus-agnostic scripts/preprocess_us_notes.py with the
mtsamples layout. Kept for backwards compatibility with scripts/docs that
reference this filename.

Usage:
    venv-medcat/bin/python scripts/preprocess_mtsamples.py \\
        --in-dir data/eval_corpora/mtsamples_neuro \\
        --out-dir data/eval_corpora/mtsamples_neuro_preprocessed \\
        --min-relevance-score 3.0
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", default="data/eval_corpora/mtsamples_neuro")
    ap.add_argument("--out-dir", default="data/eval_corpora/mtsamples_neuro_preprocessed")
    ap.add_argument("--min-relevance-score", type=float, default=3.0)
    ap.add_argument("--min-chars", type=int, default=300)
    args = ap.parse_args()

    cmd = [
        sys.executable, str(REPO / "scripts" / "preprocess_us_notes.py"),
        "--layout", "mtsamples",
        "--in-dir", args.in_dir,
        "--out-dir", args.out_dir,
        "--corpus", "mtsamples",
        "--min-relevance-score", str(args.min_relevance_score),
        "--min-chars", str(args.min_chars),
    ]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
