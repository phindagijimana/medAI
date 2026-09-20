"""Extraction pipeline: prompt → generate → validate → repair → log (paper §11).

Public entry point:

    result = extract_module(
        module_cls=MriModule,
        prompt=MRI_M2_V1,
        source_text=...,
        source_doc_meta=DocumentMetadata(...),
        model_backend=some_backend,
    )
    result.manifest.write()

The pipeline deliberately emits free-form text and validates afterwards
(no token-level constrained decoding), because the paper measures raw
validity separately from repaired validity per §11.

Repair is a bounded, well-defined sequence of deterministic strategies —
never a "keep asking the model" loop that could contaminate raw-validity
numbers.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, Type

from pydantic import BaseModel, ValidationError

from schema import DocumentMetadata, Evidence, DocumentType, Certainty, TemporalStatus

from .prompt_registry import PromptTemplate, module_schema_for
from .run_manifest import DecodingConfig, ManifestBuilder, RunManifest


# ---------------------------------------------------------------------------
# Model backend protocol — separates prompt construction from model I/O
# so we can smoke-test without loading Med42.
# ---------------------------------------------------------------------------


class ModelBackend(Protocol):
    """Any object that turns a prompt string into a response string."""

    model_name: str
    model_cache_dir: str

    def generate(self, prompt: str, decoding: DecodingConfig) -> tuple[str, int | None]:
        """Return (response_text, n_generated_tokens_if_known)."""
        ...


# ---------------------------------------------------------------------------
# Result object
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    manifest: RunManifest
    module: BaseModel | None    # populated iff manifest.final_valid


# ---------------------------------------------------------------------------
# Repair strategies (ordered, deterministic)
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _strip_code_fence(text: str) -> str | None:
    m = _FENCE_RE.search(text)
    return m.group(1).strip() if m else None


def _extract_first_json_object(text: str) -> str | None:
    """Grab the largest {...} span. Balanced-brace scan handles nested objects."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _try_parse(module_cls: Type[BaseModel], text: str) -> tuple[BaseModel | None, str | None]:
    try:
        return module_cls.model_validate_json(text), None
    except ValidationError as e:
        return None, str(e)[:2000]
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"[:2000]


def _repair(module_cls: Type[BaseModel], raw: str) -> tuple[BaseModel | None, str, int, str | None]:
    """Try repair strategies in order. Return (parsed_or_none, method, attempts, error)."""
    attempts = 0

    # Strategy 1: strip code fences
    stripped = _strip_code_fence(raw)
    if stripped is not None:
        attempts += 1
        parsed, err = _try_parse(module_cls, stripped)
        if parsed is not None:
            return parsed, "strip_code_fence", attempts, None

    # Strategy 2: extract first balanced JSON object
    obj_span = _extract_first_json_object(raw)
    if obj_span is not None:
        attempts += 1
        parsed, err = _try_parse(module_cls, obj_span)
        if parsed is not None:
            return parsed, "regex_json_extraction", attempts, None

    # Strategy 3: extract from within a code fence (already tried), then json-extract
    if stripped is not None:
        obj_span = _extract_first_json_object(stripped)
        if obj_span is not None:
            attempts += 1
            parsed, err = _try_parse(module_cls, obj_span)
            if parsed is not None:
                return parsed, "strip_fence_then_regex", attempts, err

    return None, "failed", attempts, err if attempts else "no_json_found"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def extract_module(
    *,
    module_cls: Type[BaseModel],
    prompt: PromptTemplate,
    source_text: str,
    source_doc_meta: DocumentMetadata,
    model_backend: ModelBackend,
    decoding: DecodingConfig | None = None,
    schema_version: str,
    inject_schema: bool | None = None,      # None ⇒ inject iff arm=="M2"
) -> ExtractionResult:
    """Run one prompt → module extraction.

    Note: the module_cls emitted here is the module (e.g. MriModule), which
    the extraction expresses in its own JSON schema. The document metadata is
    kept alongside for provenance and to fill in missing Evidence.source_*
    fields if the model omits them.
    """
    if decoding is None:
        decoding = DecodingConfig(
            do_sample=False, temperature=None, top_p=None,
            max_new_tokens=1024, seed=0,
        )

    if inject_schema is None:
        inject_schema = prompt.arm == "M2"
    schema_dict = module_schema_for(module_cls) if inject_schema else None

    full_prompt = prompt.render(source_text=source_text, module_schema=schema_dict)

    mb = ManifestBuilder.start(
        schema_version=schema_version,
        prompt=prompt,
        model_name=model_backend.model_name,
        model_cache_dir=model_backend.model_cache_dir,
        decoding=decoding,
        source_doc_id=source_doc_meta.doc_id,
        source_doc_type=source_doc_meta.doc_type.value,
        source_length_chars=len(source_text),
        arm=prompt.arm,
    )

    response, n_tokens = model_backend.generate(full_prompt, decoding)

    # First attempt — raw parse
    parsed_raw, err = _try_parse(module_cls, response)
    if parsed_raw is not None:
        # Fill missing Evidence source_* fields from doc metadata if the model
        # didn't emit them. This is a best-effort convenience — required by
        # the Evidence validator, so absent-field responses will fail parsing;
        # patching is done here only if the model emitted them wrong-but-close.
        # In practice today we require the model to emit them via the schema.
        mb.record_raw(
            response, n_tokens=n_tokens, raw_valid=True,
            parsed_value=parsed_raw.model_dump(mode="json"),
        )
        manifest = mb.finish()
        return ExtractionResult(manifest=manifest, module=parsed_raw)

    # Raw parse failed. Try repair.
    mb.record_raw(response, n_tokens=n_tokens, raw_valid=False, parse_error=err)
    repaired, method, attempts, err2 = _repair(module_cls, response)
    mb.record_repair(
        method=method,
        attempts=attempts,
        final_valid=repaired is not None,
        parsed_value=repaired.model_dump(mode="json") if repaired is not None else None,
        parse_error=err2,
    )
    manifest = mb.finish()
    return ExtractionResult(manifest=manifest, module=repaired)


# ---------------------------------------------------------------------------
# Convenience helper: fill missing Evidence source metadata from doc.
# The model's schema-conforming JSON must include source_doc_id/type/date on
# every Evidence object; helper below reconstructs Evidence source metadata
# from DocumentMetadata for offline mocking.
# ---------------------------------------------------------------------------


def evidence_boilerplate(doc: DocumentMetadata) -> dict[str, Any]:
    return {
        "source_doc_id": doc.doc_id,
        "source_doc_type": doc.doc_type.value,
        "source_date": doc.doc_date.isoformat(),
    }


def not_documented_evidence(doc: DocumentMetadata) -> dict[str, Any]:
    """Return a JSON-compatible dict for a `not_documented` Evidence[T]."""
    return {
        "value": None,
        "certainty": Certainty.NOT_DOCUMENTED.value,
        "temporal_status": TemporalStatus.UNSPECIFIED.value,
        "evidence_text": None,
        **evidence_boilerplate(doc),
    }
