"""B1 BioClinicalBERT baseline — training & inference scaffold (paper Table 6).

Status: **scaffold only**. Training requires an adjudicated labeled corpus
that does not exist yet. When labels are ready, callers instantiate a
`B1TrainingConfig` and call `train()`; the checkpoint is then loaded by
`B1InferenceBackend` (a `ModelBackend` implementation) so B1 plugs into the
same extraction pipeline as the LLM arms.

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


def train(
    examples: list[LabeledExample],
    config: B1TrainingConfig | None = None,
) -> Path:
    """Fine-tune a BioClinicalBERT with one classifier head per field.

    Returns the path to the saved checkpoint directory.

    **Not runnable until adjudicated labels exist** — see paper §7 (annotation
    study). This function raises `NotImplementedError` if called with an empty
    example list, and raises `MissingDependencyError` if the training stack
    isn't installed.
    """
    config = config or B1TrainingConfig()
    if not examples:
        raise NotImplementedError(
            "B1 training scaffold: no labeled examples provided. This baseline "
            "requires an adjudicated annotation corpus per paper §7. Steps to "
            "make this runnable: (1) complete pilot annotation and adjudication, "
            "(2) load examples via LabeledExample(source_text=..., gold=MriModule(...)), "
            "(3) call B1 train() with the list."
        )

    try:
        import torch  # noqa: F401
        from transformers import (  # noqa: F401
            AutoModel, AutoTokenizer, TrainingArguments, Trainer,
        )
    except ImportError as e:
        raise ImportError(
            "B1 training requires torch + transformers. Install with:\n"
            "  pip install torch transformers datasets accelerate\n"
            f"Underlying error: {e}"
        )

    # ------------------------------------------------------------------
    # Actual training loop lives here. Sketch:
    #
    #   1. Tokenize source_text per example (max_length=config.max_length).
    #   2. Assemble per-head labels:
    #        - Classification heads: y_i = 0/1/index for each labeled example
    #          drawn from example.gold.<field>.value.
    #        - Multi-label heads (findings): multi-hot over MriFinding enum
    #          from example.gold.findings.
    #        - Span heads: BIO-tag sequences from example.evidence_spans.
    #   3. Build a shared BERT encoder with N heads on top.
    #   4. Combined loss = sum of head losses with equal weight (tuneable).
    #   5. Trainer / TrainingArguments per config.
    #   6. Save to config.output_dir; return that path.
    # ------------------------------------------------------------------

    raise NotImplementedError(
        "B1 training loop is scaffolded but not implemented. "
        "Implementation is intentionally deferred until (a) the annotated "
        "corpus is available and (b) the eval harness gold format is frozen "
        "against SCHEMA_V0_2. Track: [[paper1-scope-minimum-no-ft]]."
    )


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
                f"B1 checkpoint not found: {ckpt}. Train the model first via "
                "services.baseline_bert.train(...)."
            )
        try:
            import torch  # noqa: F401
            from transformers import AutoModel, AutoTokenizer  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "B1 inference requires torch + transformers. "
                f"Underlying error: {e}"
            )
        # Actual load logic goes here when train() is implemented.
        raise NotImplementedError(
            "B1 inference not implemented; train() must be implemented first."
        )

    def generate(self, prompt: str, decoding) -> tuple[str, Optional[int]]:
        self.load()
        # Unreachable until load() is implemented; kept for interface stability.
        return json.dumps({}), 0
