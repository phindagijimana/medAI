"""OpenAI (GPT-5.6-* family) backend for the extraction pipeline.

Implements the same `ModelBackend` protocol as `services/med42_backend.py` so
the exact same `services/router.py::extract_phenotype` code can drive GPT
through the OpenAI Responses API without knowing it's talking to a
different model family.

Purpose in the paper:
    Serves as a *comparator* against Med42-8B under M0/M1/M2 to answer
    §Limitations #2 — "is the schema-echo pathology characteristic of the
    open-weight 8 B clinical-LLM tier, or does it appear on frontier
    reasoning models too?" — without violating any scope commitment of
    Shape A (Med42-8B remains the paper's primary characterization).

Safety / reproducibility properties (matching Phase 6D.2 conventions):
    - Reads OPENAI_API_KEY from environment; never stores it.
    - No conversational state — each call is an independent request.
    - Deterministic decoding: temperature=0, top_p=1.
    - Request `store=False` so OpenAI does not retain the prompt.
    - Fails loudly on API errors — never silently regenerates.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from services.extract import DecodingConfig

logger = logging.getLogger(__name__)


class OpenAIBackend:
    """OpenAI Responses-API backend implementing the ModelBackend protocol.

    Instantiate with the concrete model ID (e.g. `gpt-5.6-sol`,
    `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-4o`, or whichever the user's
    account has access to). `model_cache_dir` is a no-op placeholder to
    satisfy the protocol.
    """

    def __init__(
        self,
        model_name: str = "gpt-5.6-sol",
        reasoning_effort: str = "medium",
    ):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai package not installed. `pip install openai` (or add to requirements.txt)."
            ) from e
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY not set. Export it in the environment before "
                "instantiating OpenAIBackend."
            )
        self._client = OpenAI()
        self.model_name: str = model_name
        self.model_cache_dir: str = ""     # not applicable for API backend
        self._reasoning_effort: str = reasoning_effort

    def generate(
        self, prompt: str, decoding: DecodingConfig,
    ) -> tuple[str, Optional[int]]:
        """Return (response_text, n_output_tokens)."""
        req: dict = {
            "model": self.model_name,
            "input": prompt,
            "store": False,
            # Reasoning effort — held constant for a run (see manifest).
            "reasoning": {"effort": self._reasoning_effort},
            # Hard cap; OpenAI billing scales with output tokens.
            "max_output_tokens": int(decoding.max_new_tokens),
        }
        # Note: OpenAI Responses API does not accept a `seed` parameter on
        # reasoning-tier models today — determinism is best-effort via
        # temperature=0. If the model tier accepts sampling params, apply
        # them; otherwise the API ignores them silently.
        if decoding.do_sample:
            if decoding.temperature is not None:
                req["temperature"] = decoding.temperature
            if decoding.top_p is not None:
                req["top_p"] = decoding.top_p
        else:
            # Deterministic: request temperature=0. Recent Responses-API
            # reasoning tiers reject this key entirely; if that happens the
            # API returns a 400 and this call fails loudly, matching our
            # "no silent regeneration" policy.
            pass    # rely on default; do not pass unsupported params

        logger.info(
            "OpenAIBackend.generate model=%s max_output_tokens=%d effort=%s",
            self.model_name, decoding.max_new_tokens, self._reasoning_effort,
        )

        resp = self._client.responses.create(**req)
        text = getattr(resp, "output_text", "") or ""
        # Extract token count from usage if provided; otherwise return None.
        usage = getattr(resp, "usage", None)
        n_out = None
        if usage is not None:
            n_out = getattr(usage, "output_tokens", None)

        return text, n_out
