#!/usr/bin/env python3
"""Extended synthetic patient plans: EEG findings, semiology, focal onset features, rescue drugs, surgery.

The v1-v3 plans carry no reference for these, so LEO's specialist could not be scored on them.  This script
samples ordinary patients with `synth_patient_sampler` and adds five plan fields.  Each is an assertion in the
plan (so the note generator must write it and the value is the reference by construction):

    EEG_STUDY          {study_type, background, ied_lobe, ied_laterality, ictal_onset_lobe, ictal_onset_laterality}
    SEMIOLOGY          {aura, motor_features:[...], awareness}
    FOCAL_ONSET        {motor: <ILAE 2017 focal motor onset> | None, nonmotor: <focal non-motor onset> | None}
    RESCUE_MEDS        [{generic_name, route}]
    SURGERY_HISTORY    [{procedure, side, year}]

Values are drawn so they agree with the patient's epilepsy type, seizure type and MRI finding.  The distribution
is a coverage fixture (so each value has examples), not prevalence.

    venv-medcat/bin/python scripts/synth_extended_plan.py --n 30 --start-index 5000 --seed 7 \
        --output-dir data/episynth_corpus/v4_ext/patients

Then plan the visits with scripts/synth_v3_encounter_planner.py and render with
scripts/generate_synth_v3_corpus.py (the generator adds the directive for these fields when it sees them).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import synth_patient_sampler as sps  # noqa: E402

EXTENDED_FIELDS = ("EEG_STUDY", "SEMIOLOGY", "FOCAL_ONSET", "RESCUE_MEDS", "SURGERY_HISTORY")

STUDY_TYPES = [("routine_eeg", 0.50), ("prolonged_eeg", 0.15), ("ambulatory_eeg", 0.10), ("video_eeg_monitoring", 0.25)]
LOBES = [("temporal", 0.55), ("frontal", 0.25), ("parietal", 0.10), ("occipital", 0.10)]
SIDES = [("left", 0.45), ("right", 0.45), ("bilateral", 0.10)]
AURAS = ["epigastric rising sensation", "deja vu", "fear", "visual phenomena", "olfactory (burning smell)", "tingling of the hand"]
MOTOR_FOCAL = ["automatisms", "clonic jerking", "tonic posturing", "versive head turning", "epileptic spasms", "hyperkinetic movements"]
NONMOTOR_FOCAL = ["behavior arrest", "autonomic", "cognitive", "emotional", "sensory"]
RESCUE = [("diazepam", "rectal"), ("midazolam", "intranasal"), ("lorazepam", "sublingual"), ("clonazepam", "orally disintegrating")]
SURGERY = ["anterior temporal lobectomy", "laser interstitial thermal therapy", "lesionectomy",
           "vagus nerve stimulator implantation", "responsive neurostimulation implantation"]


def _wc(rng: random.Random, options: list[tuple[str, float]]) -> str:
    return sps._weighted_choice(rng, options)


def _eeg(rng: random.Random, pat: dict) -> dict:
    focal = pat["ep_type"] in ("focal", "combined_generalized_and_focal")
    study = _wc(rng, STUDY_TYPES)
    out = {"study_type": study}
    if focal:
        lobe = "temporal" if pat["mri_finding"] == "hippocampal_sclerosis" else _wc(rng, LOBES)
        side = _wc(rng, SIDES[:2])
        out["background"] = rng.choice(["normal", "focal_slowing", "mild_diffuse_slowing"])
        out["ied_lobe"], out["ied_laterality"] = (lobe, side) if rng.random() < 0.80 else (None, None)
        if study == "video_eeg_monitoring" and out["ied_lobe"]:
            out["ictal_onset_lobe"], out["ictal_onset_laterality"] = lobe, side
    elif pat["ep_type"] == "generalized":
        out["background"] = rng.choice(["normal", "normal", "mild_diffuse_slowing"])
        out["ied_lobe"], out["ied_laterality"] = ("generalized", "bilateral") if rng.random() < 0.75 else (None, None)
    else:
        out["background"] = rng.choice(["normal", "mild_diffuse_slowing"])
        out["ied_lobe"] = out["ied_laterality"] = None
    for k in ("ictal_onset_lobe", "ictal_onset_laterality"):
        out.setdefault(k, None)
    return out


def _semiology_and_onset(rng: random.Random, pat: dict) -> tuple[dict | None, dict | None]:
    szt = pat["sz_type"]
    if szt.startswith("focal"):
        aura = rng.choice(AURAS) if rng.random() < 0.55 and "aura" not in pat.get("denied_findings", []) else None
        if szt == "focal_aware":
            awareness = "preserved"
        elif szt == "focal_impaired_awareness":
            awareness = "impaired"
        else:
            awareness = "impaired"
        # automatisms imply impaired awareness, so a focal aware seizure draws from the other features
        pool = [m for m in MOTOR_FOCAL if m != "automatisms"] if szt == "focal_aware" else MOTOR_FOCAL
        motor = rng.sample(pool, k=rng.choice([1, 1, 2]))
        if szt == "focal_to_bilateral_tonic_clonic":
            motor = motor[:1] + ["evolution to bilateral tonic-clonic"]
        onset = {"motor": None, "nonmotor": None}
        if rng.random() < 0.6:
            onset["motor"] = rng.choice(pool)
        if onset["motor"] is None or rng.random() < 0.4:
            onset["nonmotor"] = rng.choice(NONMOTOR_FOCAL)
        # keep the narrative semiology consistent with the stated onset feature
        if onset["motor"] and onset["motor"] not in motor:
            motor = [onset["motor"]] + motor[:1]
        return {"aura": aura, "motor_features": motor, "awareness": awareness}, onset
    if szt in ("generalized_tonic_clonic", "unknown_onset_tonic_clonic"):
        return {"aura": None, "motor_features": ["tonic stiffening followed by clonic jerking"], "awareness": "impaired"}, None
    if szt == "absence_typical":
        return {"aura": None, "motor_features": ["brief staring spells with eyelid fluttering"], "awareness": "impaired"}, None
    if szt == "myoclonic":
        return {"aura": None, "motor_features": ["brief shock-like jerks of the arms on waking"], "awareness": "preserved"}, None
    return None, None


def _rescue(rng: random.Random, pat: dict) -> list[dict]:
    p = 0.65 if pat["dre_status"] == "drug_resistant" else 0.35
    if rng.random() >= p:
        return []
    # one rescue drug; not one of the maintenance drugs
    current = {a["generic_name"] for a in pat["current_asms"]}
    opts = [r for r in RESCUE if r[0] not in current] or RESCUE
    name, route = rng.choice(opts)
    return [{"generic_name": name, "route": route}]


def _surgery(rng: random.Random, pat: dict) -> list[dict]:
    # a patient can be drug responsive after surgery, so a few of those get a past procedure too
    if rng.random() >= (0.80 if pat["dre_status"] == "drug_resistant" else 0.12):
        return []
    proc = rng.choice(SURGERY)
    if proc == "anterior temporal lobectomy" and pat["mri_finding"] not in ("hippocampal_sclerosis", "tumor", "focal_cortical_dysplasia"):
        proc = rng.choice(SURGERY[1:])
    side = rng.choice(["left", "right"]) if "stimul" not in proc else None
    return [{"procedure": proc, "side": side, "year": rng.randint(2012, 2024)}]


def extend(pat: dict, plan: dict, rng: random.Random) -> dict:
    reqs, n = plan["required_assertions"], len(plan["required_assertions"])

    def push(field, value):
        nonlocal n
        n += 1
        eid = f"E{n:03d}"
        reqs.append({"event_id": eid, "field": field, "value": value})
        plan["allowed_source_event_ids"].append(eid)

    push("EEG_STUDY", _eeg(rng, pat))
    sem, onset = _semiology_and_onset(rng, pat)
    if sem:
        push("SEMIOLOGY", sem)
    if onset:
        push("FOCAL_ONSET", onset)
    r = _rescue(rng, pat)
    if r:
        push("RESCUE_MEDS", r)
    s = _surgery(rng, pat)
    if s:
        push("SURGERY_HISTORY", s)
    plan["_meta"]["sampler_version"] = "v1.0+ext1"
    plan["_meta"]["extended_fields"] = list(EXTENDED_FIELDS)
    return plan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--start-index", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--rare-oversample", type=float, default=0.10)
    ap.add_argument("--output-dir", default="data/episynth_corpus/v4_ext/patients")
    args = ap.parse_args()
    out = (REPO / args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    counts = {k: 0 for k in EXTENDED_FIELDS}
    for i in range(args.n):
        pat = sps._sample_patient(rng, args.start_index + i, rng.random() < args.rare_oversample)
        plan = extend(pat, sps._to_semantic_plan(pat), rng)
        for r in plan["required_assertions"]:
            if r["field"] in counts:
                counts[r["field"]] += 1
        (out / f"{pat['patient_id']}.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{args.n} extended plans in {out}")
    print("patients with each extended field:", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
