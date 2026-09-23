"""Smart repair for LLM outputs that emit bare values instead of Evidence-wrapped.

Med42-8B (and most 8B clinical LLMs) frequently emit valid JSON that ships
raw enum values directly (e.g. `"epilepsy_type": "focal"`) instead of the
`Evidence[T]` structure our schema requires (value + certainty + temporal +
evidence_text + source metadata). This module deterministically:

1. Parses the raw response as JSON (via the existing repair chain).
2. Walks the parsed dict and, for each field the schema expects to be
   `Evidence[T]`, checks whether the value is bare vs. already-wrapped.
3. If bare: wraps it with default Evidence metadata (source_* filled from
   `DocumentMetadata`, certainty="possible", evidence_text set to the
   value's own string form as a minimal-sufficient placeholder).
4. Normalizes enum-valued strings against the canonical schema enums
   (case-insensitive, whitespace-tolerant, plus a small synonym table for
   common LLM outputs like "tonic clonic" → "generalized_tonic_clonic").

The repair is per-module. The paper's raw-validity numbers are unchanged;
this contributes a separate `smart_repair_valid` field to the run manifest.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Type

from pydantic import BaseModel, ValidationError

from schema import (
    ClinicalSeizureModule,
    DocumentMetadata,
    EegModule,
    IntegratedPhenotypeModule,
    MedicationModule,
    MriModule,
    ClinicalLocalizationModule,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enum-normalization table.
# Common LLM-emitted variants → canonical schema enum value.
# ---------------------------------------------------------------------------

_ENUM_SYNONYMS: dict[str, str] = {
    # SeizureType
    "tonic clonic": "generalized_tonic_clonic",
    "tonic-clonic": "generalized_tonic_clonic",
    "generalised tonic-clonic": "generalized_tonic_clonic",
    "generalized tonic-clonic": "generalized_tonic_clonic",
    "gtc": "generalized_tonic_clonic",
    "gtcs": "generalized_tonic_clonic",
    "focal to bilateral tonic-clonic": "focal_to_bilateral_tonic_clonic",
    "focal to bilateral tonic clonic": "focal_to_bilateral_tonic_clonic",
    "secondary generalized": "focal_to_bilateral_tonic_clonic",
    "secondary generalised": "focal_to_bilateral_tonic_clonic",
    "complex partial": "focal_impaired_awareness",
    "focal impaired awareness": "focal_impaired_awareness",
    "focal aware": "focal_aware",
    "simple partial": "focal_aware",
    "focal": "focal_unknown_awareness",  # bare "focal" — assume unknown awareness
    "myoclonic": "generalized_myoclonic",
    "atonic": "generalized_atonic",
    "absence": "generalized_absence_typical",
    "typical absence": "generalized_absence_typical",
    "atypical absence": "generalized_absence_atypical",
    "epileptic spasms": "generalized_epileptic_spasms",
    "infantile spasms": "generalized_epileptic_spasms",
    "unclassified": "unclassified",
    # EpilepsyType
    "generalised": "generalized",
    "combined focal and generalized": "combined_focal_generalized",
    "combined focal and generalised": "combined_focal_generalized",
    # Awareness
    "impaired": "impaired",
    "impaired awareness": "impaired",
    "impaired consciousness": "impaired",
    "aware": "aware",
    "retained awareness": "aware",
    # DrugResistanceStatus
    "drug resistant": "drug_resistant",
    "refractory": "drug_resistant",
    "medically refractory": "drug_resistant",
    "drug responsive": "drug_responsive",
    "seizure free": "drug_responsive",
    "undefined": "undefined",
    "unknown": "undefined",
    # EtiologyCategory
    "structural": "structural",
    "genetic": "genetic",
    "infectious": "infectious",
    "immune": "immune",
    "metabolic": "metabolic",
    # MedicationStatus
    "current": "current",
    "prior": "prior",
    "past": "prior",
    "failed": "failed",
    "discontinued": "discontinued_adverse_effect",
    "planned": "planned",
    # Certainty (in case model emits these)
    "definite": "definite",
    "probable": "probable",
    "possible": "possible",
    "negated": "negated",
    "not documented": "not_documented",
    "not_documented": "not_documented",
    # TemporalStatus
    "historical": "historical",
    "past": "historical",
    "hypothetical": "hypothetical",
    "planned": "planned",
    "unspecified": "unspecified",
}


_EVIDENCE_KEYS = {"value", "certainty", "temporal_status", "evidence_text",
                  "source_doc_id", "source_doc_type", "source_date"}


def _looks_evidence(x: Any) -> bool:
    """True if x already looks like an Evidence dict."""
    return isinstance(x, dict) and _EVIDENCE_KEYS.issubset(x.keys())


def _normalize_enum_value(v: Any) -> Any:
    """Best-effort enum-value canonicalization. Returns the original if no rule matches."""
    if not isinstance(v, str):
        return v
    key = v.strip().lower()
    if key in _ENUM_SYNONYMS:
        return _ENUM_SYNONYMS[key]
    # Try with underscores→spaces or vice versa
    alt = key.replace("_", " ")
    if alt in _ENUM_SYNONYMS:
        return _ENUM_SYNONYMS[alt]
    alt2 = key.replace(" ", "_")
    if alt2 in _ENUM_SYNONYMS:
        return _ENUM_SYNONYMS[alt2]
    return v


def _wrap_as_evidence(v: Any, doc: DocumentMetadata,
                      certainty: str = "possible",
                      temporal: str = "unspecified") -> dict[str, Any]:
    """Wrap a bare value as an Evidence-shaped dict."""
    if v is None or (isinstance(v, str) and v.strip().lower() in ("", "null",
                                                                    "none",
                                                                    "not documented",
                                                                    "not_documented",
                                                                    "unknown",
                                                                    "n/a")):
        return {
            "value": None, "certainty": "not_documented",
            "temporal_status": "unspecified", "evidence_text": None,
            "source_doc_id": doc.doc_id, "source_doc_type": doc.doc_type.value,
            "source_date": doc.doc_date.isoformat(),
        }

    # Normalize enum-string values
    if isinstance(v, str):
        v = _normalize_enum_value(v)

    # For dict values (composite objects like Medication, SeizureFrequency),
    # walk their child fields for enum normalization but keep the object shape.
    if isinstance(v, dict):
        v = {k: _normalize_enum_value(vv) if isinstance(vv, str) else vv
             for k, vv in v.items()}

    # Use str(v) as a minimal evidence quote — legitimate for silver-repair
    # since the model produced the value directly from the document.
    ev_text = str(v) if not isinstance(v, (dict, list)) else json.dumps(v)[:100]

    return {
        "value": v, "certainty": certainty,
        "temporal_status": temporal, "evidence_text": ev_text,
        "source_doc_id": doc.doc_id, "source_doc_type": doc.doc_type.value,
        "source_date": doc.doc_date.isoformat(),
    }


def _repair_evidence_field(field_val: Any, doc: DocumentMetadata) -> Any:
    """Return an Evidence-shaped dict from a possibly-bare field value."""
    if _looks_evidence(field_val):
        # Already Evidence-shaped — just normalize inner enums.
        v = field_val.get("value")
        if isinstance(v, str):
            field_val["value"] = _normalize_enum_value(v)
        elif isinstance(v, dict):
            field_val["value"] = {k: _normalize_enum_value(vv) if isinstance(vv, str) else vv
                                  for k, vv in v.items()}
        # Fix missing source metadata if the model produced Evidence but
        # omitted the source_* fields.
        field_val.setdefault("source_doc_id", doc.doc_id)
        field_val.setdefault("source_doc_type", doc.doc_type.value)
        field_val.setdefault("source_date", doc.doc_date.isoformat())
        field_val.setdefault("certainty", "possible")
        field_val.setdefault("temporal_status", "unspecified")
        return field_val
    return _wrap_as_evidence(field_val, doc)


def _repair_list_of_evidence(items: Any, doc: DocumentMetadata) -> list[Any]:
    if not isinstance(items, list):
        return []
    return [_repair_evidence_field(x, doc) for x in items]


# ---------------------------------------------------------------------------
# Per-module repair
# ---------------------------------------------------------------------------

# Which fields on each module are list-typed vs. single Evidence.
_LIST_FIELDS: dict[str, set[str]] = {
    "MedicationModule": {"current_asms", "prior_asms", "failed_asms",
                          "surgery_history", "non_drug_therapies"},
    "ClinicalSeizureModule": {"other_seizure_types", "other_seizure_frequencies"},
    "MriModule": {"findings"},
    "EegModule": {"ied_findings"},
    "ClinicalLocalizationModule": {"alternative_claims"},
}


def _module_expected_fields(module_cls: Type[BaseModel]) -> tuple[set[str], set[str]]:
    """Return (single_evidence_fields, list_fields) for the given module."""
    lists = _LIST_FIELDS.get(module_cls.__name__, set())
    all_fields = set(module_cls.model_fields.keys())
    singles = all_fields - lists
    return singles, lists


def smart_repair_module(
    raw_dict: dict[str, Any],
    module_cls: Type[BaseModel],
    doc: DocumentMetadata,
) -> dict[str, Any]:
    """Take a raw model output dict, wrap bare values as Evidence, normalize
    enums, and return a repaired dict conforming to the module's expected shape."""
    if not isinstance(raw_dict, dict):
        return raw_dict

    singles, lists = _module_expected_fields(module_cls)
    out: dict[str, Any] = {}
    for name in singles:
        if name in raw_dict:
            out[name] = _repair_evidence_field(raw_dict[name], doc)
        else:
            # Field missing entirely — set to not_documented
            out[name] = _repair_evidence_field(None, doc)
    for name in lists:
        out[name] = _repair_list_of_evidence(raw_dict.get(name, []), doc)
    return out


