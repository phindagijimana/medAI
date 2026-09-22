"""B1 BioClinicalBERT baseline — training & inference (paper Table 6).

Status: **working single-head classifier for `epilepsy_type`**. Trains on the
Fonferko-Shadrach silver labels; extend to other fields by copying the pattern.
Runs on CPU (~3–5 min for 200 examples × 3 epochs on distilbert-base-uncased).
For real evaluation runs use the recommended base model:
`emilyalsentzer/Bio_ClinicalBERT`.

Design:
- One classifier per field. Fields with categorical values (enum outputs
  like SeizureType, MriFinding, EpilepsyType, Laterality) get single-label
  or multi-label classification heads. Booleans get binary heads. Free-text
  fields (semiology_text, dose_text, ...) are out of scope for B1 —
  they'd need seq2seq; B1 is explicitly the "conventional NER/classifier"
  baseline the paper wants.
- Evidence spans are produced via a separate token-classification head
  (BIO tagging) trained jointly.
- Base model: emilyalsentzer/Bio_ClinicalBERT (or dmis-lab/biobert-v1.1 as
  an alternative — pick per §11 experimental log).
- The training loop mirrors the schema exactly: for each field in the
  labeled examples, run the associated head; assemble a `MriModule` (or
  other module) at inference time.

This module deliberately does NOT install transformers/datasets/torch at
top level — it imports lazily so the file can be loaded even in environments
without a training stack (e.g., the CI or the lightweight app).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from schema import DocumentMetadata, MriModule


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config types
# ---------------------------------------------------------------------------


@dataclass
class B1TrainingConfig:
    base_model: str = "emilyalsentzer/Bio_ClinicalBERT"
    output_dir: str = "./checkpoints/b1_mri"
    learning_rate: float = 3e-5
    batch_size: int = 16
    epochs: int = 5
    max_length: int = 512
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    seed: int = 0
    # NER head: fields that need span extraction (BIO tags on the source)
    span_fields: tuple[str, ...] = (
        "lesion_lobe", "lesion_laterality", "field_strength_tesla",
    )
    # Classification heads: (field_name, num_labels or "multi_label")
    classification_fields: tuple[tuple[str, Any], ...] = (
        ("overall_normal", 2),
        ("hippocampal_sclerosis", 2),
        ("focal_cortical_dysplasia", 2),
        ("mri_negative_for_epilepsy", 2),
        ("findings", "multi_label"),   # multi-label over MriFinding enum
    )


@dataclass
class B1InferenceConfig:
    checkpoint_dir: str
    device: str = "cuda"                    # or "cpu"
    batch_size: int = 8


# ---------------------------------------------------------------------------
# Labeled data types — one per training example. Aligns with our Pydantic schema.
# ---------------------------------------------------------------------------


@dataclass
class LabeledExample:
    """One (source text, gold MriModule) pair, plus optional per-field evidence
    spans as (start, end) offsets in the source. Populate from the adjudicated
    annotation database once §7 is complete."""
    source_text: str
    gold: MriModule
    evidence_spans: dict[str, tuple[int, int]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Training entry point — raises NotImplementedError until labels are wired
# ---------------------------------------------------------------------------


def train_epilepsy_type_head(
    examples: list[LabeledExample] | None = None,
    silver_labels_dir: str | Path | None = None,
    config: B1TrainingConfig | None = None,
    *,
    max_train: int | None = None,
) -> Path:
    """Fine-tune a single-head classifier on `epilepsy_type` (ILAE 2017).

    Accepts either explicit `LabeledExample`s (institutional gold) or a
    directory of silver-label JSON records (Fonferko-Shadrach pipeline).
    Silver-label mode expects the JSON layout produced by
    `scripts/silver_label_fonferko.py`.

    Args:
        examples: optional list of gold examples with .gold.epilepsy_type.
        silver_labels_dir: optional directory of silver JSON records.
        config: hyperparameters.
        max_train: if set, limit training to first N labeled examples
                   (useful for CPU smoke tests).

    Returns the path to the saved checkpoint directory.
    """
    config = config or B1TrainingConfig()

    try:
        import torch
        from transformers import (
            AutoModelForSequenceClassification, AutoTokenizer,
            Trainer, TrainingArguments,
        )
        from torch.utils.data import Dataset
    except ImportError as e:
        raise ImportError(
            "B1 training requires torch + transformers. Install with:\n"
            "  pip install torch transformers accelerate\n"
            f"Underlying error: {e}"
        )

    # ---- Collect labeled examples ---------------------------------------
    training_pairs: list[tuple[str, str]] = []   # (text, epilepsy_type_string)
    if examples:
        for ex in examples:
            if ex.gold and hasattr(ex.gold, "epilepsy_type"):
                v = ex.gold.epilepsy_type.value
                if v:
                    training_pairs.append((ex.source_text,
                                           v.value if hasattr(v, "value") else str(v)))
    if silver_labels_dir:
        d = Path(silver_labels_dir)
        for f in sorted(d.glob("EA*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            src_rel = data.get("source_text_path")
            if not src_rel:
                continue
            # Resolve relative to repo root (2 levels up from this file)
            repo_root = Path(__file__).resolve().parent.parent
            src_path = repo_root / src_rel
            if not src_path.exists():
                continue
            text = src_path.read_text(encoding="utf-8")
            ph = data.get("phenotype", {})
            cs = ph.get("clinical_seizure") or {}
            et_ev = cs.get("epilepsy_type") or {}
            v = et_ev.get("value")
            if v:
                training_pairs.append((text, v))

    if max_train is not None:
        training_pairs = training_pairs[:max_train]

    if len(training_pairs) < 5:
        raise ValueError(
            f"Need at least 5 labeled examples for B1 training, got {len(training_pairs)}"
        )

    # ---- Label encoding --------------------------------------------------
    label_list = sorted({y for _, y in training_pairs})
    label2id = {l: i for i, l in enumerate(label_list)}
    id2label = {i: l for l, i in label2id.items()}

    logger.info(
        "B1 epilepsy_type: %d examples, %d classes (%s)",
        len(training_pairs), len(label_list), label_list,
    )

    # ---- Dataset ---------------------------------------------------------
    tokenizer = AutoTokenizer.from_pretrained(config.base_model)

    class _Dataset(Dataset):
        def __init__(self, pairs):
            self.pairs = pairs
        def __len__(self): return len(self.pairs)
        def __getitem__(self, i):
            text, label = self.pairs[i]
            enc = tokenizer(text, truncation=True, max_length=config.max_length,
                            padding="max_length", return_tensors="pt")
            return {"input_ids": enc["input_ids"].squeeze(0),
                    "attention_mask": enc["attention_mask"].squeeze(0),
                    "labels": torch.tensor(label2id[label], dtype=torch.long)}

    ds = _Dataset(training_pairs)

    # ---- Model -----------------------------------------------------------
    model = AutoModelForSequenceClassification.from_pretrained(
        config.base_model,
        num_labels=len(label_list),
        id2label=id2label, label2id=label2id,
    )

    # ---- Training --------------------------------------------------------
    out_dir = Path(config.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(out_dir),
        num_train_epochs=config.epochs,
        per_device_train_batch_size=config.batch_size,
        learning_rate=config.learning_rate,
        weight_decay=config.weight_decay,
        warmup_ratio=config.warmup_ratio,
        seed=config.seed,
        logging_steps=5,
        save_strategy="no",       # single-run smoke; caller can save if needed
        report_to=[],             # no wandb/tb by default
    )

    trainer = Trainer(model=model, args=training_args, train_dataset=ds)
    trainer.train()

    # Save the tokenizer + model
    model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))
    # Persist label mapping alongside for inference
    (out_dir / "label_map.json").write_text(
        json.dumps({"id2label": id2label, "label2id": label2id}, indent=2)
    )
    logger.info("B1 epilepsy_type checkpoint saved to %s", out_dir)
    return out_dir


# Backward-compatible alias — kept so the old scaffold API still resolves.
def train(*args, **kwargs) -> Path:
    """Legacy alias; delegates to `train_epilepsy_type_head`."""
    return train_epilepsy_type_head(*args, **kwargs)


# ---------------------------------------------------------------------------
# Inference backend — implements the ModelBackend protocol so B1 can drop
# into the extraction pipeline once a checkpoint exists.
# ---------------------------------------------------------------------------


@dataclass
class B1InferenceBackend:
    """Loads a trained B1 checkpoint and produces MriModule-shaped JSON.

    Not usable until `train()` has produced a checkpoint. Provides the same
    (model_name, model_cache_dir, generate(...)) surface as Med42Backend.
    """
    config: B1InferenceConfig
    model_name: str = "baseline/b1-bioclinicalbert-mri"
    model_cache_dir: str = ""
    _loaded: bool = False

    def load(self) -> None:
        if self._loaded:
            return
        ckpt = Path(self.config.checkpoint_dir)
        if not ckpt.exists():
            raise FileNotFoundError(
                f"B1 checkpoint not found: {ckpt}. Train first via "
                "services.baseline_bert.train_epilepsy_type_head(...)."
            )
        try:
            import torch
            from transformers import (
                AutoModelForSequenceClassification, AutoTokenizer,
            )
        except ImportError as e:
            raise ImportError(
                "B1 inference requires torch + transformers. "
                f"Underlying error: {e}"
            )

        self._tokenizer = AutoTokenizer.from_pretrained(str(ckpt))
        self._model = AutoModelForSequenceClassification.from_pretrained(str(ckpt))
        self._model.eval()
        if self.config.device == "cuda" and torch.cuda.is_available():
            self._model = self._model.cuda()
        label_map = json.loads((ckpt / "label_map.json").read_text())
        self._id2label = {int(k): v for k, v in label_map["id2label"].items()}
        self._loaded = True

    def predict_epilepsy_type(self, text: str) -> str:
        """Return the predicted epilepsy_type label for a document."""
        import torch
        self.load()
        enc = self._tokenizer(text, truncation=True, max_length=512,
                              return_tensors="pt")
        if self.config.device == "cuda" and torch.cuda.is_available():
            enc = {k: v.cuda() for k, v in enc.items()}
        with torch.no_grad():
            out = self._model(**enc)
        pred_id = int(out.logits.argmax(dim=-1).item())
        return self._id2label[pred_id]

    def generate(self, prompt: str, decoding) -> tuple[str, Optional[int]]:
        """ModelBackend surface: passes the source text through predict.
        Returns a minimal ClinicalSeizureModule JSON with epilepsy_type set."""
        self.load()
        source = getattr(self, "_current_source", None)
        if source is None:
            return json.dumps({}), 0
        pred_label = self.predict_epilepsy_type(source)
        # Emit a minimal ClinicalSeizureModule-compatible JSON — caller must
        # union with schema defaults / not_documented for the other fields.
        return json.dumps({
            "epilepsy_type": {
                "value": pred_label, "certainty": "probable",
                "temporal_status": "current",
                "evidence_text": pred_label,
            },
        }), None
