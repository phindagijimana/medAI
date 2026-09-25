#!/usr/bin/env python3
"""Convert Phase 6D.1 v2 semantic plans → MedAI-EPI Evidence[T] extraction
targets.

For each pilot case (P001…P006) the freeze provides a semantic_plan with
`required_assertions` naming which fields must be present. Each assertion has
a `field` in the Phase 6D.1 vocabulary (`EP_TYPE`, `SZ_FREQ`, `EEG_RESULT`, …)
which maps to a specific field in the MedAI-EPI v0.2.1 ontology.

This script produces one `target_phenotype.json` per pilot patient — a fully
validated `EpilepsyPhenotype` object that the current app can accept as the
gold reference for evaluating an extractor.

The output pairs each rendered document with a schema-conforming target:

    input   :  data/episynth_pilot/run_001/<arm>/<cond>/<pid>/output.txt
    target  :  data/episynth_pilot/run_001/targets/<pid>/target_phenotype.json

The mapping is intentionally minimal and MEDAI-PROPOSED: only the fields the
freeze actually authorizes. Unspecified fields are set to `not_documented`
per §Phase 3D/4.1 semantic closure — no hallucination of ground truth.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from schema import (
    Awareness, Certainty, ClinicalSeizureModule, DocumentMetadata,
    DocumentType, EegBackground, EegModule, EegStudyType, EpilepsyPhenotype,
    EpilepsyType, Evidence, IntegratedPhenotypeModule, MedicationModule,
    SeizureType, TemporalStatus,
)
from schema.ontology import SeizureFrequency

FREEZE_DIR = Path(
    "/tmp/phase6d1v2/MedAI_Phase6D1_v2_GPT_MultiGenerator_PreRun_Freeze"
)
RUN_DIR = REPO / "data" / "episynth_pilot" / "run_001"
TARGETS_DIR = RUN_DIR / "targets"

# The freeze date — used as the "source_date" on every Evidence record so
# that the target is temporally consistent with the rendered documents.
SOURCE_DATE = date(2026, 9, 25)


# ---------------------------------------------------------------------------
# Field-mapping tables — the semantic bridge between freeze vocabulary and
# MedAI-EPI v0.2.1 enums. All items here are MEDAI-PROPOSED under Phase
# 4B.1/6D.3 §machine-projection policy.
# ---------------------------------------------------------------------------

_EP_TYPE_MAP = {
    "Focal": EpilepsyType.FOCAL,
    "Generalized": EpilepsyType.GENERALIZED,
    "Combined generalized and focal": EpilepsyType.COMBINED_FOCAL_GENERALIZED,
    "Unknown": EpilepsyType.UNKNOWN,
}


def _sf_from_value(v: dict) -> SeizureFrequency:
    """Convert freeze SZ_FREQ {quantity, unit} → schema SeizureFrequency."""
    q = float(v.get("quantity"))
    unit = str(v.get("unit", "unspecified")).lower()
    if unit not in ("day", "week", "month", "year"):
        unit = "unspecified"
    return SeizureFrequency(
        raw_text=f"{v.get('quantity')} per {v.get('unit')}",
        period=unit,           # type: ignore
        count_min=q, count_max=q,
    )


def _evidence(value, evidence_text: str, doc_id: str) -> Evidence:
    return Evidence(
        value=value,
        certainty=Certainty.DEFINITE,
        temporal_status=TemporalStatus.CURRENT,
        evidence_text=evidence_text,
        source_doc_id=doc_id,
        source_doc_type=DocumentType.PROGRESS_NOTE,
        source_date=SOURCE_DATE,
    )


def _not_documented(doc_id: str) -> Evidence:
    return Evidence(
        value=None,
        certainty=Certainty.NOT_DOCUMENTED,
        temporal_status=TemporalStatus.UNSPECIFIED,
        evidence_text=None,
        source_doc_id=doc_id,
        source_doc_type=DocumentType.PROGRESS_NOTE,
        source_date=SOURCE_DATE,
    )


# ---------------------------------------------------------------------------
# Per-patient converter
# ---------------------------------------------------------------------------


def _build_target(pid: str, plan: dict, case: dict) -> EpilepsyPhenotype:
    doc = DocumentMetadata(
        doc_id=pid, patient_id=pid,
        doc_type=DocumentType.PROGRESS_NOTE, doc_date=SOURCE_DATE,
    )

    nd = _not_documented(pid)
    cs_fields = dict(
        epilepsy_type=nd, predominant_seizure_type=nd,
        other_seizure_types=[],
        awareness=nd, semiology_text=nd, age_at_onset_years=nd,
        seizure_frequency=nd, other_seizure_frequencies=[],
        status_epilepticus_history=nd,
        etiology_category=nd, etiology_details_text=nd,
        etiology_specifics=nd,
        focal_motor_onset=nd, focal_nonmotor_onset=nd,
    )
    eeg_fields = dict(
        study_type=nd, background=nd,
        ied_present=nd, ied_findings=[],
        seizures_captured=nd, seizures_captured_count=nd,
        ictal_onset_lobe=nd, ictal_onset_laterality=nd,
    )
    med_fields = dict(
        current_asms=[], prior_asms=[], failed_asms=[],
        adverse_effects_text=nd, drug_resistance_status=nd,
        surgery_history=[], non_drug_therapies=[],
    )

    for req in plan.get("required_assertions", []):
        field = req["field"]
        value = req["value"]
        if field == "EP_TYPE":
            enum = _EP_TYPE_MAP.get(value)
            if enum is None:
                raise ValueError(f"Unknown EP_TYPE {value!r} for {pid}")
            cs_fields["epilepsy_type"] = _evidence(enum, value.lower(), pid)
        elif field == "SZ_FREQ":
            sf = _sf_from_value(value)
            cs_fields["seizure_frequency"] = _evidence(
                sf, f"{value['quantity']} per {value['unit']}", pid,
            )
        elif field == "EEG_RESULT":
            # Map to a coarse EEG background flag. There is no dedicated
            # "abnormal EEG boolean" in v0.2.1; we express this by setting
            # `background` to a diffusely-slowed indicator when the plan says
            # "Abnormal", or leave it as the ILAE `NORMAL` background when the
            # plan says "Normal". Note: the granularity mismatch is a known
            # gap per §Phase 3D/4.1 semantic closure.
            if value == "Normal":
                eeg_fields["background"] = _evidence(
                    EegBackground.NORMAL, "normal EEG", pid,
                )
            elif value == "Abnormal":
                eeg_fields["background"] = _evidence(
                    EegBackground.DIFFUSE_SLOWING, "abnormal EEG", pid,
                )
            else:
                raise ValueError(f"Unknown EEG_RESULT {value!r} for {pid}")

    phen = EpilepsyPhenotype(
        document=doc,
        clinical_seizure=ClinicalSeizureModule(**cs_fields),
        medication=MedicationModule(**med_fields),
        eeg=EegModule(**eeg_fields),
    )
    return phen


def main():
    if not FREEZE_DIR.exists():
        print(f"Missing freeze: {FREEZE_DIR}", file=sys.stderr)
        sys.exit(2)
    TARGETS_DIR.mkdir(parents=True, exist_ok=True)

    n = 0
    for plan_path in sorted((FREEZE_DIR / "semantic_plans").glob("P*.json")):
        pid = plan_path.stem
        plan = json.loads(plan_path.read_text())
        case = json.loads((FREEZE_DIR / "pilot_cases" / f"{pid}.json").read_text())

        phen = _build_target(pid, plan, case)

        out_dir = TARGETS_DIR / pid
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "target_phenotype.json").write_text(
            phen.model_dump_json(indent=2), encoding="utf-8",
        )
        n += 1

    print(f"Converted {n} semantic plans → Evidence[T] targets under {TARGETS_DIR}")


if __name__ == "__main__":
    main()
