#!/usr/bin/env python3
"""Generate a 1000-pair synthetic clinical-note corpus for fine-tuning.

For each of the 500 patients under `data/episynth_corpus/v1/patients/`,
render two documents via GPT-5.6-sol under the C3 semantic-plan-
constrained prompt:

    1. Progress note (always)
    2. Modality report (chosen from patient's phenotype):
         - MRI_FINDING present → MRI report
         - Otherwise → EEG report (or another progress note if minimal
           phenotype)

Output layout (Phase-6D.2-compatible):

    data/episynth_corpus/v1/documents/{PID}/{doc_type}/output.txt
                                           /request.json
                                           /response.json
                                           /metadata.json

Aggregate manifest:
    data/episynth_corpus/v1/execution_manifest.csv
    data/episynth_corpus/v1/run_metadata.json

Idempotent — if an output.txt already exists for (patient, doc_type),
that render is skipped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

CORPUS_ROOT = REPO / "data" / "episynth_corpus" / "v1"
PATIENTS_DIR = CORPUS_ROOT / "patients"
DOCS_DIR = CORPUS_ROOT / "documents"
DEFAULT_MODEL = "gpt-5.6-sol"


PROGRESS_NOTE_PROMPT = """You are rendering a synthetic clinical epilepsy progress note for a research benchmark.

Patient information (authorized clinical facts — express EVERY one of these accurately, use no other clinical content):

{authorized_content}

Write a single realistic epilepsy clinic progress note. Include a brief salutation, history of present illness, current medications, seizure burden summary, assessment, and plan.

RULES:
- Express every authorized fact accurately, using standard clinical language.
- Do NOT invent additional clinical facts, diagnoses, findings, treatments, or investigations that are not authorized.
- Do NOT infer higher-level conclusions from lower-level observations.
- Do NOT include a patient name, DOB, or hospital number.
- Return only the document text (no JSON, no code fence, no explanations).
"""


MRI_REPORT_PROMPT = """You are rendering a synthetic brain MRI report for a research benchmark.

Patient information (authorized clinical facts — express EVERY one of these accurately, use no other clinical content):

{authorized_content}

Write a single realistic radiology MRI brain report. Include Technique, Findings, and Impression sections. Address the reported MRI finding directly.

RULES:
- Express every authorized fact accurately, using standard neuroradiology language.
- Do NOT invent additional imaging findings not authorized.
- Do NOT invent diagnostic conclusions that go beyond what the MRI itself supports.
- Do NOT include a patient name, DOB, or accession number.
- Return only the document text.
"""


EEG_REPORT_PROMPT = """You are rendering a synthetic EEG report for a research benchmark.

Patient information (authorized clinical facts — express EVERY one of these accurately, use no other clinical content):

{authorized_content}

Write a single realistic routine EEG interpretation report. Include Clinical Indication, Technique, Findings, and Impression sections.

RULES:
- Express every authorized fact accurately using standard neurophysiology language.
- Do NOT invent additional interictal or ictal findings not authorized.
- Do NOT infer epilepsy diagnosis, seizure type, or ictal localization solely from EEG.
- Do NOT include a patient name, DOB, or accession number.
- Return only the document text.
"""


def _authorized_content_str(plan: dict) -> str:
    """Human-readable but strictly enumerated list of required assertions."""
    lines = []
    for req in plan.get("required_assertions", []):
        field = req["field"]
        value = req["value"]
        if isinstance(value, (dict, list)):
            v = json.dumps(value, ensure_ascii=False)
        else:
            v = str(value)
        lines.append(f"  - {field}: {v}")
    return "\n".join(lines)


def _pick_second_doc_type(plan: dict) -> str:
    """Decide the second doc type based on the patient's phenotype."""
    has_mri = any(
        r["field"] == "MRI_FINDING" for r in plan.get("required_assertions", [])
    )
    return "mri_report" if has_mri else "eeg_report"


