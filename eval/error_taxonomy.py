"""Error taxonomy scorer (paper Table 8).

Given a (pred_module, gold_module) pair, walk field-by-field and classify each
disagreement into one of the twelve categories the paper defines:

  1. missed_fact                 — gold has value, pred has value=None
  2. wrong_label                 — both values present, they differ
  3. negation                    — pred marks presence where gold negates (or vice-versa)
  4. uncertainty                 — certainty enum mismatch (definite vs. possible etc.)
  5. temporal                    — temporal_status mismatch (current vs. historical etc.)
  6. medication_status           — medication.status mismatch (current vs. prior/failed)
  7. eeg_semantic                — mismatches within EEG-specific value objects (IED type,
                                    ictal onset lobe, laterality)
  8. mri_semantic                — mismatches within MRI-specific value objects
  9. conflict                    — pred and gold disagree in a way not covered elsewhere
                                    (fallback; also used for multi-value list disagreement)
 10. unsupported_inference       — pred value not None but pred evidence_text does not
                                    appear in source (surfaced via evidence verifier — the
                                    scorer just labels it here)
 11. evidence_mismatch           — value is correct but pred evidence_text ≠ gold's
                                    (soft match on normalized whitespace, then differ)
 12. schema                      — pred failed schema validity (from run manifest)

Emits per-category counts + per-error records for the paper's error appendix.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

# Error category identifiers — string constants for portability
E_MISSED           = "missed_fact"
E_WRONG_LABEL      = "wrong_label"
E_NEGATION         = "negation"
E_UNCERTAINTY      = "uncertainty"
E_TEMPORAL         = "temporal"
E_MEDICATION_STATUS = "medication_status"
E_EEG_SEMANTIC     = "eeg_semantic"
E_MRI_SEMANTIC     = "mri_semantic"
E_CONFLICT         = "conflict"
E_UNSUPPORTED      = "unsupported_inference"
E_EVIDENCE_MISMATCH = "evidence_mismatch"
E_SCHEMA           = "schema"

ALL_CATEGORIES = (
    E_MISSED, E_WRONG_LABEL, E_NEGATION, E_UNCERTAINTY, E_TEMPORAL,
    E_MEDICATION_STATUS, E_EEG_SEMANTIC, E_MRI_SEMANTIC, E_CONFLICT,
    E_UNSUPPORTED, E_EVIDENCE_MISMATCH, E_SCHEMA,
)


@dataclass
class ErrorRecord:
    doc_id: str
    module: str
    field_path: str
    category: str
    pred_value: Any = None
    gold_value: Any = None
    detail: str = ""


@dataclass
class ErrorReport:
    counts: Counter = field(default_factory=Counter)
    errors: list[ErrorRecord] = field(default_factory=list)

    def add(self, err: ErrorRecord) -> None:
        self.counts[err.category] += 1
        self.errors.append(err)

    def to_dict(self) -> dict:
        return {
            "counts": {c: self.counts.get(c, 0) for c in ALL_CATEGORIES},
            "total_errors": sum(self.counts.values()),
            "errors_sample": [
                {"doc_id": e.doc_id, "module": e.module, "field_path": e.field_path,
                 "category": e.category, "pred_value": e.pred_value,
                 "gold_value": e.gold_value, "detail": e.detail}
                for e in self.errors[:200]
            ],
        }


def _norm(v: Any) -> Any:
    if v is None:
        return None
    if hasattr(v, "value"):
        return v.value
    if isinstance(v, str):
        return v.strip().lower()
    return v


def _certainty_mismatch(pred_ev: dict, gold_ev: dict) -> bool:
    """Different certainty labels on the same field. Uncertainty errors are
    counted separately from wrong-label errors even when the value differs;
    but here we only flag the certainty-only case (value equal, certainty diff)."""
    if _norm(pred_ev.get("value")) != _norm(gold_ev.get("value")):
        return False
    return pred_ev.get("certainty") != gold_ev.get("certainty")


def _temporal_mismatch(pred_ev: dict, gold_ev: dict) -> bool:
    if _norm(pred_ev.get("value")) != _norm(gold_ev.get("value")):
        return False
    return pred_ev.get("temporal_status") != gold_ev.get("temporal_status")


def _negation_conflict(pred_ev: dict, gold_ev: dict) -> bool:
    """One side asserts presence, the other explicitly negates. For boolean
    fields: pred=True vs gold=False (or vice-versa) with either side having
    certainty=negated."""
    pv = _norm(pred_ev.get("value"))
    gv = _norm(gold_ev.get("value"))
    if pv == gv:
        return False
    pc = pred_ev.get("certainty")
    gc = gold_ev.get("certainty")
    return "negated" in (pc, gc)


def _evidence_normalized_match(pred_ev: dict, gold_ev: dict) -> bool:
    """Same value, different quoted evidence text (both non-empty)."""
    if _norm(pred_ev.get("value")) != _norm(gold_ev.get("value")):
        return False
    pt = (pred_ev.get("evidence_text") or "").strip().lower()
    gt = (gold_ev.get("evidence_text") or "").strip().lower()
    if not pt or not gt:
        return False
    return pt != gt


def _module_semantic_bucket(module_name: str) -> Optional[str]:
    return {"mri": E_MRI_SEMANTIC, "eeg": E_EEG_SEMANTIC}.get(module_name)


def classify_field(
    *, doc_id: str, module: str, field_path: str,
    pred_ev: dict | None, gold_ev: dict | None,
) -> list[ErrorRecord]:
    """Classify one (pred, gold) Evidence-dict pair. Returns 0..N ErrorRecords.

    A single field can raise MULTIPLE categories (e.g., wrong_label AND
    evidence_mismatch); each is counted. Callers may deduplicate if the
    paper's primary endpoint requires disjoint categories.
    """
    out: list[ErrorRecord] = []
    if pred_ev is None:
        pred_ev = {}
    if gold_ev is None:
        gold_ev = {}
    pv = _norm(pred_ev.get("value"))
    gv = _norm(gold_ev.get("value"))

    # Category 1: missed_fact — gold has value, pred does not
    if gv is not None and pv is None:
        out.append(ErrorRecord(doc_id, module, field_path, E_MISSED,
                               pred_value=pv, gold_value=gv,
                               detail="gold present, pred absent"))
        return out

    # Category 9-ish: false positive (pred has value, gold doesn't). We label
    # this under wrong_label with a specific detail; some papers call this
    # over-extraction.
    if pv is not None and gv is None:
        out.append(ErrorRecord(doc_id, module, field_path, E_WRONG_LABEL,
                               pred_value=pv, gold_value=gv,
                               detail="pred present, gold absent (over-extraction)"))
        return out

    # Both absent → no error
    if pv is None and gv is None:
        return out

    # Both present. Check disagreements in order of specificity.
    if pv != gv:
        # Negation conflict wins over wrong_label
        if _negation_conflict(pred_ev, gold_ev):
            out.append(ErrorRecord(doc_id, module, field_path, E_NEGATION,
                                   pred_value=pv, gold_value=gv,
                                   detail="negation certainty on one side"))
            return out

        # Semantic bucket for MRI/EEG modules
        sem_bucket = _module_semantic_bucket(module)
        if sem_bucket:
            out.append(ErrorRecord(doc_id, module, field_path, sem_bucket,
                                   pred_value=pv, gold_value=gv,
                                   detail=f"{module}-specific value mismatch"))
            return out

        # medication status specifically — captured when field_path includes
        # the medication's status
        if module == "medication" and "status" in field_path:
            out.append(ErrorRecord(doc_id, module, field_path, E_MEDICATION_STATUS,
                                   pred_value=pv, gold_value=gv,
                                   detail="ASM status label mismatch"))
            return out

        # Generic wrong_label
        out.append(ErrorRecord(doc_id, module, field_path, E_WRONG_LABEL,
                               pred_value=pv, gold_value=gv))
        return out

    # Values agree. Check certainty / temporal / evidence mismatches.
    if _certainty_mismatch(pred_ev, gold_ev):
        out.append(ErrorRecord(doc_id, module, field_path, E_UNCERTAINTY,
                               pred_value=pv, gold_value=gv,
                               detail=f"certainty {pred_ev.get('certainty')!r} vs {gold_ev.get('certainty')!r}"))
    if _temporal_mismatch(pred_ev, gold_ev):
        out.append(ErrorRecord(doc_id, module, field_path, E_TEMPORAL,
                               pred_value=pv, gold_value=gv,
                               detail=f"temporal_status {pred_ev.get('temporal_status')!r} vs {gold_ev.get('temporal_status')!r}"))
    if _evidence_normalized_match(pred_ev, gold_ev):
        out.append(ErrorRecord(doc_id, module, field_path, E_EVIDENCE_MISMATCH,
                               pred_value=pv, gold_value=gv,
                               detail="value equal, evidence_text differs"))
    return out


def _iter_evidences(mod_dict: dict | None, module: str, prefix: str = "") -> list[tuple[str, dict]]:
    """Yield (field_path, evidence_dict) for every Evidence-shaped dict inside a module."""
    if not isinstance(mod_dict, dict):
        return []
    out: list[tuple[str, dict]] = []
    for name, val in mod_dict.items():
        path = f"{prefix}{name}"
        if isinstance(val, dict) and "value" in val and "evidence_text" in val:
            out.append((path, val))
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, dict) and "value" in item and "evidence_text" in item:
                    out.append((f"{path}[{i}]", item))
    return out


def score_error_taxonomy(
    *, doc_id: str, module: str,
    pred_module: dict | None, gold_module: dict | None,
    manifest_schema_failed: bool = False,
    unsupported_field_paths: list[str] | None = None,
) -> ErrorReport:
    """Score one predicted module against its gold under the paper's error taxonomy.

    Additional error signals passed in:
      - `manifest_schema_failed=True` if the run manifest says the raw JSON
        did not pass schema validation (counts one E_SCHEMA error per module).
      - `unsupported_field_paths` — list of Evidence field paths where the
        evidence verifier flagged unsupported_claim; each yields one
        E_UNSUPPORTED record.
    """
    report = ErrorReport()

    if manifest_schema_failed:
        report.add(ErrorRecord(doc_id, module, "<module>", E_SCHEMA,
                               detail="raw prediction failed schema validation"))

    for path in (unsupported_field_paths or []):
        report.add(ErrorRecord(doc_id, module, path, E_UNSUPPORTED,
                               detail="evidence quote not found in source"))

    # Pair up predicted and gold Evidence fields (union of paths)
    pred_pairs = dict(_iter_evidences(pred_module, module))
    gold_pairs = dict(_iter_evidences(gold_module, module))
    all_paths = set(pred_pairs) | set(gold_pairs)
    for path in sorted(all_paths):
        errors = classify_field(
            doc_id=doc_id, module=module, field_path=path,
            pred_ev=pred_pairs.get(path), gold_ev=gold_pairs.get(path),
        )
        for e in errors:
            report.add(e)
    return report
