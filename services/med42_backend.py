"""Med42 backend adapter for the extraction pipeline (paper §10, §20).

Implements the `ModelBackend` protocol in services/extract.py by wrapping
the existing Med42ModelService with deterministic decoding suitable for
evaluation runs. The existing app's Med42ModelService uses sampling-based
decoding (temperature=0.3, do_sample=True) which is fine for interactive
use but not acceptable for locked-eval reproducibility — this adapter
overrides those defaults per-call from `DecodingConfig`.

Not modifying Med42ModelService directly because it's still used by the
Flask app; the adapter isolates eval-mode decoding.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Type

from pydantic import BaseModel

from services.med42_model import Med42ModelService
from services.extract import DecodingConfig

logger = logging.getLogger(__name__)


class Med42Backend:
    """Deterministic-decoding wrapper around Med42ModelService."""

    def __init__(self, service: Med42ModelService):
        if not service.model_loaded:
            raise RuntimeError(
                "Med42ModelService.load_model() must succeed before wrapping in Med42Backend"
            )
        self._svc = service
        self.lora_adapter_dir: Optional[str] = service.lora_adapter_dir
        # When a LoRA is loaded, decorate model_name so manifests distinguish
        # tuned from base runs at a glance (e.g. "…-8B+lora:pilot_v1").
        if service.lora_loaded and service.lora_adapter_dir:
            adapter_tag = service.lora_adapter_dir.rstrip("/").split("/")[-1]
            self.model_name: str = f"{service.model_name}+lora:{adapter_tag}"
        else:
            self.model_name: str = service.model_name
        self.model_cache_dir: str = service.config.model_cache_dir or ""

    def generate(self, prompt: str, decoding: DecodingConfig) -> tuple[str, Optional[int]]:
        import torch

        model = self._svc.model
        tok = self._svc.tokenizer

        # Seed if requested (deterministic decoding still benefits from a seed
        # for any stochastic model-internal ops on some backends).
        if decoding.seed is not None:
            torch.manual_seed(decoding.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(decoding.seed)

        # Tokenize — keep the same context envelope Med42ModelService uses.
        max_input_tokens = 3200
        toks = tok(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=max_input_tokens,
        )

        model_device = next(model.parameters()).device
        for k in toks:
            if hasattr(toks[k], "to"):
                toks[k] = toks[k].to(model_device)

        gen_kwargs: dict = {
            "max_new_tokens": decoding.max_new_tokens,
            "do_sample": decoding.do_sample,
            "pad_token_id": tok.eos_token_id,
            "eos_token_id": tok.eos_token_id,
        }
        if decoding.do_sample:
            if decoding.temperature is not None:
                gen_kwargs["temperature"] = decoding.temperature
            if decoding.top_p is not None:
                gen_kwargs["top_p"] = decoding.top_p
        if decoding.repetition_penalty is not None:
            gen_kwargs["repetition_penalty"] = decoding.repetition_penalty

        input_token_count = toks["input_ids"].shape[1]

        logger.info(
            "Med42Backend.generate input_tokens=%d max_new=%d do_sample=%s seed=%s",
            input_token_count,
            decoding.max_new_tokens,
            decoding.do_sample,
            decoding.seed,
        )

        with torch.no_grad():
            outputs = model.generate(
                toks["input_ids"],
                attention_mask=toks.get("attention_mask"),
                **gen_kwargs,
            )

        generated_ids = outputs[0][input_token_count:]
        generated_text = tok.decode(generated_ids, skip_special_tokens=True).strip()
        n_generated = int(outputs.shape[1] - input_token_count)

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return generated_text, n_generated

    def generate_constrained(
        self,
        prompt: str,
        pydantic_model: Type[BaseModel],
        decoding: DecodingConfig,
    ) -> tuple[str, Optional[int]]:
        """Schema-constrained generation. Output is JSON-valid against
        `pydantic_model` by construction (lm-format-enforcer prefix mask).

        Falls back to the standard `generate()` if LMFE is unavailable — the
        caller can still recover via the smart-repair chain.
        """
        from services.constrained_decode import generate_constrained, is_available
        if not is_available():
            logger.warning(
                "generate_constrained called but LMFE not installed; "
                "falling back to standard decoding."
            )
            return self.generate(prompt, decoding)
        return generate_constrained(
            model=self._svc.model,
            tokenizer=self._svc.tokenizer,
            prompt=prompt,
            pydantic_model=pydantic_model,
            max_new_tokens=decoding.max_new_tokens,
            seed=decoding.seed,
        )