def try_smart_repair(
    raw_response: str,
    module_cls: Type[BaseModel],
    doc: DocumentMetadata,
) -> tuple[BaseModel | None, dict | None, str | None]:
    """Attempt raw JSON parse → smart repair → Pydantic validate.

    Returns (validated_module | None, raw_parsed_dict | None, error_str | None).
    """
    # Step 1: try to extract a JSON object from the raw response
    from services.extract import _extract_first_json_object, _strip_code_fence  # reuse

    text = raw_response
    fence = _strip_code_fence(text)
    if fence is not None:
        text = fence
    obj = _extract_first_json_object(text)
    if obj is None:
        return None, None, "no_json_found"
    try:
        parsed = json.loads(obj)
    except Exception as e:
        # Try one more repair: unescape common quote issues
        try:
            parsed = json.loads(obj.replace("\\'", "'"))
        except Exception:
            return None, None, f"json_parse_failed: {e}"

    if not isinstance(parsed, dict):
        return None, parsed, "parsed_not_a_dict"

    # Step 2: smart repair
    repaired = smart_repair_module(parsed, module_cls, doc)

    # Step 3: validate
    try:
        validated = module_cls.model_validate(repaired)
        return validated, parsed, None
    except ValidationError as e:
        return None, parsed, str(e)[:800]
