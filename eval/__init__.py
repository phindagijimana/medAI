"""MedAI-EPI evaluation harness (paper §15–16, Tables 7 and 8).

Public API:

    from eval import (
        FieldMetrics,
        ArmSummary,
        score_field,
        score_module,
        aggregate_manifests,
        bootstrap_ci,
    )
"""

from .metrics import (
    ArmSummary,
    FieldMetrics,
    ModuleScore,
    bootstrap_ci,
    score_field,
    score_module,
)
from .aggregator import aggregate_manifests, load_gold

__all__ = [
    "ArmSummary",
    "FieldMetrics",
    "ModuleScore",
    "aggregate_manifests",
    "bootstrap_ci",
    "load_gold",
    "score_field",
    "score_module",
]
