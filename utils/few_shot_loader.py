"""
Load few-shot examples from data/few_shot_examples.json and static guideline snippets
from data/guidelines/neurology_guidelines.json for prompt augmentation.
"""
from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path
from typing import Any

logger = logging.getLogger("vectaai")

_CONDITION_TO_GUIDELINE = {
    "epilepsy": "epilepsy_guidelines",
    "parkinsons": "parkinsons_guidelines",
    "stroke": "stroke_guidelines",
    "headache": "headache_guidelines",
}


def _app_home() -> Path:
    return Path(os.environ.get("APP_HOME", os.getcwd())).resolve()


class FewShotExampleLoader:
    def __init__(self) -> None:
        self._examples_root: dict[str, Any] | None = None
        self._guidelines: dict[str, Any] | None = None
        self._examples_path = _app_home() / "data" / "few_shot_examples.json"
        self._guidelines_path = _app_home() / "data" / "guidelines" / "neurology_guidelines.json"

    def _load_examples(self) -> None:
        if self._examples_root is not None:
            return
        if not self._examples_path.is_file():
            logger.warning("few_shot_examples.json not found: %s", self._examples_path)
            self._examples_root = {}
            return
        with open(self._examples_path, encoding="utf-8") as f:
            data = json.load(f)
        self._examples_root = data.get("neurology_few_shot_examples") or {}
        logger.debug("Loaded few-shot conditions: %s", list(self._examples_root.keys()))

    def _load_guidelines(self) -> None:
        if self._guidelines is not None:
            return
        if not self._guidelines_path.is_file():
            logger.warning("neurology_guidelines.json not found: %s", self._guidelines_path)
            self._guidelines = {}
            return
        with open(self._guidelines_path, encoding="utf-8") as f:
            full = json.load(f)
        self._guidelines = {k: v for k, v in full.items() if k != "metadata"}

    def get_examples_by_condition(
        self,
        condition: str,
        n: int = 2,
        analysis_type: str = "classification",
    ) -> list[dict[str, Any]]:
        self._load_examples()
        assert self._examples_root is not None
        pool = self._examples_root.get(condition)
        if not pool:
            return []
        typed = [e for e in pool if e.get("analysis_type") == analysis_type]
        use = typed if typed else list(pool)
        k = max(1, min(int(n), len(use)))
        rng = random.Random(42)
        if len(use) <= k:
            return list(use)
        return rng.sample(use, k)

    def format_few_shot_examples_for_prompt(
        self,
        examples: list[dict[str, Any]],
        analysis_type: str = "classification",
    ) -> str:
        if not examples:
            return ""
        lines = [
            "📋 FEW-SHOT REFERENCE EXAMPLES (patterns only; do not copy patient identifiers):",
            "",
        ]
        for ex in examples:
            eid = ex.get("id", "?")
            inp = (ex.get("input") or "").strip()
            if len(inp) > 1200:
                inp = inp[:1200] + "…"
            lines.append(f"** Example {eid} **")
            lines.append(f"Input: {inp}")
            eo = ex.get("expected_output")
            if isinstance(eo, dict):
                parts = [f"{k}: {v}" for k, v in eo.items() if v]
                lines.append("Expected output shape: " + " | ".join(parts[:6]))
            lines.append("")
        return "\n".join(lines).strip()

    def get_guideline_context(self, condition: str, max_chars: int = 4500) -> str:
        gkey = _CONDITION_TO_GUIDELINE.get(condition)
        if not gkey:
            return ""
        self._load_guidelines()
        assert self._guidelines is not None
        block = self._guidelines.get(gkey)
        if not block:
            return ""
        try:
            text = json.dumps(block, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(block)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n… [truncated]"
        return text

    def reload(self) -> None:
        """Clear caches (e.g. after learning cycle updates examples file)."""
        self._examples_root = None
        self._guidelines = None
        self._load_examples()
        self._load_guidelines()
