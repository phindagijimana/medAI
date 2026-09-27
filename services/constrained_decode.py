"""Schema-constrained decoding for MedAI-EPI extraction.

Wraps the model generation call with an lm-format-enforcer prefix-allowed-tokens
function derived from a Pydantic model's JSON schema. Every generated token is
constrained to keep the running output on a path that will validate against the
target schema, so the raw response is JSON-valid by construction and post-hoc
repair becomes optional.

This is inference-only. It does NOT touch training weights and is composable
with the base Med42 model, the LoRA-adapted variant, or any HF causal LM.

Usage (called from Med42Backend.generate_constrained):

    from services.constrained_decode import generate_constrained
    text, n_tok = generate_constrained(
        model=hf_model,
        tokenizer=hf_tokenizer,
        prompt=prompt_str,
        pydantic_model=MriModule,        # any BaseModel subclass
        max_new_tokens=1024, seed=0,
    )

Requires: lm-format-enforcer (installed) and a Pydantic v2 BaseModel.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Type

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Lazy imports so importing this module doesn't require torch/LMFE unless used.
_LMFE_READY: Optional[bool] = None
_JsonSchemaParser = None
_build_prefix_fn = None


def _lazy_import() -> None:
    global _LMFE_READY, _JsonSchemaParser, _build_prefix_fn
    if _LMFE_READY is not None:
        return
    try:
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import (
            build_transformers_prefix_allowed_tokens_fn,
        )
        _JsonSchemaParser = JsonSchemaParser
        _build_prefix_fn = build_transformers_prefix_allowed_tokens_fn
        _LMFE_READY = True
    except ImportError as e:
        logger.warning("lm-format-enforcer unavailable: %s", e)
        _LMFE_READY = False


def is_available() -> bool:
    """True iff lm-format-enforcer is importable in this process."""
    _lazy_import()
    return bool(_LMFE_READY)


def generate_constrained(
    model: Any,
    tokenizer: Any,
    prompt: str,
    pydantic_model: Type[BaseModel],
    max_new_tokens: int = 1024,
    seed: Optional[int] = 0,
    max_input_tokens: int = 3200,
) -> tuple[str, Optional[int]]:
    """Generate a JSON string constrained to `pydantic_model`'s JSON schema.

    Returns (generated_text, n_generated_tokens). Deterministic (do_sample=False).
    Raises RuntimeError if LMFE is not installed.
    """
    _lazy_import()
    if not _LMFE_READY:
        raise RuntimeError(
            "constrained decoding requested but lm-format-enforcer is not "
            "installed. Install with: pip install 'lm-format-enforcer<0.11'"
        )
    import torch

    if seed is not None:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

    schema = pydantic_model.model_json_schema()
    parser = _JsonSchemaParser(schema)
    prefix_fn = _build_prefix_fn(tokenizer, parser)

    toks = tokenizer(
        prompt, return_tensors="pt",
        truncation=True, max_length=max_input_tokens,
    )
    model_device = next(model.parameters()).device
    for k in toks:
        if hasattr(toks[k], "to"):
            toks[k] = toks[k].to(model_device)

    input_len = toks["input_ids"].shape[1]

    with torch.no_grad():
        outputs = model.generate(
            toks["input_ids"],
            attention_mask=toks.get("attention_mask"),
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
            prefix_allowed_tokens_fn=prefix_fn,
        )

    generated_ids = outputs[0][input_len:]
    text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
    n_generated = int(outputs.shape[1] - input_len)

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return text, n_generated
