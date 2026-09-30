#!/usr/bin/env python3
"""Train MetaCAT classifiers (Presence / Experiencer / Temporality / Certainty).

One MetaCAT model is trained per task, sharing a BERT tokenizer +
embedder.  Input is a MedCATTrainer-format silver export from
scripts/emit_metacat_silver.py.

Output: checkpoints/metacat/{TASK}/  containing the MetaCAT save_dir_path
files (model_state_dict.pt, config, tokenizer artifacts).

Usage:

    venv-medcat/bin/python scripts/train_metacat.py \\
        --training-export data/metacat_training/silver.json \\
        --out-dir checkpoints/metacat \\
        --tokenizer-model emilyalsentzer/Bio_ClinicalBERT \\
        --tasks Presence,Experiencer,Temporality,Certainty \\
        --epochs 5

For quick smoke, pass --tasks Presence and --epochs 1.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


DEFAULT_TASKS = ["Presence", "Experiencer", "Temporality", "Certainty"]


def _train_one_task(export_path: Path, task: str, out_dir: Path,
                    tokenizer_model: str, epochs: int, seed: int = 0) -> None:
    """Train a single MetaCAT classifier for `task` from the silver export."""
    from medcat.components.addons.meta_cat.meta_cat import MetaCAT
    from medcat.config.config_meta_cat import ConfigMetaCAT
    from medcat.components.addons.meta_cat.mctokenizers.bert_tokenizer import (
        TokenizerWrapperBERT,
    )
    from transformers import AutoTokenizer, AutoModel

    print(f"[train-metacat] === Task: {task} ===", flush=True)
    tokenizer_hf = AutoTokenizer.from_pretrained(tokenizer_model)
    embedder = AutoModel.from_pretrained(tokenizer_model)
    tokenizer = TokenizerWrapperBERT(hf_tokenizers=tokenizer_hf)

    # Extract initial embedding weights
    embeddings = embedder.embeddings.word_embeddings.weight.detach().clone()

    config = ConfigMetaCAT()
    config.general.category_name = task
    config.model.nclasses = 0  # auto-detected from training data
    config.train.nepochs = epochs
    config.train.batch_size = 32
    config.train.lr = 2e-5
    config.train.class_weights = None  # will be inferred from data
    config.train.test_size = 0.1
    config.train.shuffle_data = True
    config.model.model_name = "bert"  # BERT-family classifier head
    config.train.metric = {"base": "weighted", "score": "f1"}

    mc = MetaCAT(tokenizer=tokenizer, embeddings=embeddings, config=config)

    task_out = out_dir / task
    task_out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    result = mc.train_raw(json_path=str(export_path), save_dir_path=str(task_out))
    print(f"[train-metacat]   {task} done in {time.time()-t0:.1f}s")
    print(f"[train-metacat]   result: {result}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--training-export", required=True,
                    help="MedCATTrainer JSON export from emit_metacat_silver.py")
    ap.add_argument("--out-dir", default="checkpoints/metacat")
    ap.add_argument("--tokenizer-model", default="emilyalsentzer/Bio_ClinicalBERT",
                    help="HuggingFace model ID for BERT tokenizer + initial embeddings")
    ap.add_argument("--tasks", default=",".join(DEFAULT_TASKS),
                    help="Comma-separated task names")
    ap.add_argument("--epochs", type=int, default=5)
    args = ap.parse_args()

    export_path = Path(args.training_export)
    if not export_path.is_absolute():
        export_path = REPO / export_path
    if not export_path.exists():
        raise SystemExit(f"Missing training export: {export_path}")

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    for task in tasks:
        _train_one_task(export_path, task, out_dir,
                        args.tokenizer_model, args.epochs)

    print(f"\n[train-metacat] All tasks done. Weights: {out_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
