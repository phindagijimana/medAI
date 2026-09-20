"""Manifest → summary aggregator (paper §15–16, Tables 3-5).

Reads all run manifests from a directory, optionally pairs them with gold-label
JSON files, and produces per-arm summaries with:
  - schema validity rates (raw + repaired)
  - repair method counts
  - per-field precision/recall/F1
  - evidence correctness + unsupported-claim rate (paper §12)
  - doc-type stratification
  - patient-level bootstrap CIs on final validity

Gold format (one JSON per document, keyed by manifest.source_doc_id):
    {
      "doc_id": "...", "doc_type": "...", "patient_id": "...",
      "phenotype": <EpilepsyPhenotype JSON matching SCHEMA_VERSION>,
    }
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from schema import modules_for, DocumentType

from .metrics import ArmSummary, FieldMetrics, ModuleScore, bootstrap_ci, score_module


def load_gold(gold_dir: str | Path) -> dict[str, dict]:
    """Load gold JSON files keyed by doc_id.

    Each file is expected to be JSON with a top-level `doc_id` key. Missing
    directory or empty dir → empty dict (aggregator will still produce a
    validity-only summary)."""
    p = Path(gold_dir)
    if not p.exists():
        return {}
    gold: dict[str, dict] = {}
    for f in p.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            doc_id = data.get("doc_id") or data.get("document", {}).get("doc_id")
            if doc_id:
                gold[doc_id] = data
        except Exception:
            continue
    return gold


def _iter_manifests(root: Path):
    for f in sorted(root.rglob("*.json")):
        try:
            yield f, json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue


def _applicable_field_set(doc_type_str: str, module_name: str) -> set[str] | None:
    """Return the set of fields applicable for (doc_type, module). None means
    'no per-field mask defined' — all fields scored."""
    try:
        dt = DocumentType(doc_type_str)
    except ValueError:
        return None
    if module_name not in modules_for(dt):
        return set()          # module not applicable → score no fields
    return None                # no per-field carveouts currently


def aggregate_manifests(
    manifest_root: str | Path,
    *,
    gold: dict[str, dict] | None = None,
    filter_arm: str | None = None,
) -> dict[str, ArmSummary]:
    """Read all manifests under `manifest_root` and return one ArmSummary per arm.

    If `gold` is provided and contains a doc_id, per-field scoring runs;
    otherwise only validity/evidence/efficiency stats are computed.
    """
    root = Path(manifest_root)
    gold = gold or {}
    arms: dict[str, ArmSummary] = defaultdict(lambda: ArmSummary(arm=""))
    per_patient_valid: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )   # arm → patient_id → [0/1 final_valid per doc]

    for _path, mf in _iter_manifests(root):
        arm = mf.get("arm") or "unknown"
        if filter_arm and arm != filter_arm:
            continue
        s = arms[arm]
        if not s.arm:
            s.arm = arm

        s.n_documents += 1
        if mf.get("raw_valid"):
            s.raw_valid += 1
        elif mf.get("final_valid"):
            s.repaired_valid += 1
        if mf.get("final_valid"):
            s.final_valid += 1
        else:
            s.parse_failures += 1

        rm = mf.get("repair_method")
        if rm:
            s.repair_method_counts[rm] = s.repair_method_counts.get(rm, 0) + 1

        s.total_duration_s += float(mf.get("duration_s") or 0.0)
        if mf.get("raw_response_tokens"):
            s.total_tokens_generated += int(mf["raw_response_tokens"])

        # Patient-level tracking for bootstrap CI
        # Manifests don't yet carry patient_id explicitly — derive from doc_id
        # convention or leave as document-level
        doc_id = mf.get("source_doc_id", "")
        gold_entry = gold.get(doc_id)
        patient_id = ""
        if gold_entry:
            patient_id = gold_entry.get("patient_id") \
                or gold_entry.get("phenotype", {}).get("document", {}).get("patient_id", "")
        per_patient_valid[arm][patient_id or doc_id].append(
            1 if mf.get("final_valid") else 0
        )

        # Scoring
        if gold_entry:
            pred_pheno = mf.get("parsed_value")
            gold_pheno = gold_entry.get("phenotype") or gold_entry
            _score_one(s, mf.get("source_doc_type", ""), pred_pheno, gold_pheno)

    # Attach patient-level bootstrap CI on final validity
    for arm_name, s in arms.items():
        per_pt_means = [sum(v) / len(v) for v in per_patient_valid[arm_name].values() if v]
        if per_pt_means:
            mean, lo, hi = bootstrap_ci(per_pt_means)
            s_dict_ci = {"mean": round(mean, 4), "lo": round(lo, 4), "hi": round(hi, 4)}
            # Stash on the module scores by convention — added as a synthetic
            # top-level metric via `to_dict` post-processing.
            s.modules.setdefault("_meta", ModuleScore(module_name="_meta"))
            # Store CI as a fake field for reporting
            fm = FieldMetrics(field_name="final_validity_rate_ci")
            fm.n = len(per_pt_means)
            fm.n_applicable = len(per_pt_means)
            fm.tp = int(mean * len(per_pt_means))
            fm.tn = len(per_pt_means) - fm.tp
            s.modules["_meta"].fields["final_validity_rate_ci"] = fm
            s.modules["_meta"].fields["final_validity_rate_ci_bounds"] = FieldMetrics(
                field_name=f"final_validity_ci_lo={lo:.4f}_hi={hi:.4f}",
            )

    return dict(arms)


def _score_one(summary: ArmSummary, doc_type_str: str, pred_pheno: dict | None,
               gold_pheno: dict) -> None:
    """Score one predicted phenotype against its gold. Predicted may be a
    single module dict (if extraction ran only one module) or a full
    EpilepsyPhenotype dict; handle both."""
    pred = pred_pheno or {}
    # If the manifest was per-module, its parsed_value IS the module dict,
    # not a full phenotype. Infer which module it maps to via `source_doc_type`
    # + heuristic on top-level keys.
    for module_name in ("mri", "eeg", "clinical_seizure", "medication",
                        "clinical_localization", "integrated"):
        gold_mod = gold_pheno.get(module_name) if isinstance(gold_pheno, dict) else None
        # `pred` might be the module itself (per-module manifest) or nested.
        pred_mod = pred.get(module_name) if isinstance(pred, dict) else None
        if pred_mod is None and isinstance(pred, dict) and any(
            k in pred for k in _module_signature_keys(module_name)
        ):
            pred_mod = pred    # per-module manifest

        if pred_mod is None and gold_mod is None:
            continue

        applicable = _applicable_field_set(doc_type_str, module_name)
        if applicable == set():   # module not applicable
            continue

        existing = summary.modules.get(module_name)
        summary.modules[module_name] = score_module(
            module_name, pred_mod, gold_mod,
            applicable_fields=applicable,
            existing=existing,
        )


def _module_signature_keys(module_name: str) -> tuple[str, ...]:
    """Signature keys unique enough to identify a module dict as that module."""
    return {
        "mri": ("overall_normal", "hippocampal_sclerosis", "focal_cortical_dysplasia"),
        "eeg": ("study_type", "ied_findings", "ictal_onset_lobe"),
        "clinical_seizure": ("epilepsy_type", "predominant_seizure_type", "etiology_category"),
        "medication": ("current_asms", "drug_resistance_status", "surgery_history"),
        "clinical_localization": ("primary_claim", "alternative_claims"),
        "integrated": ("eeg_localization", "mri_localization", "concordance"),
    }[module_name]
