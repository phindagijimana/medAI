"""Metric primitives (paper §15, Table 7).

Field-level P/R/F1 with support, module-level macro/micro summaries, and
patient-level bootstrap CIs. Categorical fields are scored by exact-match
after normalization. List-valued fields (findings, IEDs, ASMs) are scored
as multi-set equality on the extracted `value` items.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldMetrics:
    """Per-field aggregate over N predictions."""
    field_name: str
    n: int = 0                                 # total scored predictions
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    # Applicable-only counters — fields marked not-applicable for a doc type
    # are excluded from denominators (§11 applicability mask).
    n_applicable: int = 0

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def accuracy(self) -> float:
        d = self.tp + self.tn + self.fp + self.fn
        return (self.tp + self.tn) / d if d else 0.0

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "field_name": self.field_name,
            "n": self.n,
            "n_applicable": self.n_applicable,
            "tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "accuracy": round(self.accuracy, 4),
        }


@dataclass
class ModuleScore:
    module_name: str
    fields: dict[str, FieldMetrics] = field(default_factory=dict)

    @property
    def macro_f1(self) -> float:
        vals = [f.f1 for f in self.fields.values() if f.n_applicable > 0]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def micro_f1(self) -> float:
        tp = sum(f.tp for f in self.fields.values())
        fp = sum(f.fp for f in self.fields.values())
        fn = sum(f.fn for f in self.fields.values())
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def to_dict(self) -> dict:
        return {
            "module_name": self.module_name,
            "macro_f1": round(self.macro_f1, 4),
            "micro_f1": round(self.micro_f1, 4),
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
        }


@dataclass
class ArmSummary:
    """Everything the aggregator produces for one arm (M0/M1/M2/B0/…)."""
    arm: str
    n_documents: int = 0
    n_patients: int = 0
    # Schema validity (paper §11)
    raw_valid: int = 0
    repaired_valid: int = 0
    final_valid: int = 0
    parse_failures: int = 0
    repair_method_counts: dict[str, int] = field(default_factory=dict)
    # Evidence (paper §12)
    total_evidence_objects: int = 0
    evidence_supported: int = 0
    evidence_unsupported: int = 0
    evidence_missing: int = 0
    # Per-module
    modules: dict[str, ModuleScore] = field(default_factory=dict)
    # Efficiency
    total_duration_s: float = 0.0
    total_tokens_generated: int = 0

    @property
    def raw_validity_rate(self) -> float:
        return self.raw_valid / self.n_documents if self.n_documents else 0.0

    @property
    def final_validity_rate(self) -> float:
        return self.final_valid / self.n_documents if self.n_documents else 0.0

    @property
    def unsupported_claim_rate(self) -> float:
        denom = self.evidence_supported + self.evidence_unsupported + self.evidence_missing
        return self.evidence_unsupported / denom if denom else 0.0

    @property
    def evidence_precision(self) -> float:
        denom = self.evidence_supported + self.evidence_unsupported + self.evidence_missing
        return self.evidence_supported / denom if denom else 0.0

    def to_dict(self) -> dict:
        return {
            "arm": self.arm,
            "n_documents": self.n_documents,
            "n_patients": self.n_patients,
            "raw_validity_rate": round(self.raw_validity_rate, 4),
            "final_validity_rate": round(self.final_validity_rate, 4),
            "raw_valid": self.raw_valid,
            "repaired_valid": self.repaired_valid,
            "final_valid": self.final_valid,
            "parse_failures": self.parse_failures,
            "repair_method_counts": dict(self.repair_method_counts),
            "unsupported_claim_rate": round(self.unsupported_claim_rate, 4),
            "evidence_precision": round(self.evidence_precision, 4),
            "total_evidence_objects": self.total_evidence_objects,
            "modules": {k: v.to_dict() for k, v in self.modules.items()},
            "efficiency": {
                "total_duration_s": round(self.total_duration_s, 2),
                "total_tokens_generated": self.total_tokens_generated,
                "avg_duration_s": round(
                    self.total_duration_s / self.n_documents, 2
                ) if self.n_documents else 0.0,
            },
        }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _norm(v: Any) -> Any:
    """Canonicalize a value for exact-match scoring."""
    if v is None:
        return None
    if hasattr(v, "value"):        # str enum
        return v.value
    if isinstance(v, str):
        return v.strip().lower()
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 4)
    return v


def _norm_list(v: list[Any]) -> tuple[Any, ...]:
    """Multi-set-friendly canonicalization: sorted tuple of normalized values."""
    return tuple(sorted((_norm(x) for x in v), key=lambda k: repr(k)))


def score_field(
    field_name: str,
    pred: dict | None,
    gold: dict | None,
    applicable: bool,
    metrics: FieldMetrics | None = None,
) -> FieldMetrics:
    """Update a `FieldMetrics` accumulator for one (pred, gold) pair of Evidence dicts.

    `applicable` indicates whether the field is scoreable for this document
    (per the applicability mask). Non-applicable fields are counted but not
    scored.
    """
    m = metrics or FieldMetrics(field_name=field_name)
    m.n += 1
    if not applicable:
        return m
    m.n_applicable += 1

    pred_val = _extract_value(pred)
    gold_val = _extract_value(gold)

    # Both null → true negative (agreement on "not documented / unknown")
    if pred_val is None and gold_val is None:
        m.tn += 1
        return m

    # Prediction absent but gold present → false negative
    if pred_val is None and gold_val is not None:
        m.fn += 1
        return m

    # Prediction present but gold absent → false positive
    if pred_val is not None and gold_val is None:
        m.fp += 1
        return m

    # Both present — compare
    if isinstance(gold_val, list) or isinstance(pred_val, list):
        # Partial-list (multiset) scoring: per-item TP/FP/FN via multiset
        # difference. TP = items in both, FP = items in pred but not gold,
        # FN = items in gold but not pred. This treats findings/IEDs/ASMs
        # as sets of tokens rather than all-or-nothing.
        from collections import Counter
        pv_items = pred_val if isinstance(pred_val, list) else [pred_val]
        gv_items = gold_val if isinstance(gold_val, list) else [gold_val]
        pv_counter = Counter(repr(_norm(x)) for x in pv_items)
        gv_counter = Counter(repr(_norm(x)) for x in gv_items)
        tp_bag = pv_counter & gv_counter
        fp_bag = pv_counter - gv_counter
        fn_bag = gv_counter - pv_counter
        m.tp += sum(tp_bag.values())
        m.fp += sum(fp_bag.values())
        m.fn += sum(fn_bag.values())
        return m

    if _norm(pred_val) == _norm(gold_val):
        m.tp += 1
    else:
        m.fp += 1
        m.fn += 1
    return m


def _extract_value(field_repr: Any) -> Any:
    """Given either an Evidence-shaped dict (has 'value') or a list of such
    dicts, return the underlying value(s)."""
    if field_repr is None:
        return None
    if isinstance(field_repr, list):
        return [_extract_value(x) for x in field_repr]
    if isinstance(field_repr, dict) and "value" in field_repr:
        return field_repr["value"]
    return field_repr


def score_module(
    module_name: str,
    pred_module: dict | None,
    gold_module: dict | None,
    applicable_fields: set[str] | None = None,
    existing: ModuleScore | None = None,
) -> ModuleScore:
    """Score one predicted module against gold, accumulating field metrics."""
    ms = existing or ModuleScore(module_name=module_name)

    # If neither pred nor gold populated the module, nothing to score.
    if pred_module is None and gold_module is None:
        return ms

    # If gold has the module and pred doesn't, all gold fields are FN.
    if pred_module is None:
        pred_module = {}
    if gold_module is None:
        gold_module = {}

    all_fields = set(pred_module.keys()) | set(gold_module.keys())
    for fname in sorted(all_fields):
        applicable = applicable_fields is None or fname in applicable_fields
        existing_fm = ms.fields.get(fname)
        ms.fields[fname] = score_field(
            fname,
            pred_module.get(fname),
            gold_module.get(fname),
            applicable=applicable,
            metrics=existing_fm,
        )
    return ms


# ---------------------------------------------------------------------------
# Patient-level bootstrap CIs (paper §16)
# ---------------------------------------------------------------------------


def bootstrap_ci(
    per_patient_values: list[float],
    n_resamples: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Nonparametric percentile bootstrap CI on the mean of a per-patient metric.

    Returns (mean, lo, hi) where [lo, hi] is a (1-alpha)*100% CI.
    """
    if not per_patient_values:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(per_patient_values)
    means: list[float] = []
    for _ in range(n_resamples):
        sample = [per_patient_values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    mean = sum(per_patient_values) / n
    lo = means[int(math.floor(alpha / 2 * n_resamples))]
    hi = means[int(math.ceil((1 - alpha / 2) * n_resamples)) - 1]
    return (mean, lo, hi)
