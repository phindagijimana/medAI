#!/usr/bin/env python3
"""Generate the synth-v3 US-realistic epilepsy note corpus.

Consumes an encounter_manifest.csv (from synth_v3_encounter_planner.py) and
per-patient semantic plans (from synth_patient_sampler.py). For each visit
row, loads the matching prompt template (prompts/synth_v3_templates/
template_{A-L}_*.txt), injects the semantic plan + encounter metadata, and
calls the OpenAI Responses API to produce a note. Writes the note to
`documents/{visit_id}.txt` and emits the universal corpus manifest v1.0.

The script is idempotent — re-runs skip visits whose output already exists,
so partial batches can resume without losing tokens.

Template ↔ note-type routing:
    A → new_patient_consult
    B → telephone_fuv
    C → progress_note
    D → emu_admission
    E → ed_note
    F → prc_summary
    G → mri_report
    H → eeg_report
    I → neuropsych
    J → discharge_summary
    K → triage_call
    L → inpatient_progress

Usage (smoke test, 10 docs, ~$1):
    set -a; source .env; set +a
    python scripts/generate_synth_v3_corpus.py \\
        --patients-dir data/episynth_corpus/v3/patients \\
        --encounter-manifest data/episynth_corpus/v3/encounter_manifest.csv \\
        --out-dir data/eval_corpora/synth_v3 \\
        --model gpt-5.6-sol \\
        --limit 10

Full run (~500 docs, ~$40-60):
    python scripts/generate_synth_v3_corpus.py \\
        --patients-dir data/episynth_corpus/v3/patients \\
        --encounter-manifest data/episynth_corpus/v3/encounter_manifest.csv \\
        --out-dir data/eval_corpora/synth_v3 \\
        --model gpt-5.6-sol
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO / "prompts" / "synth_v3_templates"
DEFAULT_MODEL = "gpt-5.6-sol"

TEMPLATE_TO_NOTE_TYPE = {
    "A": "new_patient_consult",
    "B": "telephone_fuv",
    "C": "progress_note",
    "D": "emu_admission",
    "E": "ed_note",
    "F": "prc_summary",
    "G": "mri_report",
    "H": "eeg_report",
    "I": "neuropsych",
    "J": "discharge_summary",
    "K": "triage_call",
    "L": "inpatient_progress",
}

TEMPLATE_FILE = {
    "A": "template_A_new_patient_consult.txt",
    "B": "template_B_telephone_fuv.txt",
    "C": "template_C_in_person_fuv.txt",
    "D": "template_D_emu_admission.txt",
    "E": "template_E_ed_note.txt",
    "F": "template_F_prc_summary.txt",
    "G": "template_G_mri_report.txt",
    "H": "template_H_eeg_report.txt",
    "I": "template_I_neuropsych.txt",
    "J": "template_J_discharge_summary.txt",
    "K": "template_K_triage_call.txt",
    "L": "template_L_inpatient_progress.txt",
}


# ─── Prompt assembly ─────────────────────────────────────────────────────

_TEMPLATE_CACHE: dict[str, str] = {}


def _load_template(template_id: str) -> str:
    if template_id not in _TEMPLATE_CACHE:
        path = TEMPLATES_DIR / TEMPLATE_FILE[template_id]
        _TEMPLATE_CACHE[template_id] = path.read_text(encoding="utf-8")
    return _TEMPLATE_CACHE[template_id]


def _build_encounter_metadata(row: dict, patient_context: dict) -> dict:
    """Encounter metadata injected into the prompt alongside the semantic plan."""
    meta = {
        "visit_id": row["visit_id"],
        "visit_number": int(row["visit_number"]),
        "visit_date": row["visit_date"],
        "age_at_visit_years": float(row["age_at_visit"]),
        "note_type": row["note_type"],
        "care_setting": row["care_setting"],
        "provider_persona": row["provider_persona"],
        "specialty": row["specialty"],
        "phenotype_profile": row["phenotype_profile"],
        "patient_sex": row["patient_sex"],
    }
    # Add prior visit context if this isn't the first visit
    prior = patient_context.get(row["patient_id"], [])
    if prior:
        meta["prior_visit_summary"] = (
            f"Patient was last seen on {prior[-1]['visit_date']} for a "
            f"{prior[-1]['note_type'].replace('_', ' ')} in the "
            f"{prior[-1]['care_setting'].replace('_', ' ')} setting."
        )
        meta["interval_events"] = []  # placeholder — GPT fills based on plan
    # Common template-specific hints
    if row["note_type"] == "telephone_fuv":
        meta["is_video"] = True
        meta["time_spent_min"] = "xx"
    if row["note_type"] == "emu_admission":
        meta["emu_indication"] = (
            "presurgical" if row["phenotype_profile"] == "presurgical"
            else "diagnostic"
        )
        meta["planned_duration_days"] = 5
    if row["note_type"] == "ed_note":
        meta["ed_chief_complaint"] = (
            "status epilepticus" if row["phenotype_profile"] == "status_epilepticus"
            else "breakthrough seizure"
        )
        meta["neuro_consulted"] = True
    if row["note_type"] == "inpatient_progress":
        meta["hospital_day_number"] = int(row["visit_number"])
        meta["is_emu"] = row["care_setting"] == "emu"
    return meta


def _assemble_prompt(row: dict, plan: dict, patient_context: dict) -> str:
    template_id = row["note_template"]
    template = _load_template(template_id)
    plan_json = json.dumps(plan, indent=2, ensure_ascii=False)
    metadata_json = json.dumps(
        _build_encounter_metadata(row, patient_context),
        indent=2, ensure_ascii=False,
    )
    prompt = template.replace("{SEMANTIC_PLAN_JSON}", plan_json)
    prompt = prompt.replace("{ENCOUNTER_METADATA_JSON}", metadata_json)
    return prompt


# ─── Manifest emission ───────────────────────────────────────────────────

MANIFEST_FIELDS = [
    "visit_id", "patient_id", "corpus", "corpus_version",
    "patient_dob", "patient_sex", "patient_race", "patient_ethnicity", "patient_zip3",
    "visit_date", "visit_number", "age_at_visit",
    "note_type", "note_template", "care_setting", "provider_persona", "specialty",
    "note_char_count", "note_word_count", "note_section_count", "note_language",
    "generator_model", "generator_seed",
    "generator_tokens_in", "generator_tokens_out", "generator_cost_usd",
    "phenotype_profile",
    "note_path", "gold_path", "semantic_plan_path", "raw_source_path",
    "gold_source", "gold_conformant", "silver_labeler", "review_status",
    "epilepsy_relevance_score",
    "created_at", "created_by", "ingest_batch", "notes",
]


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _word_count(text: str) -> int:
    return len(text.split())


def _section_count(text: str) -> int:
    """Rough count of headers (Title Case colon or ALL CAPS colon)."""
    return len(re.findall(r"^\s*[A-Z][A-Za-z /]{2,40}:\s*$", text, re.M))


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patients-dir", required=True,
                    help="Directory of P######.json semantic plans")
    ap.add_argument("--encounter-manifest", required=True,
                    help="CSV emitted by synth_v3_encounter_planner.py")
    ap.add_argument("--out-dir", required=True,
                    help="Output dir (documents/ + manifest.csv will be written here)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--reasoning-effort", default="medium",
                    help="OpenAI Responses reasoning effort")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap on number of visits to render (for smoke tests)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print prompt for visit 1 and exit (no API call)")
    args = ap.parse_args()

    patients_dir = Path(args.patients_dir).resolve()
    enc_manifest_path = Path(args.encounter_manifest).resolve()
    out_dir = Path(args.out_dir).resolve()
    docs_dir = out_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Load encounter rows
    with enc_manifest_path.open() as fh:
        enc_rows = list(csv.DictReader(fh))
    if args.limit:
        enc_rows = enc_rows[: args.limit]

    # Preload plans
    plans: dict[str, dict] = {}
    for pid in {r["patient_id"] for r in enc_rows}:
        plan_path = patients_dir / f"{pid}.json"
        if plan_path.exists():
            plans[pid] = json.loads(plan_path.read_text())

    # Build prior-visit context (each patient's history)
    patient_context: dict[str, list[dict]] = defaultdict(list)

    # Dry-run: print prompt for visit 1 and exit
    if args.dry_run:
        row = enc_rows[0]
        plan = plans.get(row["patient_id"])
        if not plan:
            raise SystemExit(f"No plan for {row['patient_id']}")
        print(_assemble_prompt(row, plan, patient_context))
        return

    # Require OpenAI
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not set. `set -a; source .env; set +a` first.")
    try:
        from openai import OpenAI
    except ImportError as e:
        raise SystemExit(f"openai not installed: {e}")
    client = OpenAI()

    # Load existing manifest for idempotency
    manifest_path = out_dir / "manifest.csv"
    manifest_rows: list[dict] = []
    if manifest_path.exists():
        with manifest_path.open() as fh:
            manifest_rows = list(csv.DictReader(fh))
    existing_visit_ids = {r["visit_id"] for r in manifest_rows}

    ingest_batch = f"synth_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    n_new = n_skip = n_err = 0
    t0 = time.time()

    for i, row in enumerate(enc_rows, 1):
        visit_id = row["visit_id"]
        pid = row["patient_id"]
        note_path_rel = f"documents/{visit_id}.txt"

        if visit_id in existing_visit_ids:
            n_skip += 1
            patient_context[pid].append(row)
            continue

        plan = plans.get(pid)
        if not plan:
            print(f"  [{i:>4}/{len(enc_rows)}] {visit_id} SKIP: no plan for {pid}",
                  file=sys.stderr)
            n_err += 1
            continue

        prompt = _assemble_prompt(row, plan, patient_context)
        request = {
            "model": args.model,
            "input": prompt,
            "reasoning": {"effort": args.reasoning_effort},
            "store": False,
        }

        started = _now()
        try:
            resp = client.responses.create(**request)
            text = getattr(resp, "output_text", "") or ""
            completed = _now()

            (docs_dir / f"{visit_id}.txt").write_text(text, encoding="utf-8")

            usage = getattr(resp, "usage", None)
            tokens_in = getattr(usage, "input_tokens", None) if usage else None
            tokens_out = getattr(usage, "output_tokens", None) if usage else None

            manifest_rows.append({
                "visit_id": visit_id,
                "patient_id": pid,
                "corpus": "synth_v3",
                "corpus_version": "v1.0",
                "patient_dob": row["patient_dob"],
                "patient_sex": row["patient_sex"],
                "patient_race": "",
                "patient_ethnicity": "",
                "patient_zip3": "",
                "visit_date": row["visit_date"],
                "visit_number": row["visit_number"],
                "age_at_visit": row["age_at_visit"],
                "note_type": row["note_type"],
                "note_template": row["note_template"],
                "care_setting": row["care_setting"],
                "provider_persona": row["provider_persona"],
                "specialty": row["specialty"],
                "note_char_count": len(text),
                "note_word_count": _word_count(text),
                "note_section_count": _section_count(text),
                "note_language": "en",
                "generator_model": getattr(resp, "model", args.model) or args.model,
                "generator_seed": "",
                "generator_tokens_in": tokens_in or "",
                "generator_tokens_out": tokens_out or "",
                "generator_cost_usd": "",
                "phenotype_profile": row["phenotype_profile"],
                "note_path": note_path_rel,
                "gold_path": "",
                "semantic_plan_path": f"../../episynth_corpus/v3/patients/{pid}.json",
                "raw_source_path": "",
                "gold_source": "semantic_plan_derived",
                "gold_conformant": "",
                "silver_labeler": "",
                "review_status": "unreviewed",
                "epilepsy_relevance_score": "",
                "created_at": completed,
                "created_by": "generate_synth_v3_corpus.py v1.0",
                "ingest_batch": ingest_batch,
                "notes": f"prompt_sha256={_sha(prompt)[:16]}",
            })
            patient_context[pid].append(row)
            n_new += 1
        except Exception as e:
            print(f"  [{i:>4}/{len(enc_rows)}] {visit_id} ERR: {e}", file=sys.stderr)
            n_err += 1
            continue

        # Flush manifest every 25 docs so partial progress is durable
        if i % 25 == 0 or i == len(enc_rows):
            with manifest_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
                writer.writeheader()
                for r in manifest_rows:
                    writer.writerow(r)
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(enc_rows) - i) / rate if rate > 0 else 0
            print(f"  [{i:>4}/{len(enc_rows)}] new={n_new} skip={n_skip} err={n_err} "
                  f"elapsed={elapsed:.0f}s eta={eta/60:.1f}min")

    # Final manifest write (in case len(enc_rows) < 25)
    with manifest_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for r in manifest_rows:
            writer.writerow(r)

    (out_dir / "run_metadata.json").write_text(json.dumps({
        "corpus": "synth_v3",
        "corpus_version": "v1.0",
        "generator_model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "encounter_manifest": str(enc_manifest_path),
        "n_visits_planned": len(enc_rows),
        "n_generated_new": n_new,
        "n_skipped_existing": n_skip,
        "n_errors": n_err,
        "ingest_batch": ingest_batch,
        "created_at": _now(),
    }, indent=2), encoding="utf-8")

    print(f"\nDone. new={n_new}, skipped={n_skip}, errors={n_err}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
