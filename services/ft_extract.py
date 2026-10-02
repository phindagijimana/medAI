"""Inference contract for the LoRA-tuned Med42-8B adapters (Arm H).

The adapters (``scripts/finetune_lora_epi.py``) were trained on ONE prompt:
the whole ``EpilepsyPhenotype`` JSON in a single generation, with a
``PATIENT_ID:`` line prepended to the note.  They were never trained on the
per-module M0/M1/M2 prompts.

Evaluating a tuned adapter through the M-arm prompts (what
``scripts/run_med42_on_fs_test.py`` does) is therefore an out-of-contract
test: with M2 every response is the JSON Schema echoed back until the
4096-token limit, which ``smart_repair`` then wraps into an empty module
that counts as "valid" (see ``docs/EVAL_PROTOCOL_LEO.md``, finding F1).

This module is the in-contract path: same template as training, one
generation per letter, then per-module validation with ``smart_repair``.
It has no torch import so tests and scorers can use it on CPU.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Optional

# Keep byte-identical to scripts/finetune_lora_epi.py::PROMPT_TEMPLATE.
# tests/test_ft_extract.py asserts this against the training script's text.
FT_PROMPT_TEMPLATE = (
    "Extract the epilepsy phenotype from this clinical text into the "
    "MedAI-EPI v0.2.1 JSON schema. Return only valid JSON.\n\n"
    "Clinical text:\n\"\"\"\n{note}\n\"\"\"\n\n"
    "Phenotype JSON:\n"
)

FT_PROMPT_ID = "epilepsy_phenotype.FT.v1"
FT_ARM = "FT"


def build_ft_prompt(note: str, patient_id: Optional[str] = None) -> str:
    """Training-time prompt.  ``patient_id`` reproduces the ID augmentation
    (the adapter learned to copy it into every ID field)."""
    if patient_id:
        note = f"PATIENT_ID: {patient_id}\n\n{note}"
    return FT_PROMPT_TEMPLATE.format(note=note)


def _first_json_object(text: str) -> Optional[str]:
    from services.extract import _extract_first_json_object, _strip_code_fence
    fenced = _strip_code_fence(text)
    return _extract_first_json_object(fenced if fenced else text)


def _null_evidence(doc_id: str) -> dict:
    return {"value": None, "certainty": "not_documented", "temporal_status": "unspecified",
            "evidence_text": None, "source_doc_id": doc_id,
            "source_doc_type": "progress_note", "source_date": "2024-01-01"}


def validate_with_salvage(cls: Any, sub: dict, doc_id: str, max_rounds: int = 16):
    """Validate one module, dropping only the fields that fail.

    A single out-of-vocabulary enum (the adapter wrote ``etiology_category =
    "undefined"``) would otherwise discard every correct field in the module.
    A failing field is replaced by a not-documented placeholder (``[]`` for
    list fields) and validation is retried.  Returns ``(module | None,
    dropped_field_names)``.
    """
    from pydantic import ValidationError
    work = dict(sub)
    dropped: list[str] = []
    for _ in range(max_rounds):
        try:
            return cls.model_validate(work), dropped
        except ValidationError as e:
            bad = {str(err["loc"][0]) for err in e.errors() if err.get("loc")}
            progress = False
            for name in bad:
                if name in work and name not in dropped:
                    work[name] = [] if isinstance(work[name], list) else _null_evidence(doc_id)
                    dropped.append(name)
                    progress = True
                elif name not in work and name in cls.model_fields:
                    work[name] = _null_evidence(doc_id)
                    dropped.append(name)
                    progress = True
            if not progress:
                break
    return None, dropped


def split_phenotype(raw: str, *, doc_id: str = "x") -> dict[str, dict]:
    """Parse a full-phenotype generation into validated per-module dicts.

    Each module is validated on its own, with field-level salvage
    (:func:`validate_with_salvage`), then ``try_smart_repair`` as a last
    resort.  Modules that still fail are absent - never partially populated.
    """
    from schema import DocumentMetadata, DocumentType
    from services.router import MODULE_CLASSES
    from services.smart_repair import try_smart_repair

    blob = _first_json_object(raw or "")
    if not blob:
        return {}
    try:
        obj = json.loads(blob)
    except Exception:
        try:
            import json_repair  # type: ignore
            obj = json_repair.loads(blob)
        except Exception:
            return {}
    if not isinstance(obj, dict):
        return {}

    doc = DocumentMetadata(doc_id=doc_id, patient_id=doc_id,
                           doc_type=DocumentType.PROGRESS_NOTE, doc_date=date(2024, 1, 1))
    out: dict[str, dict] = {}
    for name, cls in MODULE_CLASSES.items():
        sub = obj.get(name)
        if not isinstance(sub, dict):
            continue
        validated, _dropped = validate_with_salvage(cls, sub, doc_id)
        if validated is None:
            validated, _raw, _err = try_smart_repair(json.dumps(sub), cls, doc)
        if validated is not None:
            out[name] = validated.model_dump(mode="json")
    return out


_EVIDENCE_LIKE = re.compile(r"populated")


def populated_fields(module: Optional[dict]) -> int:
    """Number of Evidence slots with a non-null value in one module dict."""
    n = 0
    for v in (module or {}).values():
        if isinstance(v, dict) and v.get("value") not in (None, [], {}):
            n += 1
        elif isinstance(v, list):
            n += sum(1 for e in v if isinstance(e, dict) and e.get("value") not in (None, [], {}))
    return n


def is_degenerate(modules: dict[str, dict]) -> bool:
    """True when nothing at all was extracted (the 'valid but empty' case)."""
    return not any(populated_fields(m) for m in modules.values())


def generate_ft(backend: Any, note: str, patient_id: str, *, max_new_tokens: int = 4096,
                seed: int = 0) -> tuple[str, Optional[int]]:
    """One in-contract generation (greedy).  ``backend`` is a Med42Backend."""
    from services.extract import DecodingConfig
    decoding = DecodingConfig(do_sample=False, temperature=None, top_p=None,
                              max_new_tokens=max_new_tokens, seed=seed, constrained=False)
    return backend.generate(build_ft_prompt(note, patient_id), decoding)


__all__ = [
    "FT_ARM", "FT_PROMPT_ID", "FT_PROMPT_TEMPLATE", "build_ft_prompt",
    "generate_ft", "is_degenerate", "populated_fields", "split_phenotype",
    "validate_with_salvage",
]