def _prompt_for(doc_type: str, plan: dict) -> str:
    ac = _authorized_content_str(plan)
    if doc_type == "progress_note":
        return PROGRESS_NOTE_PROMPT.format(authorized_content=ac)
    if doc_type == "mri_report":
        return MRI_REPORT_PROMPT.format(authorized_content=ac)
    if doc_type == "eeg_report":
        return EEG_REPORT_PROMPT.format(authorized_content=ac)
    raise ValueError(f"unknown doc_type {doc_type!r}")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--reasoning-effort", default="medium")
    ap.add_argument("--patients-glob", default="P0009*.json",
                     help="Which patients to render (default: last 100 for smoke test)")
    ap.add_argument("--doc-types", default="progress_note,second",
                     help="Comma-separated doc types per patient; 'second' means auto-choose")
    ap.add_argument("--limit", type=int, default=None,
                     help="Optional cap on number of patients to render (for staging)")
    args = ap.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not set. `set -a; source .env; set +a` first.")

    try:
        from openai import OpenAI
    except ImportError as e:
        raise SystemExit(f"openai not installed: {e}")

    client = OpenAI()

    # Enumerate patient plans (excludes _case.json)
    plan_paths = sorted(
        p for p in PATIENTS_DIR.glob(args.patients_glob)
        if not p.stem.endswith("_case")
    )
    if args.limit:
        plan_paths = plan_paths[:args.limit]
    print(f"Rendering {len(plan_paths)} patients × {len(args.doc_types.split(','))} docs each")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = CORPUS_ROOT / "execution_manifest.csv"
    manifest_rows = []
    if manifest_path.exists():
        with manifest_path.open() as fh:
            manifest_rows = list(csv.DictReader(fh))
    existing = {(r["patient_id"], r["doc_type"]) for r in manifest_rows}

    n_new = n_skip = n_err = 0
    t0 = time.time()

    for pi, plan_path in enumerate(plan_paths, 1):
        pid = plan_path.stem
        plan = json.loads(plan_path.read_text())

        for doc_type_spec in args.doc_types.split(","):
            doc_type = doc_type_spec.strip()
            if doc_type == "second":
                doc_type = _pick_second_doc_type(plan)

            key = (pid, doc_type)
            if key in existing:
                n_skip += 1
                continue

            outdir = DOCS_DIR / pid / doc_type
            outdir.mkdir(parents=True, exist_ok=True)

            prompt = _prompt_for(doc_type, plan)
            request = {
                "model": args.model,
                "input": prompt,
                "reasoning": {"effort": args.reasoning_effort},
                "store": False,
            }
            (outdir / "request.json").write_text(
                json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8",
            )

            started = _now()
            try:
                resp = client.responses.create(**request)
                text = getattr(resp, "output_text", "") or ""
                raw = resp.model_dump_json(indent=2)
                (outdir / "response.json").write_text(raw, encoding="utf-8")
                (outdir / "output.txt").write_text(text, encoding="utf-8")
                completed = _now()
                (outdir / "metadata.json").write_text(json.dumps({
                    "response_id": getattr(resp, "id", None),
                    "response_model": getattr(resp, "model", None),
                    "created_at": getattr(resp, "created_at", None),
                    "started_at": started, "completed_at": completed,
                }, indent=2), encoding="utf-8")
                manifest_rows.append({
                    "patient_id": pid, "doc_type": doc_type,
                    "model": args.model, "status": "completed",
                    "started_at": started, "completed_at": completed,
                    "input_sha256": _sha(prompt),
                    "output_sha256": _sha(text),
                    "response_model": getattr(resp, "model", None) or "",
                    "response_id": getattr(resp, "id", "") or "",
                    "error": "",
                })
                n_new += 1
            except Exception as e:
                (outdir / "error.txt").write_text(repr(e), encoding="utf-8")
                manifest_rows.append({
                    "patient_id": pid, "doc_type": doc_type,
                    "model": args.model, "status": "failed",
                    "started_at": started, "completed_at": _now(),
                    "input_sha256": _sha(prompt),
                    "output_sha256": "", "response_model": "",
                    "response_id": "", "error": repr(e),
                })
                n_err += 1
                print(f"  [{pi:>4}/{len(plan_paths)}] {pid} {doc_type} ERR: {e}",
                      file=sys.stderr)
                continue

        if pi % 25 == 0 or pi == len(plan_paths):
            elapsed = time.time() - t0
            rate = pi / elapsed if elapsed > 0 else 0
            eta_s = (len(plan_paths) - pi) / rate if rate > 0 else 0
            print(f"  [{pi:>4}/{len(plan_paths)}] elapsed={elapsed:.0f}s "
                  f"rate={rate:.2f}/s new={n_new} skip={n_skip} err={n_err} "
                  f"eta={eta_s/60:.1f}min")

    # Write manifest
    fields = ["patient_id", "doc_type", "model", "status",
              "started_at", "completed_at", "input_sha256", "output_sha256",
              "response_model", "response_id", "error"]
    with manifest_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in manifest_rows:
            w.writerow(r)

    (CORPUS_ROOT / "run_metadata.json").write_text(json.dumps({
        "corpus_version": "v1",
        "generator_model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "created_at": _now(),
        "total_documents": n_new + n_skip,
        "new_documents_this_run": n_new,
        "skipped_existing": n_skip,
        "failed": n_err,
    }, indent=2), encoding="utf-8")

    print(f"\nDone. new={n_new}, skipped={n_skip}, errors={n_err}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
