"""Convert Synthea output (text notes + CSV structured export) into v0.2.1 EpilepsyPhenotype
gold JSON + per-encounter text corpus.

Filters to patients with epilepsy diagnosis. Emits a per-doc pair (note.txt + gold.json).

Usage:
    venv-medcat/bin/python scripts/synthea_to_v021.py \
        --synthea-output references/synthea/output_epi \
        --out-dir data/eval_corpora/synthea_epilepsy \
        [--limit 200]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Synthea SNOMED codes for epilepsy phenotype
EPILEPSY_SNOMED = {"84757009", "128613002"}  # Epilepsy, Seizure disorder
SEIZURE_SNOMED = {"91175000", "84392008", "313307000"}  # Seizure family
AED_RXNORM = {
    "carbamazepine": "197521", "phenytoin": "203029", "valproate": "203134",
    "lamotrigine": "197744", "levetiracetam": "310241", "topiramate": "199530",
    "phenobarbital": "197380", "diazepam": "197599", "clonazepam": "197527",
    "oxcarbazepine": "310211",
}


def _make_evidence(value, evidence_text=None, certainty="definite", temporal="current",
                   source_doc_id=None, source_doc_type="progress_note"):
    return {
        "value": value,
        "certainty": certainty,
        "temporal_status": temporal,
        "evidence_text": evidence_text,
        "source_doc_id": source_doc_id,
        "source_doc_type": source_doc_type,
        "source_date": "2026-09-25",
        "char_start": None,
        "char_end": None,
    }


def _not_documented(source_doc_id=None):
    return _make_evidence(None, certainty="not_documented", temporal="unspecified",
                          source_doc_id=source_doc_id)


def _load_from_fhir(fhir_dir: Path):
    """Parse FHIR bundles for conditions + medications keyed by patient UUID.

    Returns (conditions, medications, uuid_by_stem) where the last dict maps
    the FHIR filename stem (e.g. 'Abe604_Rogahn59_f75caf9c-...') to the
    patient's FHIR UUID — used to correlate with text_encounters filenames
    (Synthea per-encounter notes are named with the same stem + encounter idx).
    """
    conditions: dict[str, list[dict]] = {}
    medications: dict[str, list[dict]] = {}
    uuid_by_stem: dict[str, str] = {}
    for bp in sorted(fhir_dir.glob("*.json")):
        try:
            bundle = json.loads(bp.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        pid = None
        for e in bundle.get("entry", []):
            r = e.get("resource", {})
            if r.get("resourceType") == "Patient":
                pid = r.get("id")
                if pid:
                    uuid_by_stem[bp.stem] = pid
                break
        if not pid:
            continue
        for e in bundle.get("entry", []):
            r = e.get("resource", {})
            t = r.get("resourceType")
            if t == "Condition":
                c = (r.get("code", {}).get("coding", []) or [{}])[0]
                conditions.setdefault(pid, []).append({
                    "CODE": c.get("code", ""),
                    "DESCRIPTION": c.get("display", ""),
                    "START": (r.get("onsetDateTime", "") or "")[:10],
                    "STOP": (r.get("abatementDateTime", "") or "")[:10],
                })
            elif t in ("MedicationRequest", "MedicationStatement"):
                m = r.get("medicationCodeableConcept", {}) or {}
                c = (m.get("coding", []) or [{}])[0]
                period = r.get("effectivePeriod", {}) or {}
                medications.setdefault(pid, []).append({
                    "CODE": c.get("code", ""),
                    "DESCRIPTION": c.get("display", "") or m.get("text", ""),
                    "START": ((r.get("authoredOn", "") or period.get("start", "")) or "")[:10],
                    "STOP": (period.get("end", "") or "")[:10],
                })
    return conditions, medications, uuid_by_stem


def _patient_has_epilepsy(conditions: list[dict]) -> bool:
    for c in conditions:
        code = c.get("CODE", "")
        desc = (c.get("DESCRIPTION", "") or "").lower()
        if code in EPILEPSY_SNOMED:
            return True
        if "epilep" in desc:
            return True
    return False


def _build_gold(pid: str, conditions: list[dict], meds: list[dict],
                doc_id: str, note_text: str) -> dict:
    """Derive v0.2.1-shape EpilepsyPhenotype from Synthea structured data."""
    epi_types = [c for c in conditions
                 if c.get("CODE", "") in EPILEPSY_SNOMED
                 or "epilep" in (c.get("DESCRIPTION", "") or "").lower()]

    # Predominant seizure type — Synthea epilepsy module doesn't split types
    # finely; default to generalized_tonic_clonic if seizure detected in text.
    predom = None
    if any(kw in note_text.lower() for kw in ("tonic-clonic", "grand mal", "convulsion")):
        predom = "generalized_tonic_clonic"
    elif "focal" in note_text.lower():
        predom = "focal_impaired_awareness"
    elif "seizure" in note_text.lower():
        predom = "unknown_onset_tonic_clonic"

    # Current AEDs — meds with STOP field empty (active)
    current_asms = []
    for m in meds:
        desc = (m.get("DESCRIPTION", "") or "").lower()
        stop = m.get("STOP", "").strip()
        for generic in AED_RXNORM:
            if generic in desc and not stop:
                current_asms.append({
                    "generic_name": generic,
                    "brand_name": None,
                    "dose_text": None,
                    "frequency_text": None,
                    "route": None,
                    "rxnorm_cui": AED_RXNORM[generic],
                    "start_date": m.get("START"),
                    "stop_date": None,
                    "certainty": "definite",
                    "temporal_status": "current",
                    "evidence_text": m.get("DESCRIPTION"),
                    "source_doc_id": doc_id,
                })
                break

    # Prior AEDs — meds with STOP field populated
    prior_asms = []
    for m in meds:
        desc = (m.get("DESCRIPTION", "") or "").lower()
        stop = m.get("STOP", "").strip()
        for generic in AED_RXNORM:
            if generic in desc and stop:
                prior_asms.append({
                    "generic_name": generic,
                    "brand_name": None,
                    "dose_text": None,
                    "frequency_text": None,
                    "route": None,
                    "rxnorm_cui": AED_RXNORM[generic],
                    "start_date": m.get("START"),
                    "stop_date": stop,
                    "certainty": "definite",
                    "temporal_status": "past",
                    "evidence_text": m.get("DESCRIPTION"),
                    "source_doc_id": doc_id,
                })
                break

    return {
        "schema_version": "v0.2.1",
        "document": {
            "doc_id": doc_id,
            "doc_type": "progress_note",
            "doc_date": "2026-09-25",
            "patient_id": pid[:8],
            "icd10cm_codes": [],
            "snomed_ct_codes": [c["CODE"] for c in epi_types],
        },
        "clinical_seizure": {
            "epilepsy_type": _make_evidence("unknown", source_doc_id=doc_id) if epi_types else _not_documented(doc_id),
            "predominant_seizure_type": _make_evidence(predom, source_doc_id=doc_id) if predom else _not_documented(doc_id),
            "other_seizure_types": [],
            "awareness": _not_documented(doc_id),
            "focal_motor_onset": _not_documented(doc_id),
            "focal_nonmotor_onset": _not_documented(doc_id),
            "seizure_frequency": _not_documented(doc_id),
            "other_seizure_frequencies": [],
            "age_at_onset_years": _not_documented(doc_id),
            "etiology_category": _make_evidence("unknown", source_doc_id=doc_id) if epi_types else _not_documented(doc_id),
            "etiology_details_text": _not_documented(doc_id),
            "etiology_specifics": _not_documented(doc_id),
            "status_epilepticus_history": _not_documented(doc_id),
            "semiology_text": _not_documented(doc_id),
        },
        "medication": {
            "current_asms": current_asms,
            "prior_asms": prior_asms,
            "failed_asms": [],
            "drug_resistance_status": _not_documented(doc_id),
            "adverse_effects_text": _not_documented(doc_id),
            "non_drug_therapies": [],
            "surgery_history": [],
        },
        "clinical_localization": {
            "primary_claim": _not_documented(doc_id),
            "alternative_claims": [],
            "localization_source": _not_documented(doc_id),
        },
        "eeg": {
            "study_type": _not_documented(doc_id),
            "background": _not_documented(doc_id),
            "ied_present": _not_documented(doc_id),
            "ied_findings": [],
            "seizures_captured": _not_documented(doc_id),
            "seizures_captured_count": _not_documented(doc_id),
            "ictal_onset_lobe": _not_documented(doc_id),
            "ictal_onset_laterality": _not_documented(doc_id),
        },
        "mri": {
            "field_strength_tesla": _not_documented(doc_id),
            "findings": _not_documented(doc_id),
            "overall_normal": _not_documented(doc_id),
            "hippocampal_sclerosis": _not_documented(doc_id),
            "focal_cortical_dysplasia": _not_documented(doc_id),
            "lesion_lobe": _not_documented(doc_id),
            "lesion_laterality": _not_documented(doc_id),
        },
        "integrated": {
            "clinical_localization": _not_documented(doc_id),
            "eeg_localization": _not_documented(doc_id),
            "mri_localization": _not_documented(doc_id),
            "concordance": _make_evidence("not_assessed", source_doc_id=doc_id),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthea-output", default="references/synthea/output_epi",
                    help="Synthea output directory (has csv/ and notes/ subdirs)")
    ap.add_argument("--out-dir", default="data/eval_corpora/synthea_epilepsy")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap number of epilepsy patients to emit")
    args = ap.parse_args()

    synth = REPO_ROOT / args.synthea_output
    out_dir = REPO_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "documents").mkdir(exist_ok=True)
    (out_dir / "gold_v0_2_1").mkdir(exist_ok=True)

    fhir_dir = synth / "fhir"
    notes_dir = synth / "text_encounters"
    if not fhir_dir.exists() or not notes_dir.exists():
        print(f"[synthea-conv] ERROR: expected {fhir_dir} and {notes_dir}", file=sys.stderr)
        return 2

    print(f"[synthea-conv] Loading FHIR bundles from {fhir_dir}...")
    conditions_by_pid, meds_by_pid, uuid_by_stem = _load_from_fhir(fhir_dir)
    stem_by_uuid = {v: k for k, v in uuid_by_stem.items()}

    epilepsy_pids = {pid for pid, conds in conditions_by_pid.items()
                    if _patient_has_epilepsy(conds)}
    print(f"[synthea-conv] {len(epilepsy_pids)} epilepsy patients / {len(conditions_by_pid)} total")

    if args.limit:
        epilepsy_pids = set(sorted(epilepsy_pids)[:args.limit])

    manifest_rows = []
    n_docs = 0
    for pid in sorted(epilepsy_pids):
        stem = stem_by_uuid.get(pid)
        if not stem:
            continue
        # Synthea per-encounter file naming: {stem}{encounter_idx}.txt
        # where {stem} is FirstName_LastName_UUID
        for note_path in sorted(notes_dir.glob(f"{stem}*.txt")):
            note_text = note_path.read_text(encoding="utf-8", errors="replace")
            if not note_text.strip():
                continue
            # Keep only notes that reference epilepsy/seizure
            if not re.search(r"epilep|seizur|convuls|spell", note_text, re.IGNORECASE):
                continue
            doc_id = note_path.stem
            # Save note text
            (out_dir / "documents" / f"{doc_id}.txt").write_text(note_text)
            # Derive gold
            gold = _build_gold(pid, conditions_by_pid.get(pid, []),
                               meds_by_pid.get(pid, []), doc_id, note_text)
            (out_dir / "gold_v0_2_1" / f"{doc_id}.json").write_text(
                json.dumps(gold, indent=2))
            manifest_rows.append({
                "id": doc_id,
                "patient_id": pid[:8],
                "doc_type": "progress_note",
                "char_count": len(note_text),
                "n_conditions": len(conditions_by_pid.get(pid, [])),
                "n_medications": len(meds_by_pid.get(pid, [])),
            })
            n_docs += 1
            if args.limit and n_docs >= args.limit:
                break
        if args.limit and n_docs >= args.limit:
            break

    with (out_dir / "manifest.csv").open("w") as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifest_rows[0].keys())
                           if manifest_rows else ["id"])
        w.writeheader()
        w.writerows(manifest_rows)

    print(f"[synthea-conv] Wrote {n_docs} epilepsy-relevant notes + gold to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
