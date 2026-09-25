#!/usr/bin/env python3
"""LoRA fine-tune Med42-8B or DeepSeek-R1-Distill-Llama-8B on MedAI-EPI pairs.

Supersedes `finetune_med42_lora.py`. Accepts `--base-model` (med42 | deepseek
| any HF id) and `--corpus` (pilot | synth-v1 | both) so the same script
trains either model on either training set.

Training data:
  (rendered_document, target_phenotype.json) pairs from:
    - pilot   : data/episynth_pilot/run_001/  (60 pairs, C0 + 3 GPT tiers × C1/C2/C3)
    - synth-v1: data/episynth_corpus/v1/      (up to 1000 pairs, GPT-5.6-sol)
    - both    : concatenation

Adapter output:
    checkpoints/{base_model_slug}_lora_epi/

Defaults tuned for L40S 24 GB: rank 16, alpha 32, q/k/v/o_proj, lr 3e-4,
bfloat16, batch=1, grad_accum=8, 5 epochs. Deterministic (seed=0).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

logger = logging.getLogger(__name__)

PILOT_RUN = REPO / "data" / "episynth_pilot" / "run_001"
PILOT_TARGETS = PILOT_RUN / "targets"

SYNTH_ROOT = REPO / "data" / "episynth_corpus" / "v1"
SYNTH_DOCS = SYNTH_ROOT / "documents"
SYNTH_TARGETS = SYNTH_ROOT / "targets"

BASE_MODEL_ALIASES = {
    "med42": "m42-health/Llama3-Med42-8B",
    "deepseek": "deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
}

PROMPT_TEMPLATE = (
    "Extract the epilepsy phenotype from this clinical text into the "
    "MedAI-EPI v0.2.1 JSON schema. Return only valid JSON.\n\n"
    "Clinical text:\n\"\"\"\n{note}\n\"\"\"\n\n"
    "Phenotype JSON:\n"
)


def _pilot_pairs() -> list[tuple[str, str, str]]:
    """(pid, note, target_json) triples for the 60-doc pilot corpus."""
    triples: list[tuple[str, str, str]] = []
    for arm_dir in sorted(PILOT_RUN.iterdir()):
        if not arm_dir.is_dir() or arm_dir.name in ("g2", "targets"):
            continue
        if arm_dir.name == "C0":
            iterator = [(p.name, p / "output.txt")
                        for p in sorted(arm_dir.iterdir()) if p.is_dir()]
        else:
            iterator = []
            for cond_dir in sorted(arm_dir.iterdir()):
                if not cond_dir.is_dir():
                    continue
                for p in sorted(cond_dir.iterdir()):
                    if p.is_dir():
                        iterator.append((p.name, p / "output.txt"))
        for pid, text_path in iterator:
            if not text_path.exists():
                continue
            target_path = PILOT_TARGETS / pid / "target_phenotype.json"
            if not target_path.exists():
                continue
            triples.append((
                pid,
                text_path.read_text(encoding="utf-8"),
                target_path.read_text(encoding="utf-8"),
            ))
    return triples


def _synth_pairs() -> list[tuple[str, str, str]]:
    """(pid, note, target_json) triples for the synth-v1 corpus."""
    triples: list[tuple[str, str, str]] = []
    if not SYNTH_DOCS.exists():
        return triples
    for pid_dir in sorted(SYNTH_DOCS.iterdir()):
        if not pid_dir.is_dir():
            continue
        pid = pid_dir.name
        target_path = SYNTH_TARGETS / pid / "target_phenotype.json"
        if not target_path.exists():
            continue
        target_json = target_path.read_text(encoding="utf-8")
        for doc_type_dir in sorted(pid_dir.iterdir()):
            if not doc_type_dir.is_dir():
                continue
            out_path = doc_type_dir / "output.txt"
            if not out_path.exists():
                continue
            note = out_path.read_text(encoding="utf-8")
            if not note.strip():
                continue
            triples.append((f"{pid}/{doc_type_dir.name}", note, target_json))
    return triples


def _build_training_pairs(corpus: str) -> list[tuple[str, str]]:
    triples: list[tuple[str, str, str]] = []
    if corpus in ("pilot", "both"):
        triples.extend(_pilot_pairs())
    if corpus in ("synth-v1", "both"):
        triples.extend(_synth_pairs())
    return [(PROMPT_TEMPLATE.format(note=note), target) for _, note, target in triples]


def _resolve_base_model(alias_or_id: str) -> str:
    return BASE_MODEL_ALIASES.get(alias_or_id, alias_or_id)


def _slug(model_id: str) -> str:
    return model_id.split("/")[-1].replace(".", "_").lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-model", default="med42",
                    help="med42 | deepseek | any HF model id")
    ap.add_argument("--corpus", default="pilot",
                    choices=("pilot", "synth-v1", "both"))
    ap.add_argument("--output-dir", default=None,
                    help="Adapter output dir (default: checkpoints/{slug}_lora_epi)")
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--max-length", type=int, default=4096)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true",
                    help="Report pair count and exit; do not load model or train.")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    model_id = _resolve_base_model(args.base_model)
    output_dir = args.output_dir or str(REPO / "checkpoints" / f"{_slug(model_id)}_lora_epi")

    pairs = _build_training_pairs(args.corpus)
    logger.info("Base model : %s", model_id)
    logger.info("Corpus     : %s", args.corpus)
    logger.info("Pairs      : %d", len(pairs))
    logger.info("Output dir : %s", output_dir)

    if not pairs:
        raise SystemExit(
            "No (prompt, target) pairs found. Run the corpus generator/converter first."
        )
    if args.dry_run:
        return

    try:
        import torch
        from transformers import (
            AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer,
            DataCollatorForLanguageModeling,
        )
        from peft import LoraConfig, TaskType, get_peft_model
        from datasets import Dataset
    except ImportError as e:
        raise SystemExit(
            f"Fine-tuning deps missing: {e}\n"
            "Install with: pip install peft trl bitsandbytes accelerate datasets"
        )

    cache_dir = os.environ.get("MED42_MODEL_CACHE_DIR", str(REPO / "model_cache"))
    logger.info("Loading tokenizer + model (cache=%s)", cache_dir)
    tok = AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    base = AutoModelForCausalLM.from_pretrained(
        model_id, cache_dir=cache_dir,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        trust_remote_code=True,
    )
    lora_cfg = LoraConfig(
        r=args.rank, lora_alpha=args.alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05, bias="none", task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(base, lora_cfg)
    model.print_trainable_parameters()

    def _format(row):
        text = row["prompt"] + row["target"] + tok.eos_token
        toks = tok(text, truncation=True, max_length=args.max_length, padding=False)
        toks["labels"] = toks["input_ids"].copy()
        return toks

    ds = Dataset.from_list([{"prompt": p, "target": t} for p, t in pairs])
    ds = ds.map(_format, remove_columns=ds.column_names)

    targs = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        warmup_ratio=0.1,
        weight_decay=0.01,
        logging_steps=5,
        save_strategy="epoch",
        bf16=torch.cuda.is_available(),
        report_to="none",
        seed=0,
    )
    trainer = Trainer(
        model=model, args=targs, train_dataset=ds,
        data_collator=DataCollatorForLanguageModeling(tok, mlm=False),
    )
    trainer.train()
    model.save_pretrained(output_dir)
    tok.save_pretrained(output_dir)
    logger.info("Saved LoRA adapter → %s", output_dir)


if __name__ == "__main__":
    main()
