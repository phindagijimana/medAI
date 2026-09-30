#!/usr/bin/env python3
"""synth-v3 encounter planner.

Consumes per-patient semantic plans emitted by synth_patient_sampler.py, groups
patients into 8 clinical phenotype profiles, and produces a longitudinal
encounter timeline per patient: a sequence of (visit_id, note_type,
note_template, care_setting, provider_persona, visit_date, interval_events,
prior_visit_summary) records.

The output is a single CSV — encounter_manifest.csv — where each row is one
future visit that will later be routed through generate_synth_v3_corpus.py to
GPT to produce the actual note text.

Phenotype profiles derived from the semantic plan:
    newly_diagnosed       — first-ever seizure, no prior AEDs, r/o dx
    drug_responsive       — seizure-free ≥ 1 year on stable regimen
    drug_resistant        — DRE, no surgery yet
    presurgical           — DRE, actively in surgical workup (EMU / PRC / neuropsych)
    post_surgical         — s/p resection/ablation/RNS/DBS
    autoimmune            — MOGHE / GAD65 / LGI1 / autoantibody-positive
    developmental         — pediatric-onset syndromic (SCN1A, KCNQ2, PCDH19)
    status_epilepticus    — recent SE episode driving care sequence

Note-type distribution (aggregate ~500 visits across ~100 patients):
    C progress_note        ~40%
    A new_patient_consult  ~12%
    B telephone_fuv        ~12%
    D emu_admission        ~8%
    E ed_note              ~5%
    F prc_summary          ~5%
    G mri_report           ~5%
    H eeg_report           ~5%
    I neuropsych           ~3%
    J discharge_summary    ~2%
    K triage_call          ~2%
    L inpatient_progress   ~1%

Usage:
    python scripts/synth_v3_encounter_planner.py \\
        --patients-dir data/episynth_corpus/v3/patients \\
        --out-manifest data/episynth_corpus/v3/encounter_manifest.csv \\
        --n-patients 100 \\
        --seed 0
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


# ─── Phenotype profile inference ─────────────────────────────────────────

def _classify_phenotype(plan: dict, rng: random.Random | None = None) -> str:
    """Map a semantic plan to one of 8 clinical phenotype profiles.

    Uses `rng` to break ties between overlapping profiles (e.g. presurgical vs
    plain drug_resistant, or newly_diagnosed vs drug_responsive when a patient
    is on stable AEDs but the frequency isn't zero).
    """
    reqs = {r["field"]: r["value"] for r in plan.get("required_assertions", [])}
    etiology = reqs.get("ETIOLOGY_CATEGORY")
    etio_specs = reqs.get("ETIOLOGY_SPECIFICS") or {}
    dre = reqs.get("DRE_STATUS")
    sz_freq = reqs.get("SZ_FREQ") or {}
    aoo = reqs.get("AGE_AT_ONSET_YEARS", 30)
    asms = reqs.get("CURRENT_ASMS") or []
    causative_gene = etio_specs.get("causative_gene") if isinstance(etio_specs, dict) else None
    causative_ab = etio_specs.get("causative_antibody") if isinstance(etio_specs, dict) else None

    # Rare but strong signals first
    if etiology == "immune" or causative_ab:
        return "autoimmune"
    if causative_gene:
        return "developmental"
    if aoo <= 15 and etiology in ("structural", "genetic"):
        return "developmental"

    if dre == "drug_resistant":
        # Split DRE into presurgical (active workup) vs drug_resistant (non-surgical)
        return "presurgical" if (rng and rng.random() < 0.55) else "drug_resistant"

    # Non-DRE branches
    freq_qty = sz_freq.get("quantity") if isinstance(sz_freq, dict) else None
    freq_unit = sz_freq.get("unit") if isinstance(sz_freq, dict) else None
    is_seizure_free = (freq_qty == 0) or (sz_freq.get("frequency_class") == "seizure_free")

    if is_seizure_free and len(asms) >= 1:
        return "drug_responsive"
    if len(asms) >= 1 and freq_unit in ("year", "years"):
        # ~1/year on AEDs — mostly controlled but not fully seizure-free
        return "drug_responsive" if (rng and rng.random() < 0.60) else "newly_diagnosed"

    return "newly_diagnosed"


PHENOTYPE_TO_NOTE_SEQUENCE = {
    # Each is a sequence template. The planner picks a length (2-8) and slices.
    "newly_diagnosed": [
        ("A", "new_patient_consult"),
        ("G", "mri_report"),
        ("H", "eeg_report"),
        ("C", "progress_note"),
        ("C", "progress_note"),
        ("B", "telephone_fuv"),
    ],
    "drug_responsive": [
        ("C", "progress_note"),
        ("C", "progress_note"),
        ("B", "telephone_fuv"),
        ("C", "progress_note"),
        ("B", "telephone_fuv"),
    ],
    "drug_resistant": [
        ("C", "progress_note"),
        ("E", "ed_note"),
        ("C", "progress_note"),
        ("K", "triage_call"),
        ("C", "progress_note"),
        ("B", "telephone_fuv"),
    ],
    "presurgical": [
        ("A", "new_patient_consult"),
        ("G", "mri_report"),
        ("H", "eeg_report"),
        ("D", "emu_admission"),
        ("L", "inpatient_progress"),
        ("L", "inpatient_progress"),
        ("H", "eeg_report"),
        ("I", "neuropsych"),
        ("F", "prc_summary"),
        ("C", "progress_note"),
    ],
    "post_surgical": [
        ("D", "emu_admission"),
        ("J", "discharge_summary"),
        ("C", "progress_note"),
        ("G", "mri_report"),
        ("H", "eeg_report"),
        ("C", "progress_note"),
        ("B", "telephone_fuv"),
    ],
    "autoimmune": [
        ("A", "new_patient_consult"),
        ("G", "mri_report"),
        ("H", "eeg_report"),
        ("E", "ed_note"),
        ("C", "progress_note"),
        ("C", "progress_note"),
        ("B", "telephone_fuv"),
    ],
    "developmental": [
        ("A", "new_patient_consult"),
        ("C", "progress_note"),
        ("H", "eeg_report"),
        ("I", "neuropsych"),
        ("C", "progress_note"),
        ("B", "telephone_fuv"),
        ("C", "progress_note"),
    ],
    "status_epilepticus": [
        ("E", "ed_note"),
        ("L", "inpatient_progress"),
        ("L", "inpatient_progress"),
        ("J", "discharge_summary"),
        ("C", "progress_note"),
        ("B", "telephone_fuv"),
    ],
}


# ─── Care setting + provider persona sampling ────────────────────────────

CARE_SETTING_PRIOR = {
    "academic_medical_center": 0.55,
    "community_neurology": 0.25,
    "emu": 0.10,  # forced by note_type
    "ed": 0.05,   # forced by note_type
    "va": 0.05,
}

PROVIDER_BY_NOTE_TYPE = {
    "new_patient_consult": ["attending_neurologist", "neurosurgeon"],
    "progress_note": ["attending_neurologist", "fellow"],
    "telephone_fuv": ["attending_neurologist"],
    "emu_admission": ["attending_neurologist", "fellow"],
    "ed_note": ["ed_physician"],
    "prc_summary": ["attending_neurologist"],
    "mri_report": ["radiologist"],
    "eeg_report": ["attending_neurologist"],
    "neuropsych": ["psychologist"],
    "discharge_summary": ["attending_neurologist", "neurosurgeon"],
    "triage_call": ["app"],
    "inpatient_progress": ["attending_neurologist", "fellow"],
}

SPECIALTY_BY_NOTE_TYPE = {
    "new_patient_consult": "neurology",
    "progress_note": "neurology",
    "telephone_fuv": "neurology",
    "emu_admission": "neurology",
    "ed_note": "ed",
    "prc_summary": "neurology",
    "mri_report": "radiology",
    "eeg_report": "neurophysiology",
    "neuropsych": "psychology",
    "discharge_summary": "neurology",
    "triage_call": "neurology",
    "inpatient_progress": "neurology",
}


def _pick_care_setting(rng: random.Random, note_type: str) -> str:
    """Force setting for note types that only occur in specific settings."""
    if note_type == "ed_note":
        return "ed"
    if note_type in ("emu_admission", "inpatient_progress"):
        return "emu" if note_type == "emu_admission" or rng.random() < 0.70 else "academic_medical_center"
    if note_type in ("prc_summary", "neuropsych"):
        return "academic_medical_center"
    # Otherwise sample from prior
    options = ["academic_medical_center", "community_neurology", "va"]
    weights = [0.60, 0.30, 0.10]
    return rng.choices(options, weights=weights, k=1)[0]


def _pick_provider(rng: random.Random, note_type: str) -> str:
    return rng.choice(PROVIDER_BY_NOTE_TYPE[note_type])


# ─── Timeline construction ───────────────────────────────────────────────

def _sample_dob(rng: random.Random, age_at_onset: int) -> date:
    """Fictional DOB. Ensures visit dates are after age of onset + some time."""
    # Adult age at index visit: onset + rng(1..30) years
    years_since_onset = rng.randint(1, 30)
    age_now = age_at_onset + years_since_onset
    today = date(2026, 9, 30)
    dob_year = today.year - age_now
    dob_month = rng.randint(1, 12)
    dob_day = rng.randint(1, 28)
    return date(dob_year, dob_month, dob_day)


def _make_visit_dates(rng: random.Random, n_visits: int) -> list[date]:
    """Space visits over a plausible 1-4 year window."""
    end = date(2026, 9, 30)
    total_days = rng.randint(365, 365 * 4)
    start = end - timedelta(days=total_days)
    intervals = sorted(rng.sample(range(total_days), min(n_visits, total_days)))
    return [start + timedelta(days=int(d)) for d in intervals]


def _visit_id(patient_id: str, visit_number: int) -> str:
    return f"{patient_id}_V{visit_number:02d}"


def _plan_patient_timeline(
    rng: random.Random,
    plan: dict,
    dob: date,
    n_visits: int,
) -> list[dict]:
    phenotype = _classify_phenotype(plan, rng)

    # Diversification: some presurgical bumped to post_surgical (already completed)
    # and some drug_resistant bumped to status_epilepticus (recent SE episode)
    if phenotype == "presurgical" and rng.random() < 0.30:
        phenotype = "post_surgical"
    elif phenotype == "drug_resistant" and rng.random() < 0.15:
        phenotype = "status_epilepticus"

    sequence = PHENOTYPE_TO_NOTE_SEQUENCE[phenotype]
    # Take the first n_visits from the phenotype sequence, cycling if needed
    picks = []
    for i in range(n_visits):
        template_id, note_type = sequence[i % len(sequence)]
        picks.append((template_id, note_type))

    dates = _make_visit_dates(rng, n_visits)

    rows = []
    for i, ((template_id, note_type), vdate) in enumerate(zip(picks, dates), start=1):
        care_setting = _pick_care_setting(rng, note_type)
        provider = _pick_provider(rng, note_type)
        specialty = SPECIALTY_BY_NOTE_TYPE[note_type]
        age_at_visit = (vdate - dob).days / 365.25

        rows.append({
            "patient_id": plan["patient_id"],
            "visit_id": _visit_id(plan["patient_id"], i),
            "visit_number": i,
            "visit_date": vdate.isoformat(),
            "age_at_visit": round(age_at_visit, 1),
            "note_type": note_type,
            "note_template": template_id,
            "care_setting": care_setting,
            "provider_persona": provider,
            "specialty": specialty,
            "phenotype_profile": phenotype,
        })

    return rows


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patients-dir", required=True,
                    help="Directory of P######.json semantic plans")
    ap.add_argument("--out-manifest", required=True,
                    help="Path for encounter_manifest.csv output")
    ap.add_argument("--n-patients", type=int, default=100,
                    help="Cap number of patients (uses first N by patient_id)")
    ap.add_argument("--min-visits", type=int, default=2)
    ap.add_argument("--max-visits", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--patients-out-dir", default=None,
                    help="If set, copy per-patient DOB/phenotype JSON here")
    args = ap.parse_args()

    patients_dir = Path(args.patients_dir).resolve()
    out_manifest = Path(args.out_manifest).resolve()
    out_manifest.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)

    plan_paths = sorted(p for p in patients_dir.glob("P*.json") if "_case" not in p.name and "_target" not in p.name)
    if args.n_patients > 0:
        plan_paths = plan_paths[: args.n_patients]

    all_rows = []
    phenotype_counts: dict[str, int] = {}
    note_type_counts: dict[str, int] = {}
    patient_meta = {}

    for plan_path in plan_paths:
        plan = json.loads(plan_path.read_text())
        # Extract age_at_onset from plan for DOB sampling
        reqs = {r["field"]: r["value"] for r in plan.get("required_assertions", [])}
        aoo = reqs.get("AGE_AT_ONSET_YEARS", 30)
        dob = _sample_dob(rng, int(aoo) if isinstance(aoo, (int, float, str)) and str(aoo).isdigit() else 30)

        n_visits = rng.randint(args.min_visits, args.max_visits)
        rows = _plan_patient_timeline(rng, plan, dob, n_visits)

        # Sex sampling for realism (50/50 for now)
        sex = rng.choice(["M", "F"])

        for r in rows:
            r["patient_dob"] = dob.isoformat()
            r["patient_sex"] = sex
            all_rows.append(r)
            phenotype_counts[r["phenotype_profile"]] = phenotype_counts.get(r["phenotype_profile"], 0) + 1
            note_type_counts[r["note_type"]] = note_type_counts.get(r["note_type"], 0) + 1

        patient_meta[plan["patient_id"]] = {
            "patient_id": plan["patient_id"],
            "patient_dob": dob.isoformat(),
            "patient_sex": sex,
            "phenotype_profile": rows[0]["phenotype_profile"],
            "n_visits": n_visits,
        }

    # Write encounter manifest
    fieldnames = [
        "patient_id", "visit_id", "visit_number", "visit_date", "age_at_visit",
        "note_type", "note_template", "care_setting", "provider_persona", "specialty",
        "phenotype_profile", "patient_dob", "patient_sex",
    ]
    with out_manifest.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)

    # Write per-patient meta if requested
    if args.patients_out_dir:
        patients_out = Path(args.patients_out_dir).resolve()
        patients_out.mkdir(parents=True, exist_ok=True)
        for pid, meta in patient_meta.items():
            (patients_out / f"{pid}_meta.json").write_text(json.dumps(meta, indent=2))

    print(f"[synth-v3 planner]")
    print(f"  patients:        {len(plan_paths)}")
    print(f"  total visits:    {len(all_rows)}")
    print(f"  manifest:        {out_manifest}")
    print()
    print("  Phenotype distribution:")
    for k, v in sorted(phenotype_counts.items(), key=lambda x: -x[1]):
        pct = 100 * v / max(len(all_rows), 1)
        print(f"    {k:22s} {v:4d} ({pct:.1f}%)")
    print()
    print("  Note-type distribution:")
    for k, v in sorted(note_type_counts.items(), key=lambda x: -x[1]):
        pct = 100 * v / max(len(all_rows), 1)
        print(f"    {k:22s} {v:4d} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
