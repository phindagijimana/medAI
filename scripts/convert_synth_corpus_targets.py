#!/usr/bin/env python3
"""Convert v1 synthetic-corpus semantic plans → MedAI-EPI Evidence[T] targets.

Extended vocabulary compared to Phase 6D.2 pilot's converter — this handles
the full 8-field EpilepsyPhenotype vocabulary emitted by
`scripts/synth_patient_sampler.py`:

    EP_TYPE, SZ_TYPE, AGE_AT_ONSET_YEARS, SZ_FREQ,
    ETIOLOGY_CATEGORY, ETIOLOGY_SPECIFICS, DRE_STATUS,
    CURRENT_ASMS, MRI_FINDING

Emits one target_phenotype.json per patient at:

    data/episynth_corpus/v1/targets/{PID}/target_phenotype.json

Every emitted target validates against the v0.2.1 EpilepsyPhenotype schema
and is directly usable as a fine-tuning label.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from schema import (
    Certainty, ClinicalSeizureModule, DocumentMetadata, DocumentType,
    DrugResistanceStatus, EpilepsyPhenotype, EpilepsyType, EtiologyCategory,
    Evidence, MedicationModule, MriFinding, MriModule, SeizureType,
    TemporalStatus,
)
from schema.enums import Laterality, LobarLocalization, MedicationStatus
from schema.ontology import EtiologySpecifics, Medication, SeizureFrequency

CORPUS_ROOT = REPO / "data" / "episynth_corpus" / "v1"
PATIENTS_DIR = CORPUS_ROOT / "patients"
TARGETS_DIR = CORPUS_ROOT / "targets"
SOURCE_DATE = date(2026, 9, 25)


# ---------------------------------------------------------------------------
# Field mappings — sampler vocabulary → v0.2.1 enum
# ---------------------------------------------------------------------------

_EP_TYPE_MAP = {
    "focal": EpilepsyType.FOCAL,
    "generalized": EpilepsyType.GENERALIZED,
    "combined_generalized_and_focal": EpilepsyType.COMBINED_FOCAL_GENERALIZED,
    "unknown": EpilepsyType.UNKNOWN,
}

_SZ_TYPE_MAP = {
    # Sampler emits SeizureType enum-value strings directly, so this is a
    # sanity-check pass rather than a real translation. Any string not in
    # this set is treated as "unknown seizure type".
    v.value: v for v in SeizureType
}

_ETIOLOGY_MAP = {
    "structural": EtiologyCategory.STRUCTURAL,
    "genetic": EtiologyCategory.GENETIC,
    "infectious": EtiologyCategory.INFECTIOUS,
    "immune": EtiologyCategory.IMMUNE,
    "metabolic": EtiologyCategory.METABOLIC,
    "unknown": EtiologyCategory.UNKNOWN,
}

_MRI_FINDING_MAP = {v.value: v for v in MriFinding}
_MRI_FINDING_MAP["nonspecific_white_matter_changes"] = MriFinding.OTHER_LESION
_MRI_FINDING_MAP["incidental_lesion"] = MriFinding.OTHER_LESION

_DRE_MAP = {
    "drug_resistant": DrugResistanceStatus.DRUG_RESISTANT,
    "drug_responsive": DrugResistanceStatus.DRUG_RESPONSIVE,
    "indeterminate": DrugResistanceStatus.UNDEFINED,
}


def _ev(value, evidence_text: str, doc_id: str) -> Evidence:
    return Evidence(
        value=value,
        certainty=Certainty.DEFINITE,
        temporal_status=TemporalStatus.CURRENT,
        evidence_text=evidence_text,
        source_doc_id=doc_id,
        source_doc_type=DocumentType.PROGRESS_NOTE,
        source_date=SOURCE_DATE,
    )


def _nd(doc_id: str) -> Evidence:
    return Evidence(
        value=None,
        certainty=Certainty.NOT_DOCUMENTED,
        temporal_status=TemporalStatus.UNSPECIFIED,
        evidence_text=None,
        source_doc_id=doc_id,
        source_doc_type=DocumentType.PROGRESS_NOTE,
        source_date=SOURCE_DATE,
    )


def _asm_evidence(drug: dict, doc_id: str) -> Evidence:
    med = Medication(
        generic_name=drug["generic_name"],
        status=MedicationStatus.CURRENT,
    )
    return _ev(med, f"{drug['generic_name']} current", doc_id)


def _plan_to_target(pid: str, plan: dict) -> EpilepsyPhenotype:
    reqs = {r["field"]: r["value"] for r in plan.get("required_assertions", [])}
    doc = DocumentMetadata(
        doc_id=pid, patient_id=pid,
        doc_type=DocumentType.PROGRESS_NOTE, doc_date=SOURCE_DATE,
    )
    nd = _nd(pid)

    # -- Clinical Seizure module -------------------------------------------
    cs: dict = dict(
        epilepsy_type=nd, predominant_seizure_type=nd,
        other_seizure_types=[], awareness=nd, semiology_text=nd,
        age_at_onset_years=nd, seizure_frequency=nd,
        other_seizure_frequencies=[], status_epilepticus_history=nd,
        etiology_category=nd, etiology_details_text=nd,
        etiology_specifics=nd,
        focal_motor_onset=nd, focal_nonmotor_onset=nd,
    )
    if "EP_TYPE" in reqs:
        cs["epilepsy_type"] = _ev(_EP_TYPE_MAP[reqs["EP_TYPE"]], reqs["EP_TYPE"], pid)
    if "SZ_TYPE" in reqs and reqs["SZ_TYPE"] in _SZ_TYPE_MAP:
        cs["predominant_seizure_type"] = _ev(
            _SZ_TYPE_MAP[reqs["SZ_TYPE"]], reqs["SZ_TYPE"], pid,
        )
    if "AGE_AT_ONSET_YEARS" in reqs:
        cs["age_at_onset_years"] = _ev(
            float(reqs["AGE_AT_ONSET_YEARS"]),
            f"age at onset {reqs['AGE_AT_ONSET_YEARS']}", pid,
        )
    if "SZ_FREQ" in reqs:
        sf_v = reqs["SZ_FREQ"]
        if sf_v.get("seizure_free"):
            sf = SeizureFrequency(
                raw_text="seizure free", period="unspecified",
                seizure_free=True, count_min=0, count_max=0,
            )
            ev_text = "seizure free"
        else:
            q = float(sf_v["quantity"])
            unit = sf_v["unit"]
            if unit not in ("day", "week", "month", "year"):
                unit = "unspecified"
            sf = SeizureFrequency(
                raw_text=f"{q} per {unit}", period=unit,   # type: ignore
                count_min=q, count_max=q,
            )
            ev_text = f"{q} per {unit}"
        cs["seizure_frequency"] = _ev(sf, ev_text, pid)
    if "ETIOLOGY_CATEGORY" in reqs:
        cs["etiology_category"] = _ev(
            _ETIOLOGY_MAP[reqs["ETIOLOGY_CATEGORY"]],
            reqs["ETIOLOGY_CATEGORY"], pid,
        )
    if "ETIOLOGY_SPECIFICS" in reqs:
        es = reqs["ETIOLOGY_SPECIFICS"] or {}
        _ab_map = {
            "lgi1": "anti_lgi1", "caspr2": "anti_caspr2",
            "gad65": "anti_gad65", "nmda_receptor": "anti_nmdar",
        }
        ab = es.get("causative_antibody")
        specifics = EtiologySpecifics(
            causative_gene=es.get("causative_gene"),
            causative_variant=es.get("causative_variant"),
            causative_antibody=_ab_map.get(ab, ab) if ab else None,
        )
        cs["etiology_specifics"] = _ev(
            specifics,
            json.dumps(es, ensure_ascii=False),
            pid,
        )

    # -- Medication module -------------------------------------------------
    med: dict = dict(
        current_asms=[], prior_asms=[], failed_asms=[],
        adverse_effects_text=nd, drug_resistance_status=nd,
        surgery_history=[], non_drug_therapies=[],
    )
    if "CURRENT_ASMS" in reqs:
        med["current_asms"] = [_asm_evidence(d, pid) for d in reqs["CURRENT_ASMS"]]
    if "DRE_STATUS" in reqs and reqs["DRE_STATUS"] in _DRE_MAP:
        med["drug_resistance_status"] = _ev(
            _DRE_MAP[reqs["DRE_STATUS"]], reqs["DRE_STATUS"], pid,
        )

    # -- MRI module --------------------------------------------------------
    mri = None
    if "MRI_FINDING" in reqs:
        mf_str = reqs["MRI_FINDING"]
        mf_enum = _MRI_FINDING_MAP.get(mf_str, MriFinding.OTHER_LESION)
        # v0.2.1 MriModule requires consistency: HS-boolean matches findings,
        # FCD-boolean matches findings — we set them consistently.
        findings_list = [_ev(mf_enum, mf_str, pid)]
        hs_bool = _ev(True, "hippocampal sclerosis on MRI", pid) if mf_enum == MriFinding.HIPPOCAMPAL_SCLEROSIS else _ev(False, "no HS on MRI", pid)
        fcd_bool = _ev(True, "focal cortical dysplasia on MRI", pid) if mf_enum in (
            MriFinding.FOCAL_CORTICAL_DYSPLASIA, MriFinding.FCD_PALMINI_I,
            MriFinding.FCD_PALMINI_IIA, MriFinding.FCD_PALMINI_IIB,
            MriFinding.MOGHE,
        ) else _ev(False, "no FCD on MRI", pid)
        mri = MriModule(
            overall_normal=_ev(mf_enum == MriFinding.NORMAL, "MRI reviewed", pid),
            findings=findings_list,
            lesion_lobe=nd, lesion_laterality=nd,
            hippocampal_sclerosis=hs_bool,
            focal_cortical_dysplasia=fcd_bool,
            mri_negative_for_epilepsy=_ev(mf_enum == MriFinding.MRI_NEGATIVE, "MRI reviewed", pid),
            field_strength_tesla=nd,
        )

    return EpilepsyPhenotype(
        document=doc,
        clinical_seizure=ClinicalSeizureModule(**cs),
        medication=MedicationModule(**med),
        mri=mri,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patients-glob", default="P*.json")
    args = ap.parse_args()

    TARGETS_DIR.mkdir(parents=True, exist_ok=True)
    n_ok = n_err = 0
    for pp in sorted(PATIENTS_DIR.glob(args.patients_glob)):
        if pp.stem.endswith("_case"):
            continue
        pid = pp.stem
        plan = json.loads(pp.read_text())
        try:
            target = _plan_to_target(pid, plan)
        except Exception as e:
            print(f"  {pid}: SKIP ({e})", file=sys.stderr)
            n_err += 1
            continue
        out_dir = TARGETS_DIR / pid
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "target_phenotype.json").write_text(
            target.model_dump_json(indent=2), encoding="utf-8",
        )
        n_ok += 1
    print(f"Converted {n_ok} plans → targets ({n_err} errors) under {TARGETS_DIR}")


if __name__ == "__main__":
    main()
