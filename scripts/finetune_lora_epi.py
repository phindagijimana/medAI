#!/usr/bin/env python3
"""LoRA fine-tune Med42-8B or DeepSeek-R1-Distill-Llama-8B on MedAI-EPI pairs.

Accepts `--base-model` (med42 | deepseek | any HF id) and `--corpus` so
the same script trains either model on any of the training sources.

Training data:
  (rendered_document, target_phenotype.json) pairs from:
    - pilot    : data/episynth_pilot/run_001/    (60 pairs)
    - synth-v1 : data/episynth_corpus/v1/        (up to 1000 pairs)
    - fs       : data/fs_corpus/                 (200 real F-S clinic letters)
    - synth+fs : synth-v1 + fs                   (1200, pilot HELD OUT)  ← Option B
    - both     : pilot + synth-v1                (1060)
    - all      : pilot + synth-v1 + fs           (1260)

Adapter output:
    checkpoints/{base_model_slug}_lora_epi/

Training loop optimizations (all default-on unless explicitly disabled):
  1. Loss masking on prompt tokens — gradient only supervises the target
     JSON, not the prompt (major convergence win).
  2. Patient-level train/val split — 10% of patients held out for
     validation; documents from the same patient never straddle the split.
  3. LoRA on attention AND MLP projections (q/k/v/o + gate/up/down) —
     roughly doubles trainable params, consistently helps structured-
     output learning (QLoRA / Dettmers 2023). Toggle with --attn-only.
  4. Val-loss-based early stop with load_best_model_at_end — saves the
     best-eval checkpoint, not just the last epoch.

Defaults tuned for L40S 24 GB: rank 16, alpha 32, lr 3e-4, bfloat16,
batch=1, grad_accum=8, ≤5 epochs w/ patience=2. Deterministic (seed=0).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

logger = logging.getLogger(__name__)

PILOT_RUN = REPO / "data" / "episynth_pilot" / "run_001"
PILOT_TARGETS = PILOT_RUN / "targets"

SYNTH_ROOT = REPO / "data" / "episynth_corpus" / "v1"
SYNTH_DOCS = SYNTH_ROOT / "documents"
SYNTH_TARGETS = SYNTH_ROOT / "targets"

FS_ROOT = REPO / "data" / "fs_corpus"
FS_DOCS = FS_ROOT / "documents"
FS_TARGETS = FS_ROOT / "targets"

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


# --------------------------------------------------------------------------
# ID augmentation (fights adapter-memorization of training-set patient IDs)
# --------------------------------------------------------------------------
#
# Problem: because we mask prompt tokens during loss computation, the model
# never learns to condition its ID fields (document.doc_id,
# document.patient_id, every Evidence.source_doc_id) on the source doc — it
# just memorizes the training-set IDs and emits one at random at inference.
#
# Fix: for each training example, replace all patient/doc IDs in the target
# JSON with a per-example synthetic token that ALSO appears in the prompt
# (as a "PATIENT_ID: ..." line prepended to the note). The model then learns
# "copy this token from the prompt to every ID field," not "memorize this
# specific ID." At inference, we pass the ACTUAL doc_id in the prompt.
#
# Determinism: synthetic ID is a stable sha1 hash of the prompt text, so a
# restart / rerun produces identical augmented data.

def _synthetic_pid(prompt: str) -> str:
    """Deterministic per-example synthetic patient ID.

    sha1(prompt)[:8].upper() gives a compact, stable, per-example token
    that will not collide with any real patient/doc ID in our corpora
    (real IDs are EA#### or P###### — no hex prefix "SYNPID_").
    """
    h = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8].upper()
    return f"SYNPID_{h}"


def _augment_pair(
    pid_key: str, note: str, target_json: str,
) -> tuple[str, str, str, str]:
    """Return (new_note, new_target_json, old_pid, new_pid).

    old_pid is the source patient/doc ID (e.g. "EA0001" or "P000501") — we
    derive it from pid_key by taking the leading path segment (pid_key is
    either bare like "EA0001" or "PID/doc_type" like "P000500/progress_note").

    new_pid is a per-example synthetic like "SYNPID_A1B2C3D4" derived from
    a sha1 of the (old_pid + note) so the mapping is stable across runs.

    Replacement is a plain str.replace on the target JSON — safe because
    the old_pid is a specific identifier that will not collide with any
    legitimate content (dates, values, enum names, etc.).

    The prepended "PATIENT_ID: <new_pid>" line teaches the model to copy
    this token from the prompt into every ID field of the target.
    """
    old_pid = pid_key.split("/")[0]
    # Hash on old_pid + note so different documents from the same patient
    # get different SYNPIDs — otherwise all docs for one training patient
    # would collapse to the same synthetic ID and the model would still
    # over-generalize.
    hash_input = f"{old_pid}\n{note}"
    new_pid = _synthetic_pid(hash_input)
    new_note = f"PATIENT_ID: {new_pid}\n\n{note}"
    new_target_json = target_json.replace(old_pid, new_pid)
    return new_note, new_target_json, old_pid, new_pid


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


def _fs_pairs() -> list[tuple[str, str, str]]:
    """(pid, note, target_json) triples for the Fonferko-Shadrach corpus."""
    triples: list[tuple[str, str, str]] = []
    if not FS_DOCS.exists():
        return triples
    for pid_dir in sorted(FS_DOCS.iterdir()):
        if not pid_dir.is_dir():
            continue
        pid = pid_dir.name
        target_path = FS_TARGETS / pid / "target_phenotype.json"
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


def _collect_triples(corpus: str) -> list[tuple[str, str, str]]:
    """Return (pid_key, note, target_json) triples for the requested corpus."""
    triples: list[tuple[str, str, str]] = []
    if corpus in ("pilot", "both", "all"):
        triples.extend(_pilot_pairs())
    if corpus in ("synth-v1", "both", "synth+fs", "all"):
        triples.extend(_synth_pairs())
    if corpus in ("fs", "synth+fs", "all"):
        triples.extend(_fs_pairs())
    return triples


def _split_by_patient(
    triples: list[tuple[str, str, str]],
    val_frac: float,
    seed: int,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Split triples into (train, val) so no patient's docs straddle the split.

    pid_key can be a bare id like "P000500" or "PID/doc_type" like
    "P000500/progress_note" — we group by the leading path segment.
    """
    by_pid: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for pid_key, note, target in triples:
        pid_root = pid_key.split("/")[0]
        by_pid[pid_root].append((pid_key, note, target))
    pids = sorted(by_pid.keys())
    rng = random.Random(seed)
    rng.shuffle(pids)
    n_val = max(1, int(round(len(pids) * val_frac)))
    val_pids = set(pids[:n_val])
    train, val = [], []
    for pid in pids:
        (val if pid in val_pids else train).extend(by_pid[pid])
    return train, val


def _triples_to_pairs(
    triples: list[tuple[str, str, str]],
    id_aug: bool = True,
) -> list[tuple[str, str]]:
    """Convert (pid_key, note, target) triples to (prompt, target) pairs.

    When id_aug=True (default), applies per-example patient-ID augmentation:
    every training-set ID in the target JSON is replaced with a synthetic
    token that is ALSO injected into the prompt as a "PATIENT_ID:" line.
    This teaches the model to copy the ID from the prompt rather than
    memorize the training-set ID (which is what caused adapter v1 to
    hardcode "P000999" etc. into pilot outputs at F1=0.073 vs base F1=0.15).
    """
    pairs: list[tuple[str, str]] = []
    for pid_key, note, target in triples:
        if id_aug:
            note_aug, target_aug, _old, _new = _augment_pair(pid_key, note, target)
        else:
            note_aug, target_aug = note, target
        pairs.append((PROMPT_TEMPLATE.format(note=note_aug), target_aug))
    return pairs


def _resolve_base_model(alias_or_id: str) -> str:
    return BASE_MODEL_ALIASES.get(alias_or_id, alias_or_id)


def _slug(model_id: str) -> str:
    return model_id.split("/")[-1].replace(".", "_").lower()


def _dryrun_show_augmentation(triples: list[tuple[str, str, str]]) -> None:
    """Print one synth-style and one F-S-style before/after augmentation.

    Not a formal test — just enough to eyeball the substitution before we
    commit 90 minutes of GPU time.
    """
    synth_example = next(
        (t for t in triples if t[0].split("/")[0].startswith("P0")), None,
    )
    fs_example = next(
        (t for t in triples if t[0].split("/")[0].startswith("EA")), None,
    )

    def _show(label: str, triple: tuple[str, str, str]):
        pid_key, note, target = triple
        new_note, new_target, old_pid, new_pid = _augment_pair(pid_key, note, target)
        print(f"\n===== dry-run augmentation: {label} =====")
        print(f"  pid_key         = {pid_key}")
        print(f"  old_pid         = {old_pid}")
        print(f"  new_pid         = {new_pid}")
        print(f"  original note   (first 120 chars): {note[:120]!r}")
        print(f"  augmented note  (first 200 chars): {new_note[:200]!r}")
        # Find the doc.doc_id line in the target for easy comparison
        orig_snip = _snippet_around(target, old_pid, 60)
        new_snip = _snippet_around(new_target, new_pid, 60)
        print(f"  target snippet before: {orig_snip}")
        print(f"  target snippet after : {new_snip}")

    if synth_example is not None:
        _show("synth pair", synth_example)
    else:
        print("(no synth pair in train split — skipped synth dry-run)")

    if fs_example is not None:
        _show("F-S pair", fs_example)
    else:
        print("(no F-S pair in train split — skipped F-S dry-run)")


def _snippet_around(text: str, needle: str, radius: int) -> str:
    idx = text.find(needle)
    if idx < 0:
        return f"(needle {needle!r} not found)"
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    return repr(text[start:end])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-model", default="med42",
                    help="med42 | deepseek | any HF model id")
    ap.add_argument("--corpus", default="pilot",
                    choices=("pilot", "synth-v1", "fs", "synth+fs", "both", "all"))
    ap.add_argument("--output-dir", default=None,
                    help="Adapter output dir (default: checkpoints/{slug}_lora_epi)")
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--max-length", type=int, default=2048,
                    help="Max sequence length. Reduced from 4096 to fit 8B "
                         "model in 24 GB with gradient checkpointing.")
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--no-grad-ckpt", action="store_true",
                    help="Disable gradient checkpointing (default: on, saves ~5-10 GB VRAM).")
    ap.add_argument("--val-frac", type=float, default=0.1,
                    help="Fraction of PATIENTS held out for validation (0 disables).")
    ap.add_argument("--val-seed", type=int, default=0)
    ap.add_argument("--patience", type=int, default=2,
                    help="EarlyStopping patience in epochs (evaluated once/epoch).")
    ap.add_argument("--attn-only", action="store_true",
                    help="Restrict LoRA to attention projections (default: attn+MLP).")
    ap.add_argument("--no-id-aug", action="store_true",
                    help="Disable per-example patient-ID augmentation. Default is "
                         "ON: replace training-set patient/doc IDs with synthetic "
                         "SYNPID tokens injected into both the prompt and the "
                         "target JSON, so the model learns to copy the ID from "
                         "the prompt instead of memorizing training IDs.")
    ap.add_argument("--adapter-suffix", default="v2",
                    help="Suffix appended to the adapter output dir name. "
                         "Default 'v2' → checkpoints/{slug}_lora_epi_v2/, so the "
                         "existing overfit v1 adapter is not clobbered. Set to "
                         "empty string to use the historical unsuffixed path.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report pair count and split and exit; do not load model.")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    model_id = _resolve_base_model(args.base_model)

    # Adapter output dir: {slug}_lora_epi[_<suffix>]. Suffix is env-overridable
    # so the SLURM script can flip v1 → v2 without editing this file.
    suffix = os.environ.get("MEDAI_LORA_ADAPTER_SUFFIX", args.adapter_suffix) or ""
    slug = _slug(model_id) + "_lora_epi" + (f"_{suffix}" if suffix else "")
    output_dir = args.output_dir or str(REPO / "checkpoints" / slug)

    id_aug = not args.no_id_aug

    triples = _collect_triples(args.corpus)
    if args.val_frac > 0.0 and len(triples) >= 10:
        train_triples, val_triples = _split_by_patient(
            triples, args.val_frac, args.val_seed,
        )
    else:
        train_triples, val_triples = triples, []
    train_pairs = _triples_to_pairs(train_triples, id_aug=id_aug)
    val_pairs = _triples_to_pairs(val_triples, id_aug=id_aug)

    logger.info("Base model : %s", model_id)
    logger.info("Corpus     : %s", args.corpus)
    logger.info("Pairs      : %d train + %d val (patient-level split, seed=%d)",
                len(train_pairs), len(val_pairs), args.val_seed)
    logger.info("LoRA target: %s",
                "attn-only" if args.attn_only else "attn + MLP (gate/up/down)")
    logger.info("ID augment : %s", "ON (SYNPID copy-from-prompt)" if id_aug else "OFF")
    logger.info("Output dir : %s", output_dir)

    if not train_pairs:
        raise SystemExit(
            "No training pairs found. Run the corpus generator/converter first."
        )

    # In dry-run mode, show side-by-side augmentation for one synth + one F-S
    # pair so we can eyeball the substitution before spending 90 minutes on
    # the GPU.
    if args.dry_run:
        if id_aug:
            _dryrun_show_augmentation(train_triples)
        return

    try:
        import torch
        from transformers import (
            AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer,
            DataCollatorForSeq2Seq, EarlyStoppingCallback,
        )
        from peft import LoraConfig, TaskType, get_peft_model
        from datasets import Dataset
    except ImportError as e:
        raise SystemExit(
            f"Fine-tuning deps missing: {e}\n"
            "Install with: pip install peft accelerate datasets"
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
    # Gradient checkpointing is required to fit 8B + LoRA + activations in a
    # single L40S 24 GB slice. It recomputes activations on the backward pass,
    # roughly halving memory at ~20-30% wall-clock cost.
    if not args.no_grad_ckpt and torch.cuda.is_available():
        base.gradient_checkpointing_enable()
        # PEFT needs input embeddings to require grad when the base is frozen
        # under gradient checkpointing; otherwise no gradient reaches adapters.
        base.enable_input_require_grads()
        # Disable KV cache — incompatible with gradient checkpointing.
        if hasattr(base, "config"):
            base.config.use_cache = False
        logger.info("Gradient checkpointing: ON")

    target_modules = (
        ["q_proj", "k_proj", "v_proj", "o_proj"]
        if args.attn_only else
        ["q_proj", "k_proj", "v_proj", "o_proj",
         "gate_proj", "up_proj", "down_proj"]
    )
    lora_cfg = LoraConfig(
        r=args.rank, lora_alpha=args.alpha,
        target_modules=target_modules,
        lora_dropout=0.05, bias="none", task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(base, lora_cfg)
    model.print_trainable_parameters()

    max_len = args.max_length

    def _format(row):
        """Tokenize (prompt, target). Mask prompt positions so the loss
        only supervises the wrapped-JSON target."""
        # Tokenize prompt alone to measure its length.
        prompt_ids = tok(
            row["prompt"], add_special_tokens=True, truncation=True, max_length=max_len,
        )["input_ids"]
        target_text = row["target"] + tok.eos_token
        target_ids = tok(
            target_text, add_special_tokens=False, truncation=True, max_length=max_len,
        )["input_ids"]
        # Concatenate; truncate to max_len.
        input_ids = (prompt_ids + target_ids)[:max_len]
        attention_mask = [1] * len(input_ids)
        # Labels: -100 over the prompt span so gradient is target-only.
        prompt_len = min(len(prompt_ids), len(input_ids))
        labels = [-100] * prompt_len + input_ids[prompt_len:]
        return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}

    train_ds = Dataset.from_list(
        [{"prompt": p, "target": t} for p, t in train_pairs]
    ).map(_format, remove_columns=["prompt", "target"])
    val_ds = None
    if val_pairs:
        val_ds = Dataset.from_list(
            [{"prompt": p, "target": t} for p, t in val_pairs]
        ).map(_format, remove_columns=["prompt", "target"])

    do_eval = val_ds is not None
    targs = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        warmup_ratio=0.1,
        weight_decay=0.01,
        logging_steps=5,
        save_strategy="epoch",
        save_total_limit=2,
        eval_strategy="epoch" if do_eval else "no",
        load_best_model_at_end=do_eval,
        metric_for_best_model="eval_loss" if do_eval else None,
        greater_is_better=False if do_eval else None,
        bf16=torch.cuda.is_available(),
        report_to="none",
        seed=0,
    )
    callbacks = []
    if do_eval and args.patience > 0:
        callbacks.append(EarlyStoppingCallback(early_stopping_patience=args.patience))

    trainer = Trainer(
        model=model, args=targs,
        train_dataset=train_ds, eval_dataset=val_ds,
        data_collator=DataCollatorForSeq2Seq(
            tok, padding=True, label_pad_token_id=-100, return_tensors="pt",
        ),
        callbacks=callbacks,
    )
    trainer.train()
    model.save_pretrained(output_dir)
    tok.save_pretrained(output_dir)
    logger.info("Saved LoRA adapter → %s", output_dir)


if __name__ == "__main__":
    main()
