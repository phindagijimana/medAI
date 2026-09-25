#!/usr/bin/env python3
"""Epidemiology-informed synthetic epilepsy patient sampler.

Produces N EpilepsyPhenotype records at ILAE-2017 field granularity,
sampled from a distribution that reflects real epilepsy epidemiology
plus deliberate over-sampling of rare-but-important phenotypes.

Distribution (informed by Kwan & Brodie 2000, ILAE 2017 classification
prevalence data, and Fonferko-Shadrach corpus statistics):

    EP_TYPE:
        60% focal, 30% generalized, 5% combined, 5% unknown

    SZ_TYPE (given EP_TYPE):
        focal:      50% focal_impaired_awareness / 25% focal_aware /
                    25% focal_to_bilateral_tonic_clonic
        generalized: 60% generalized_tonic_clonic / 25% absence_typical /
                    15% myoclonic
        combined:   50/50 focal_impaired_awareness vs generalized_tonic_clonic
        unknown:    unknown-onset

    ETIOLOGY:
        40% structural, 15% genetic, 5% infectious, 5% immune,
        5% metabolic, 30% unknown

    DRE_STATUS:
        30% drug_resistant, 60% drug_responsive, 10% indeterminate

    AGE_AT_ONSET:
        Bimodal — childhood (5-15y, ~40%) + adult (20-40y, ~40%) +
        elderly (>60y, ~20%)

    SZ_FREQ (units realistic to freshness of the note):
        seizure_free (30%), <=1/year (15%), <=1/month (30%),
        >=1/week (25%)

    MRI_FINDING (correlated with etiology):
        Structural etiology → 70% chance of visible finding (HS 35%,
        FCD 25%, tumor 10%, encephalomalacia 15%, other 15%)
        Non-structural etiology → 15% chance of incidental finding

    CURRENT_ASMS:
        DRE patients: 2-4 concurrent ASMs
        Non-DRE:     1-2 concurrent ASMs
        Drug list: LTG, LEV, CBZ, TPM, VPA, LCM, OXC, ZNS, PER, BRV

Rare-phenotype over-sampling (~20% of the corpus):
    - Etiology_specifics.causative_gene (SCN1A, DEPDC5, KCNQ2, PCDH19,
      STXBP1) with realistic HGVS-like variant strings
    - MRI Palmini FCD IIa/IIb subtypes
    - MOGHE
    - Autoimmune causative_antibody (LGI1, GAD65, CASPR2)
    - MRI-negative focal epilepsy (deliberate stress)

Usage:
    python scripts/synth_patient_sampler.py --n 500 --seed 0 \
           --output-dir data/episynth_corpus/v1/patients/

Emits per patient (compatible with Phase 6D.1 v2 freeze conventions):
    P000500.json             — semantic plan (allowed/required/prohibited)
    P000500_case.json        — pilot case (events)
    P000500_target.json      — Evidence[T] target for fine-tuning
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


# ---------------------------------------------------------------------------
# Distributions and vocabularies
# ---------------------------------------------------------------------------

# ILAE 2017 top-level epilepsy types
EP_TYPES = [
    ("focal", 0.60),
    ("generalized", 0.30),
    ("combined_generalized_and_focal", 0.05),
    ("unknown", 0.05),
]

# ILAE 2017 basic seizure types conditional on epilepsy type
SZ_TYPE_GIVEN_EP = {
    "focal": [
        ("focal_impaired_awareness", 0.50),
        ("focal_aware", 0.25),
        ("focal_to_bilateral_tonic_clonic", 0.25),
    ],
    "generalized": [
        ("generalized_tonic_clonic", 0.60),
        ("absence_typical", 0.25),
        ("myoclonic", 0.15),
    ],
    "combined_generalized_and_focal": [
        ("focal_impaired_awareness", 0.50),
        ("generalized_tonic_clonic", 0.50),
    ],
    "unknown": [
        ("unknown_onset_tonic_clonic", 0.60),
        ("unknown_onset_motor_other", 0.20),
        ("unknown_onset_nonmotor", 0.20),
    ],
}

ETIOLOGIES = [
    ("structural", 0.40),
    ("genetic", 0.15),
    ("infectious", 0.05),
    ("immune", 0.05),
    ("metabolic", 0.05),
    ("unknown", 0.30),
]

# MRI findings conditional on etiology
MRI_FINDING_GIVEN_STRUCTURAL = [
    ("hippocampal_sclerosis", 0.35),
    ("focal_cortical_dysplasia", 0.25),
    ("tumor", 0.10),
    ("encephalomalacia", 0.15),
    ("vascular_malformation", 0.10),
    ("normal", 0.05),
]

MRI_FINDING_GIVEN_NONSTRUCTURAL = [
    ("normal", 0.85),
    ("nonspecific_white_matter_changes", 0.10),
    ("incidental_lesion", 0.05),
]

# Common ASMs (RxNorm-mappable generic names)
ASM_LIST = [
    "lamotrigine", "levetiracetam", "carbamazepine",
    "topiramate", "valproate", "lacosamide",
    "oxcarbazepine", "zonisamide", "perampanel", "brivaracetam",
]

# HGNC epilepsy-gene short-list for rare-phenotype oversampling
EPILEPSY_GENES = [
    ("SCN1A", "c.5734C>T"),
    ("DEPDC5", "c.4396C>T"),
    ("KCNQ2", "c.881C>T"),
    ("PCDH19", "c.918G>A"),
    ("STXBP1", "c.902A>G"),
]

# Autoimmune antibodies (matches EtiologySpecifics.causative_antibody enum
# names — kept lowercase to avoid enum import complexity here)
CAUSATIVE_ANTIBODIES = ["lgi1", "gad65", "caspr2", "nmda_receptor"]

# Palmini FCD fine-grained subtypes for rare-phenotype oversampling
FCD_SUBTYPES = [
    "focal_cortical_dysplasia",   # generic FCD (Palmini I family)
    "fcd_palmini_iia",             # FCD Type IIa
    "fcd_palmini_iib",             # FCD Type IIb (dysmorphic + balloon cells)
    "moghe",                       # MOGHE — mild malformation, oligodendroglial hyperplasia
]


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------


def _weighted_choice(rng: random.Random, options: list[tuple[str, float]]) -> str:
    weights = [w for _, w in options]
    labels = [x for x, _ in options]
    return rng.choices(labels, weights=weights, k=1)[0]


def _age_at_onset(rng: random.Random) -> int:
    """Bimodal: childhood peak + adult peak + elderly tail."""
    which = rng.random()
    if which < 0.4:
        return int(rng.triangular(2, 18, 10))
    elif which < 0.8:
        return int(rng.triangular(18, 45, 30))
    else:
        return int(rng.triangular(50, 85, 65))


def _sz_freq(rng: random.Random, seizure_free_rate: float = 0.30) -> dict:
    """Realistic seizure-frequency distribution."""
    r = rng.random()
    if r < seizure_free_rate:
        return {"seizure_free": True, "quantity": 0, "unit": "month"}
    r2 = rng.random()
    if r2 < 0.20:
        return {"quantity": rng.randint(1, 3), "unit": "year"}
    if r2 < 0.60:
        return {"quantity": rng.randint(1, 5), "unit": "month"}
    return {"quantity": rng.randint(1, 7), "unit": "week"}


def _current_asms(rng: random.Random, dre: bool) -> list[dict]:
    """1-4 concurrent ASMs. DRE cases get more."""
    n = rng.randint(2, 4) if dre else rng.randint(1, 2)
    n = min(n, len(ASM_LIST))
    drugs = rng.sample(ASM_LIST, k=n)
    return [{"generic_name": d, "status": "current"} for d in drugs]


def _mri_finding(rng: random.Random, etiology: str) -> str:
    if etiology == "structural":
        base = _weighted_choice(rng, MRI_FINDING_GIVEN_STRUCTURAL)
        # 20% of structural-FCD cases get a Palmini subtype for rare-phenotype coverage
        if base == "focal_cortical_dysplasia" and rng.random() < 0.20:
            return rng.choice(FCD_SUBTYPES)
        return base
    return _weighted_choice(rng, MRI_FINDING_GIVEN_NONSTRUCTURAL)


def _etiology_specifics(rng: random.Random, etiology: str, oversample_rare: bool) -> dict | None:
    """Populate causative_gene / _antibody / _variant on relevant etiology
    categories. Over-sampled to ~30% of eligible patients so the rare
    long-tail is represented in training data."""
    if etiology == "genetic" and (oversample_rare or rng.random() < 0.60):
        gene, variant = rng.choice(EPILEPSY_GENES)
        return {"causative_gene": gene, "causative_variant": variant}
    if etiology == "immune" and (oversample_rare or rng.random() < 0.60):
        return {"causative_antibody": rng.choice(CAUSATIVE_ANTIBODIES)}
    return None


# ---------------------------------------------------------------------------
# Patient generation
# ---------------------------------------------------------------------------


def _sample_patient(rng: random.Random, patient_index: int, oversample_rare: bool) -> dict:
    ep_type = _weighted_choice(rng, EP_TYPES)
    sz_type = _weighted_choice(rng, SZ_TYPE_GIVEN_EP[ep_type])
    etiology = _weighted_choice(rng, ETIOLOGIES)
    aoo = _age_at_onset(rng)
    freq = _sz_freq(rng)
    dre = rng.random() < 0.30
    asms = _current_asms(rng, dre)
    mri = _mri_finding(rng, etiology)
    etio_specs = _etiology_specifics(rng, etiology, oversample_rare)
    pid = f"P{patient_index:06d}"
    return {
        "patient_id": pid,
        "ep_type": ep_type,
        "sz_type": sz_type,
        "etiology": etiology,
        "etiology_specifics": etio_specs,
        "age_at_onset_years": aoo,
        "seizure_frequency": freq,
        "dre_status": "drug_resistant" if dre else "drug_responsive",
        "current_asms": asms,
        "mri_finding": mri,
    }


def _to_semantic_plan(pat: dict) -> dict:
    """Semantic plan compatible with Phase 6D.1 v2 freeze conventions.

    Extended vocabulary — the pilot only had EP_TYPE / SZ_FREQ / EEG_RESULT.
    We keep those field-name strings for backwards compatibility and add
    SZ_TYPE / AGE_AT_ONSET / ETIOLOGY / MRI_FINDING / DRE / CURRENT_ASMS.
    """
    reqs = []
    events = []
    e_index = 1

    def _push(field: str, value: Any, note: str | None = None):
        nonlocal e_index
        eid = f"E{e_index:03d}"
        e_index += 1
        ev = {"id": eid, "field": field, "value": value, "source": "MEDAI-EPI ILAE 2017"}
        if note:
            ev["fixture_note"] = note
        events.append(ev)
        reqs.append({"event_id": eid, "field": field, "value": value})

    _push("EP_TYPE", pat["ep_type"])
    _push("SZ_TYPE", pat["sz_type"])
    _push("AGE_AT_ONSET_YEARS", pat["age_at_onset_years"])
    _push("SZ_FREQ", pat["seizure_frequency"])
    _push("ETIOLOGY_CATEGORY", pat["etiology"])
    if pat["etiology_specifics"]:
        _push("ETIOLOGY_SPECIFICS", pat["etiology_specifics"])
    _push("DRE_STATUS", pat["dre_status"])
    _push("CURRENT_ASMS", pat["current_asms"])
    if pat["etiology"] == "structural" or pat["mri_finding"] != "normal":
        _push("MRI_FINDING", pat["mri_finding"])

    return {
        "patient_id": pat["patient_id"],
        "document_family": "epilepsy_clinic_letter",
        "allowed_source_event_ids": [e["id"] for e in events],
        "required_assertions": reqs,
        "prohibited_assertions": [],
        "optional_assertions": [],
        "information_scope_status": "MEDAI-PROPOSED EXPERIMENTAL INPUT CONTROL",
        "_meta": {
            "sampler": "scripts/synth_patient_sampler.py",
            "sampler_version": "v1.0",
        },
    }


def _to_case(pat: dict, plan: dict) -> dict:
    return {
        "patient_id": pat["patient_id"],
        "family": plan["document_family"],
        "scenario": f"{pat['ep_type']}_{pat['etiology']}",
        "events": [
            {"id": e["id"], "field": e["field"], "value": e["value"], "source": e.get("source", "")}
            for e in _plan_events_from_reqs(plan)
        ],
        "fixture_status": "MEDAI-PROPOSED COVERAGE FIXTURE — NOT PREVALENCE",
    }


def _plan_events_from_reqs(plan: dict) -> list[dict]:
    """Reconstruct event list from required_assertions (they're keyed the same)."""
    return [
        {"id": r["event_id"], "field": r["field"], "value": r["value"], "source": "MEDAI-EPI"}
        for r in plan["required_assertions"]
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500,
                     help="Number of synthetic patients to sample")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--start-index", type=int, default=500,
                     help="Starting patient index (avoids collision with P000001-P000006 pilot)")
    ap.add_argument("--output-dir", default="data/episynth_corpus/v1/patients")
    ap.add_argument("--rare-oversample", type=float, default=0.20,
                     help="Fraction of patients to force rare-phenotype oversampling")
    args = ap.parse_args()

    outdir = Path(args.output_dir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    for i in range(args.n):
        idx = args.start_index + i
        oversample = rng.random() < args.rare_oversample
        pat = _sample_patient(rng, idx, oversample)
        plan = _to_semantic_plan(pat)
        case = _to_case(pat, plan)

        (outdir / f"{pat['patient_id']}.json").write_text(
            json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        (outdir / f"{pat['patient_id']}_case.json").write_text(
            json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8",
        )

    print(f"Sampled {args.n} patients (P{args.start_index:06d}..P{args.start_index+args.n-1:06d})")
    print(f"Output: {outdir}")


if __name__ == "__main__":
    main()
