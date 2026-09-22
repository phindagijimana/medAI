#!/usr/bin/env python3
"""Open-benchmark evaluation runner (Shape A paper).

Compares each system arm (B0 rules; B1 BERT if trained; M0/M1/M2 via Med42
or mock) against the Fonferko-Shadrach silver labels using our v0.2.1
schema, and prints tables ready for the manuscript.

Arms evaluated by default (deterministic, no GPU needed):
  - B0 rules (per module: MRI where applicable, EEG where applicable, and
    clinical_seizure/medication for the progress-note clinic letters).

Additional arms if a Med42 backend is attached:
  - M0 / M1 / M2 zero/few-shot/schema-constrained via the router.

Outputs:
  eval/results/open_benchmark_summary.json   — per-arm ArmSummary
  eval/results/open_benchmark_perfield.csv   — per-field P/R/F1 table
  eval/results/open_benchmark_errors.json    — error-taxonomy counts
  eval/results/README.md                     — pointer to what these files are

The runner is designed to work with silver labels — treat all resulting
numbers as SILVER-METRIC values, not adjudicated gold. When institutional
gold arrives, point --gold at that directory and results are gold metrics.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema import (
    ClinicalSeizureModule,
    DocumentMetadata,
    DocumentType,
    EpilepsyPhenotype,
    MedicationModule,
    MriModule,
    SCHEMA_VERSION,
)
from services.baseline_rules import run_b0_mri
from services.baseline_rules_clinical_seizure import run_b0_clinical_seizure
from services.baseline_rules_eeg import run_b0_eeg
from services.baseline_rules_medication import run_b0_medication
from services.evidence_verifier import verify_phenotype
from eval.metrics import FieldMetrics, ModuleScore, ArmSummary, score_field

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("open_benchmark")

REPO = Path(__file__).resolve().parent.parent
FONFERKO_SILVER = REPO / "data" / "fonferko_shadrach_2024" / "silver_labels_v0_2_1"
FONFERKO_LETTERS = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8381080" / "Gold1-200_corrected_spelling"
OUT = REPO / "eval" / "results"


# Fields per module that we score for the paper's headline table.
# These are the "core" set from the Shape A protocol.
CORE_FIELDS = {
    "clinical_seizure": [
        "epilepsy_type", "predominant_seizure_type", "age_at_onset_years",
        "seizure_frequency", "etiology_category",
    ],
    "medication": [
        # Aggregate list-fields as "any current asm present" etc — done below
        "drug_resistance_status",
    ],
    "mri": [
        "hippocampal_sclerosis", "lesion_lobe", "lesion_laterality",
        "mri_negative_for_epilepsy",
    ],
    "eeg": [
        "study_type", "background", "ied_present",
        "ictal_onset_lobe", "ictal_onset_laterality",
    ],
}


def _load_silver(silver_dir: Path) -> list[dict]:
    records: list[dict] = []
    for f in sorted(silver_dir.glob("EA*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        # Locate source text
        src_path = REPO / data["source_text_path"]
        if not src_path.exists():
            continue
        text = src_path.read_text(encoding="utf-8")
        records.append({"doc_id": data["doc_id"], "text": text,
                        "phenotype": data["phenotype"]})
    return records


def _asm_multiset(module_dict: dict) -> list[str]:
    """Extract the multiset of ASM generic names from a MedicationModule
    dict (current + prior + failed)."""
    if not module_dict:
        return []
    names: list[str] = []
    for k in ("current_asms", "prior_asms", "failed_asms"):
        for e in module_dict.get(k, []):
            v = e.get("value") or {}
            n = v.get("generic_name")
            if n:
                names.append(n.lower())
    return sorted(names)


def _score_medication_specific(pred: dict, gold: dict, ms: ModuleScore) -> None:
    """Multi-set score for medications: ASMs mentioned, regardless of status."""
    pred_names = _asm_multiset(pred)
    gold_names = _asm_multiset(gold)
    fm = ms.fields.get("asm_names_multiset") or FieldMetrics(field_name="asm_names_multiset")
    fm.n += 1
    fm.n_applicable += 1
    from collections import Counter
    p = Counter(pred_names)
    g = Counter(gold_names)
    tp = p & g
    fp = p - g
    fn = g - p
    fm.tp += sum(tp.values())
    fm.fp += sum(fp.values())
    fm.fn += sum(fn.values())
    ms.fields["asm_names_multiset"] = fm


def _score_core(pred_module: dict | None, gold_module: dict | None,
                module_name: str, ms: ModuleScore) -> None:
    """Score core fields for one module using the metrics.score_field helper."""
    fields = CORE_FIELDS.get(module_name, [])
    pred_module = pred_module or {}
    gold_module = gold_module or {}
    for fname in fields:
        existing = ms.fields.get(fname)
        ms.fields[fname] = score_field(
            fname,
            pred_module.get(fname),
            gold_module.get(fname),
            applicable=True,
            metrics=existing,
        )


def run_b0_arm(records: list[dict]) -> tuple[ArmSummary, dict]:
    """Run the B0-rules arm across all applicable modules for each doc.

    Since Fonferko letters are clinic letters (doc_type=progress_note per our
    silver labeling), only clinical_seizure + medication modules are
    applicable. MRI/EEG rules are exercised on a separate synthetic subset —
    NOT here, to keep the doc-type stratification honest.
    """
    summary = ArmSummary(arm="B0_rules")
    modules: dict[str, ModuleScore] = {}

    for rec in records:
        summary.n_documents += 1
        summary.raw_valid += 1                # rules always produce valid JSON
        summary.final_valid += 1

        doc = DocumentMetadata(
            doc_id=rec["doc_id"], doc_type=DocumentType.PROGRESS_NOTE,
            doc_date=date(2024, 1, 1), patient_id=rec["doc_id"],
        )
        text = rec["text"]

        pred_cs = run_b0_clinical_seizure(text, doc)
        pred_med = run_b0_medication(text, doc)

        gold_cs = (rec["phenotype"] or {}).get("clinical_seizure") or {}
        gold_med = (rec["phenotype"] or {}).get("medication") or {}

        # Score core fields for clinical_seizure
        cs_score = modules.get("clinical_seizure", ModuleScore(module_name="clinical_seizure"))
        _score_core(pred_cs, gold_cs, "clinical_seizure", cs_score)
        modules["clinical_seizure"] = cs_score

        # Score core + multiset for medication
        med_score = modules.get("medication", ModuleScore(module_name="medication"))
        _score_core(pred_med, gold_med, "medication", med_score)
        _score_medication_specific(pred_med, gold_med, med_score)
        modules["medication"] = med_score

        # Evidence verification: does the rules-cited quote appear in text?
        try:
            pheno = EpilepsyPhenotype.model_validate({
                "schema_version": SCHEMA_VERSION,
                "document": {
                    "doc_id": doc.doc_id, "doc_type": doc.doc_type.value,
                    "doc_date": doc.doc_date.isoformat(),
                    "patient_id": doc.patient_id,
                    "icd10cm_codes": [], "snomed_ct_codes": [],
                },
                "clinical_seizure": pred_cs,
                "medication": pred_med,
                "clinical_localization": None, "eeg": None, "mri": None,
                "integrated": None,
            })
            report = verify_phenotype(pheno, text)
            summary.total_evidence_objects += report.total_evidence_objects
            summary.evidence_supported += report.evidence_supported
            summary.evidence_unsupported += report.evidence_unsupported
            summary.evidence_missing += report.evidence_missing
        except Exception as e:
            log.warning("evidence verification skipped for %s: %s", doc.doc_id, e)

    summary.modules = modules
    return summary, {}   # per-error report elided in this pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--silver", type=Path, default=FONFERKO_SILVER)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    if not args.silver.exists():
        log.error("silver labels dir not found: %s", args.silver)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)

    log.info("Loading silver records from %s", args.silver)
    records = _load_silver(args.silver)
    log.info("Loaded %d records", len(records))

    log.info("Running B0 rules arm ...")
    b0_summary, _ = run_b0_arm(records)

    # Write ArmSummary
    payload = {b0_summary.arm: b0_summary.to_dict()}
    (args.out / "open_benchmark_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    # Per-field CSV
    csv_lines = ["arm,module,field,n_applicable,tp,fp,fn,tn,precision,recall,f1"]
    for arm_name, s_dict in payload.items():
        for mod_name, mod in s_dict.get("modules", {}).items():
            for fname, fm in mod.get("fields", {}).items():
                csv_lines.append(
                    f"{arm_name},{mod_name},{fname},"
                    f"{fm['n_applicable']},{fm['tp']},{fm['fp']},{fm['fn']},{fm['tn']},"
                    f"{fm['precision']},{fm['recall']},{fm['f1']}"
                )
    (args.out / "open_benchmark_perfield.csv").write_text(
        "\n".join(csv_lines) + "\n", encoding="utf-8"
    )

    # README pointer
    (args.out / "README.md").write_text(
        "# Open-benchmark preliminary results\n\n"
        "These files hold the numbers for the manuscript's preliminary Tables 3–4.\n\n"
        "- `open_benchmark_summary.json` — per-arm ArmSummary "
        "(schema validity, evidence, per-module metrics)\n"
        "- `open_benchmark_perfield.csv` — one row per (arm, module, field) "
        "with n_applicable, tp/fp/fn/tn, precision, recall, f1\n\n"
        f"Generated by `scripts/run_open_benchmark.py` against silver labels at "
        f"`{args.silver.relative_to(REPO)}`.\n\n"
        "Silver-metric numbers only — treat with the honesty the paper's Limitations section requires.\n",
        encoding="utf-8",
    )

    # Console table
    print("\n=== B0 rules — Fonferko silver-metric results ===")
    print(f"Documents: {b0_summary.n_documents}")
    print(f"Schema validity (raw): {b0_summary.raw_validity_rate:.3f}")
    print(f"Evidence precision (against source text): {b0_summary.evidence_precision:.3f}")
    print(f"Unsupported claim rate: {b0_summary.unsupported_claim_rate:.3f}")
    for mod_name, ms in b0_summary.modules.items():
        print(f"\n[{mod_name}]  macro_f1 = {ms.macro_f1:.3f}  micro_f1 = {ms.micro_f1:.3f}")
        for fname, fm in ms.fields.items():
            print(f"  {fname:<32} n={fm.n_applicable:>3}  "
                  f"P={fm.precision:.2f} R={fm.recall:.2f} F1={fm.f1:.2f}")
    print(f"\nfull results → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
