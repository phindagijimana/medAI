#!/usr/bin/env python3
"""Shape D scaffold: LoRA fine-tune Med42-8B on the MedAI-EPI pilot pairs.

Given the (rendered_document, target_phenotype.json) pairs produced by
Phase 6D.2 + `scripts/semantic_plan_to_evidence.py`, build supervised
training pairs and run LoRA fine-tuning on top of the frozen Med42-8B
base model. The fine-tuned adapter is saved to `checkpoints/med42_lora_epi/`
and can be loaded by `services/med42_model.py` in a follow-up run.

This script is a *scaffold* — it wires PEFT + Trainer with sensible
defaults (rank 16, alpha 32, target modules q/k/v/o_proj, LR 3e-4, 5
epochs). It does NOT auto-execute — call the SLURM wrapper
`scripts/slurm_finetune_med42.sh` when ready.

Training data (n=60 today):
  60 (prompt, target_json) pairs where:
    prompt  = "Extract the epilepsy phenotype from this note as JSON.\\n
              Note: <rendered_document>"
    target  = the target_phenotype.json for that patient (Evidence[T]
              schema-conforming, produced by
              scripts/semantic_plan_to_evidence.py)

Scaling to 500-1000 pairs is a Shape C corpus expansion (documented in
docs/FUTURE_WORK.md); this scaffold trains on whatever pairs exist.

Note: Med42-8B in bfloat16 + LoRA at rank 16 fits comfortably in ~18 GB
VRAM. Full training run at 5 epochs × 60 examples takes ~5-15 min on a
single L40S 24 GB slice.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

logger = logging.getLogger(__name__)

# Data locations
RUN_DIR = REPO / "data" / "episynth_pilot" / "run_001"
TARGETS_DIR = RUN_DIR / "targets"
CHECKPOINT_DIR = REPO / "checkpoints" / "med42_lora_epi"


def _build_training_pairs():
    """(prompt, target_json_string) for every rendered document.

    We reuse the same rendered docs that the pilot produced — so the
    model sees the *distribution of prose styles* the pilot generates
    (C0 template, C1 free-form, C2 structured, C3 semantic-plan-constrained)
    and learns to map any of them to the canonical Evidence[T] target.
    """
    pairs: list[tuple[str, str]] = []
    for arm_dir in sorted(RUN_DIR.iterdir()):
        if not arm_dir.is_dir() or arm_dir.name in ("g2", "targets"):
            continue
        if arm_dir.name == "C0":
            iterator = [(arm_dir.name, "C0", p.name, p / "output.txt")
                        for p in sorted(arm_dir.iterdir()) if p.is_dir()]
        else:
            iterator = []
            for cond_dir in sorted(arm_dir.iterdir()):
                if not cond_dir.is_dir(): continue
                for p in sorted(cond_dir.iterdir()):
                    if p.is_dir():
                        iterator.append((arm_dir.name, cond_dir.name, p.name, p / "output.txt"))
        for _, _, pid, text_path in iterator:
            if not text_path.exists(): continue
            target_path = TARGETS_DIR / pid / "target_phenotype.json"
            if not target_path.exists(): continue
            note = text_path.read_text(encoding="utf-8")
            target = target_path.read_text(encoding="utf-8")
            prompt = (
                "Extract the epilepsy phenotype from this clinical text into "
                "the MedAI-EPI v0.2.1 JSON schema. Return only valid JSON.\n\n"
                f"Clinical text:\n\"\"\"\n{note}\n\"\"\"\n\n"
                "Phenotype JSON:\n"
            )
            pairs.append((prompt, target))
    return pairs


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Late imports — training deps are heavy.
    try:
        import torch
        from transformers import (
            AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer,
            DataCollatorForLanguageModeling,
        )
        from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
        from datasets import Dataset
    except ImportError as e:
        raise SystemExit(
            f"Fine-tuning deps missing: {e}\n"
            "Install with: pip install peft trl bitsandbytes accelerate datasets"
        )

    model_id = os.environ.get("MODEL_NAME", "m42-health/Llama3-Med42-8B")
    cache_dir = os.environ.get("MED42_MODEL_CACHE_DIR", str(REPO / "model_cache"))
    output_dir = str(CHECKPOINT_DIR)

    logger.info("Loading tokenizer and model: %s (cache=%s)", model_id, cache_dir)
    tok = AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    base = AutoModelForCausalLM.from_pretrained(
        model_id, cache_dir=cache_dir,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        trust_remote_code=True,
    )

    lora_cfg = LoraConfig(
        r=16, lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05, bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(base, lora_cfg)
    model.print_trainable_parameters()

    # Build dataset
    pairs = _build_training_pairs()
    if not pairs:
        raise SystemExit(
            "No (prompt, target) pairs found. Run scripts/semantic_plan_to_evidence.py first."
        )
    logger.info("Training pairs: %d", len(pairs))

    def _format(row):
        text = row["prompt"] + row["target"] + tok.eos_token
        toks = tok(text, truncation=True, max_length=4096, padding=False)
        toks["labels"] = toks["input_ids"].copy()
        return toks

    ds = Dataset.from_list([{"prompt": p, "target": t} for p, t in pairs])
    ds = ds.map(_format, remove_columns=ds.column_names)

    args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        num_train_epochs=5,
        learning_rate=3e-4,
        warmup_ratio=0.1,
        weight_decay=0.01,
        logging_steps=5,
        save_strategy="epoch",
        bf16=torch.cuda.is_available(),
        report_to="none",
        seed=0,
    )
    trainer = Trainer(
        model=model, args=args, train_dataset=ds,
        data_collator=DataCollatorForLanguageModeling(tok, mlm=False),
    )
    trainer.train()
    model.save_pretrained(output_dir)
    tok.save_pretrained(output_dir)
    logger.info("Saved LoRA adapter → %s", output_dir)


if __name__ == "__main__":
    main()
