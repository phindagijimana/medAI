#!/usr/bin/env python3
"""Train the B1 epilepsy_type classifier on Fonferko-Shadrach silver labels.

Usage on a GPU node:
    python scripts/train_b1_epilepsy_type.py \
        --silver data/fonferko_shadrach_2024/silver_labels_v0_2_1 \
        --base emilyalsentzer/Bio_ClinicalBERT \
        --epochs 5 --batch 16 --out checkpoints/b1_epilepsy_type_v1

The default base model is Bio_ClinicalBERT (~440 MB download on first run).
For a fast CPU smoke test, pass --base distilbert-base-uncased --epochs 1.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.baseline_bert import (
    B1TrainingConfig,
    train_epilepsy_type_head,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--silver", type=str,
                    default="data/fonferko_shadrach_2024/silver_labels_v0_2_1")
    ap.add_argument("--base", type=str, default="emilyalsentzer/Bio_ClinicalBERT")
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=str, default="checkpoints/b1_epilepsy_type_v1")
    ap.add_argument("--max-train", type=int, default=None,
                    help="Cap number of training examples (useful for smoke tests)")
    args = ap.parse_args()

    config = B1TrainingConfig(
        base_model=args.base,
        output_dir=args.out,
        learning_rate=args.lr,
        batch_size=args.batch,
        epochs=args.epochs,
        max_length=args.max_len,
        seed=args.seed,
    )

    out_dir = train_epilepsy_type_head(
        silver_labels_dir=args.silver,
        config=config,
        max_train=args.max_train,
    )
    print(f"checkpoint → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
