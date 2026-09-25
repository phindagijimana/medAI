"""DeepSeek-R1-Distill-Llama-8B backend for the extraction pipeline.

Implements the same `ModelBackend` protocol as `services/med42_backend.py`
so `services/router.py::extract_phenotype` can drive DeepSeek unchanged.

Purpose in the paper:
    Serves as a second locally-deployable 8 B-tier model for the
    extractor comparison. Answers §Limitations #2 — "is schema-echo
    Med42-specific, or characteristic of the 8 B open-weight tier?".
    Also serves as the verifier partner in `services/llm_verifier.py`
    (Med42 extracts → DeepSeek verifies, and reverse).

Model:
    `deepseek-ai/DeepSeek-R1-Distill-Llama-8B` on Hugging Face — Llama-3
    tokenizer + architecture, distilled from DeepSeek-R1 for reasoning.
    Fits ~16 GB VRAM in bfloat16, runs on the same L40S 24 GB slice as
    Med42-8B.

The backend is lazy — nothing loads until `.load()` is called or the first
`.generate()`. Loading takes ~10-20 s the first time (weights are cached
locally under `MED42_MODEL_CACHE_DIR`).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from services.extract import DecodingConfig

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "deepseek-ai/DeepSeek-R1-Distill-Llama-8B"


class DeepSeekBackend:
    """Deterministic-decoding local-inference backend for DeepSeek-R1-Distill-Llama-8B."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_ID,
        model_cache_dir: str | None = None,
        device: str | None = None,
    ):
        self.model_name: str = model_name
        self.model_cache_dir: str = model_cache_dir or os.environ.get(
            "MED42_MODEL_CACHE_DIR", "model_cache",
        )
        # Device selection follows the same MEDAI_DEVICE convention as
        # services/med42_model.py so a single env var controls the whole stack.
        env_dev = (os.environ.get("MEDAI_DEVICE") or "auto").strip().lower()
        try:
            import torch
        except ImportError as e:
            raise RuntimeError("torch not installed") from e
        cuda_ok = bool(torch.cuda.is_available())
        if device:
            self._device = device
        elif env_dev == "cuda":
            if not cuda_ok:
                raise RuntimeError("MEDAI_DEVICE=cuda but CUDA is not available.")
            self._device = "cuda"
        elif env_dev == "cpu":
            self._device = "cpu"
            logger.warning("DeepSeekBackend on CPU — expect ~5-15 min per call.")
        else:
            self._device = "cuda" if cuda_ok else "cpu"
        self._model = None
        self._tokenizer = None
        self._torch = torch

    def load(self) -> None:
        """Explicit load. Idempotent — no-op if already loaded."""
        if self._model is not None:
            return
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as e:
            raise RuntimeError("transformers not installed") from e
        torch = self._torch
        logger.info(
            "DeepSeekBackend.load model=%s device=%s cache_dir=%s",
            self.model_name, self._device, self.model_cache_dir,
        )
        tok = AutoTokenizer.from_pretrained(
            self.model_name, trust_remote_code=True,
            cache_dir=self.model_cache_dir,
        )
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        dtype = torch.bfloat16 if self._device == "cuda" else torch.float32
        model = AutoModelForCausalLM.from_pretrained(
            self.model_name, trust_remote_code=True,
            torch_dtype=dtype, cache_dir=self.model_cache_dir,
            low_cpu_mem_usage=True,
        )
        if self._device == "cuda":
            model = model.cuda()
        model.eval()
        self._model = model
        self._tokenizer = tok
        logger.info("DeepSeekBackend.load complete")

    def generate(
        self, prompt: str, decoding: DecodingConfig,
    ) -> tuple[str, Optional[int]]:
        if self._model is None:
            self.load()
        torch = self._torch
        tok = self._tokenizer
        model = self._model

        if decoding.seed is not None:
            torch.manual_seed(decoding.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(decoding.seed)

        max_input_tokens = 3200
        toks = tok(
            prompt, return_tensors="pt",
            truncation=True, max_length=max_input_tokens,
        )
        model_device = next(model.parameters()).device
        for k in toks:
            if hasattr(toks[k], "to"):
                toks[k] = toks[k].to(model_device)

        gen_kwargs = {
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

        input_token_count = toks["input_ids"].shape[1]
        logger.info(
            "DeepSeekBackend.generate input_tokens=%d max_new=%d do_sample=%s seed=%s",
            input_token_count, decoding.max_new_tokens,
            decoding.do_sample, decoding.seed,
        )
        with torch.no_grad():
            outputs = model.generate(
                toks["input_ids"],
                attention_mask=toks.get("attention_mask"),
                **gen_kwargs,
            )
        generated_ids = outputs[0][input_token_count:]
        text = tok.decode(generated_ids, skip_special_tokens=True).strip()
        n_generated = int(outputs.shape[1] - input_token_count)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return text, n_generated
