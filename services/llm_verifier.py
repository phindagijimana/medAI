"""Cross-model extractor-verifier pattern for MedAI-EPI.

Given an extracted phenotype from one LLM (the extractor), a *different*
LLM (the verifier) is asked, per Evidence-carrying field:

    "Given the source document and the extractor's claim + evidence quote,
     is the claim supported, negated, laterality-consistent, and current?"

The verifier's output is a structured `VerificationVerdict` per field:

    supported             : bool
    evidence_matches      : bool | null  — did the quote appear in the source?
    laterality_consistent : bool | null
    negation_consistent   : bool | null
    temporal_consistent   : bool | null
    verifier_confidence   : one of {"definite", "probable", "possible", "unknown"}
    verifier_rationale    : short string

Downstream, `merge_verification_into_phenotype` adds these verdicts onto
each Evidence record as sidecar fields (leaving the extractor's original
Evidence values intact), so the long-format CSV gains a
`verifier_verdict` column without changing any phenotype content.

The intent is aligned with the paper: the verifier reduces the
**unsupported-claim rate** by flagging disagreements, without changing
field F1. It is a reliability layer, not an accuracy layer.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from services.extract import DecodingConfig

logger = logging.getLogger(__name__)


_VERIFIER_SYSTEM_PROMPT = (
    "You are an evidence verifier for a research phenotyping assistant. "
    "You are given: (1) a clinical document, (2) an extraction claim about "
    "one field, and (3) an evidence quote allegedly from the document. "
    "Your job is to verify whether the claim is supported by the evidence "
    "and consistent with the document. "
    "Do NOT re-extract. Do NOT invent new content. Do NOT diagnose. "
    "Respond with a single JSON object with these exact keys and nothing else."
)


_VERIFIER_INSTRUCTION = (
    "Return JSON with EXACTLY these keys:\n"
    "  supported             : true | false\n"
    "  evidence_matches      : true | false | null   (does the quote appear in the document?)\n"
    "  laterality_consistent : true | false | null   (null if laterality is not applicable)\n"
    "  negation_consistent   : true | false | null   (null if negation is not applicable)\n"
    "  temporal_consistent   : true | false | null\n"
    "  verifier_confidence   : \"definite\" | \"probable\" | \"possible\" | \"unknown\"\n"
    "  verifier_rationale    : short string (max 40 words)\n"
    "No prose outside the JSON."
)


@dataclass
class VerificationVerdict:
    field_path: str
    supported: Optional[bool] = None
    evidence_matches: Optional[bool] = None
    laterality_consistent: Optional[bool] = None
    negation_consistent: Optional[bool] = None
    temporal_consistent: Optional[bool] = None
    verifier_confidence: str = "unknown"
    verifier_rationale: str = ""
    verifier_model: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _render_value(v: Any) -> str:
    if v is None:
        return "(not documented)"
    if isinstance(v, dict):
        return "; ".join(f"{k}={val}" for k, val in v.items() if val is not None)
    return str(v)


def _prompt_for(field_path: str, ev: dict, source_text: str) -> str:
    value = _render_value(ev.get("value"))
    quote = ev.get("evidence_text") or ""
    laterality = "n/a"
    for k in ("laterality",):
        if k in ev and ev[k] is not None:
            laterality = str(ev[k])
    certainty = ev.get("certainty") or ""
    temporal = ev.get("temporal_status") or ""
    return (
        f"{_VERIFIER_SYSTEM_PROMPT}\n\n"
        f"DOCUMENT:\n\"\"\"\n{source_text}\n\"\"\"\n\n"
        f"CLAIM:\n"
        f"  field        : {field_path}\n"
        f"  value        : {value}\n"
        f"  certainty    : {certainty}\n"
        f"  temporal     : {temporal}\n"
        f"  laterality   : {laterality}\n"
        f"  evidence     : \"{quote}\"\n\n"
        f"{_VERIFIER_INSTRUCTION}\n"
    )


def _parse_verdict(raw: str) -> dict:
    """Extract the JSON object from the verifier's output."""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m is None:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def verify_phenotype(
    *,
    verifier_backend,
    source_text: str,
    phenotype: dict,
    decoding: DecodingConfig | None = None,
    fields_to_verify: list[str] | None = None,
) -> list[VerificationVerdict]:
    """Verify each Evidence-carrying field in the phenotype dict.

    `verifier_backend` must implement `.generate(prompt, decoding) -> (str, int|None)`
    and have `.model_name`. Any model that isn't the extractor model works.
    """
    if decoding is None:
        decoding = DecodingConfig(
            do_sample=False, temperature=None, top_p=None,
            max_new_tokens=256, seed=0,
        )
    verdicts: list[VerificationVerdict] = []

    for module_name in ("clinical_seizure", "medication", "clinical_localization",
                         "eeg", "mri", "integrated"):
        module = phenotype.get(module_name)
        if not module:
            continue
        for fname, val in module.items():
            path = f"{module_name}.{fname}"
            if fields_to_verify and path not in fields_to_verify:
                continue
            # Skip list-valued fields: verify only scalar Evidence for now.
            if isinstance(val, list):
                for i, item in enumerate(val):
                    if isinstance(item, dict) and item.get("value") is not None:
                        v = _run_one(
                            verifier_backend, source_text, item,
                            f"{path}[{i}]", decoding,
                        )
                        verdicts.append(v)
                continue
            if not isinstance(val, dict):
                continue
            if val.get("value") is None:
                # Nothing extracted — nothing to verify.
                continue
            v = _run_one(
                verifier_backend, source_text, val, path, decoding,
            )
            verdicts.append(v)
    return verdicts


def _run_one(
    verifier_backend, source_text: str, ev: dict, path: str,
    decoding: DecodingConfig,
) -> VerificationVerdict:
    prompt = _prompt_for(path, ev, source_text)
    try:
        raw, _n = verifier_backend.generate(prompt, decoding)
    except Exception as e:
        logger.exception("verifier.generate failed")
        return VerificationVerdict(
            field_path=path, supported=None,
            verifier_confidence="unknown",
            verifier_rationale=f"verifier_error: {type(e).__name__}",
            verifier_model=getattr(verifier_backend, "model_name", ""),
        )
    parsed = _parse_verdict(raw)
    return VerificationVerdict(
        field_path=path,
        supported=parsed.get("supported"),
        evidence_matches=parsed.get("evidence_matches"),
        laterality_consistent=parsed.get("laterality_consistent"),
        negation_consistent=parsed.get("negation_consistent"),
        temporal_consistent=parsed.get("temporal_consistent"),
        verifier_confidence=str(parsed.get("verifier_confidence", "unknown")).lower(),
        verifier_rationale=str(parsed.get("verifier_rationale", ""))[:240],
        verifier_model=getattr(verifier_backend, "model_name", ""),
    )


def merge_verdicts_into_long_rows(
    long_rows: list[dict], verdicts: list[VerificationVerdict],
) -> list[dict]:
    """Add verifier columns to services/tabular.to_long_rows() output."""
    by_path = {v.field_path: v for v in verdicts}
    out = []
    for r in long_rows:
        path = f"{r.get('module')}.{r.get('field')}"
        v = by_path.get(path)
        r2 = dict(r)
        r2["verifier_supported"] = "" if v is None else (
            "true" if v.supported is True else "false" if v.supported is False else "unknown"
        )
        r2["verifier_confidence"] = v.verifier_confidence if v else ""
        r2["verifier_model"] = v.verifier_model if v else ""
        r2["verifier_rationale"] = v.verifier_rationale if v else ""
        out.append(r2)
    return out
