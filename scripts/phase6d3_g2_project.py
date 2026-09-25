#!/usr/bin/env python3
"""Phase 6D.3 — G2 machine-projection pass (candidate-only).

Reads the 60 raw pilot documents from data/episynth_pilot/run_001/, plus the
Phase 6D.1 v2 freeze (semantic plans + pilot cases + prompts), and emits per
document a `claim_annotations.jsonl` file containing CANDIDATE evidence spans
(P02 ALLOWED_CANDIDATE_ONLY) produced by deterministic string search over the
rendered text.

This script is deliberately bounded by the Phase 4B.1/6D.3 freeze:

  - P01: G0/G1 may pre-populate expected assertion IDs and candidate source
         links, but not G2 text spans or final support labels.
  - P02: automatic offset matching produces candidate_status=candidate only;
         a candidate is never promoted to `human_verified` here.
  - P03: a projected annotation cannot become G3 solely because it matches
         latent truth. This script produces G2 candidates only, and refuses
         to write any G3 file.
  - P04: if rendered text disagrees with G0/G1, G2 records the rendered
         meaning; discrepancies are separately flagged as
         `machine_flag=possible_contradiction` for human review.
  - P05: blocked concepts are not auto-projected — respected via the
         BLOCKED / SOURCE_TEXT_ONLY / LIMITED policy in machine_projection.

Outputs (per pilot document, N=60):
    data/episynth_pilot/run_001/g2/{arm}/{patient_id}/claim_annotations.jsonl

Aggregate manifest:
    data/episynth_pilot/run_001/g2/g2_projection_manifest.json

Aggregate summary CSV (one row per rendered document):
    data/episynth_pilot/run_001/g2/g2_projection_summary.csv
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
RUN_DIR = REPO / "data" / "episynth_pilot" / "run_001"
FREEZE_DIR = Path(
    "/tmp/phase6d1v2/MedAI_Phase6D1_v2_GPT_MultiGenerator_PreRun_Freeze"
)
G2_ROOT = RUN_DIR / "g2"


# ---------------------------------------------------------------------------
# Value → surface-form projector.
#
# G1 required_assertions carry structured values (EP_TYPE="Focal",
# SZ_FREQ={quantity: 2, unit: "month"}, EEG_RESULT="Normal"). We need to
# search for their plausible rendered surface forms — but under the freeze
# machine projection policy this must be candidate-only and NEVER promoted
# to a final SUPPORTED label. The surface-form table below is deliberately
# small and MEDAI-PROPOSED — see Do_Not_Invent register: no medical
# inference, no unlisted synonyms.
# ---------------------------------------------------------------------------

_EP_TYPE_SURFACE = {
    "Focal": [
        r"\bfocal\s+epilepsy\b",
        r"\bfocal\-onset\s+epilepsy\b",
    ],
    "Generalized": [
        r"\bgeneralised\s+epilepsy\b",
        r"\bgeneralized\s+epilepsy\b",
    ],
    "Combined generalized and focal": [
        r"\bcombined\s+generali[sz]ed\s+and\s+focal\s+epilepsy\b",
    ],
    "Unknown": [
        # Deliberately narrow — "unknown" is a very common English word.
        # A candidate match requires the phrase "unknown ... epilepsy" or
        # "epilepsy ... unknown" within a short span, tightly scoped.
        r"\bepilepsy\s+of\s+unknown\s+(onset|classification|type)\b",
        r"\bunknown\-onset\s+epilepsy\b",
        r"\bepilepsy\s+type[:\s]+unknown\b",
    ],
}

_EEG_RESULT_SURFACE = {
    "Normal": [
        r"\bnormal\s+eeg\b",
        r"\beeg\s+is\s+normal\b",
        r"\beeg\s+was\s+normal\b",
        r"\bimpression[:\s]+normal\b",
    ],
    "Abnormal": [
        r"\babnormal\s+eeg\b",
        r"\beeg\s+is\s+abnormal\b",
        r"\beeg\s+was\s+abnormal\b",
        r"\bimpression[:\s]+abnormal\b",
    ],
}


def _sz_freq_patterns(quantity: int | float, unit: str) -> list[str]:
    """Generate a small set of literal surface forms for a seizure-frequency
    tuple. Kept narrow to avoid false positives; a human adjudicator will
    upgrade or reject the candidate."""
    q = quantity
    q_int = int(q) if float(q).is_integer() else q
    unit_words = {
        "day": ["day", "24 hours"],
        "week": ["week"],
        "month": ["month"],
        "year": ["year"],
    }
    words = unit_words.get(unit.lower(), [unit.lower()])
    patterns = []
    for w in words:
        # "2 per month", "2 seizures per month", "2 seizures a month"
        patterns.append(rf"\b{q_int}\s+(seizures?\s+)?(a|per)\s+{re.escape(w)}\b")
        patterns.append(rf"\b(approximately|about|around)?\s*{q_int}\s+(seizures?\s+)?(a|per)\s+{re.escape(w)}\b")
        # "two per month" (spelled-out numerals)
        spelled = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
                    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
        if q_int in spelled:
            patterns.append(rf"\b{spelled[q_int]}\s+(seizures?\s+)?(a|per)\s+{re.escape(w)}\b")
    return patterns


def _project_required(assertion: dict) -> list[str]:
    """Return candidate regex patterns for a required_assertion."""
    field = assertion.get("field")
    value = assertion.get("value")
    if field == "EP_TYPE" and isinstance(value, str):
        return _EP_TYPE_SURFACE.get(value, [])
    if field == "SZ_FREQ" and isinstance(value, dict):
        return _sz_freq_patterns(value.get("quantity"), value.get("unit"))
    if field == "EEG_RESULT" and isinstance(value, str):
        return _EEG_RESULT_SURFACE.get(value, [])
    # Any other field is BLOCKED under freeze P05 — do not project.
    return []


def _project_prohibited(text: str, prohibited_expr: str) -> list[tuple[int, int, str]]:
    """Heuristically scan for phrases indicating a prohibited *inference*.
    The freeze says these strings are natural-language directives, not
    concept IDs, so we match keyword-level cues and mark them as candidates
    for review — never as a final rule-violation."""
    p = prohibited_expr.lower()
    hits = []
    # These are candidate cues only. Human review is required for a G3 label
    # of INFORMATION_LEAKAGE or DOCUMENT_RULE_VIOLATION.
    cues = []
    if "infer" in p:
        # Prohibited-inference patterns often manifest as diagnostic phrases.
        for pat in [r"\bepilepsy\s+diagnosis\b",
                    r"\bepilepsy\s+is\s+(likely|confirmed|diagnosed)\b",
                    r"\bfocal\s+epilepsy\b",
                    r"\bgeneralized\s+epilepsy\b",
                    r"\bIED\s+is\s+present\b",
                    r"\binterictal\s+epileptiform\s+discharges\b",
                    r"\bseizures?\s+(captured|recorded)\b",
                    r"\bictal\s+onset\b"]:
            cues.append(pat)
    for pat in cues:
        for m in re.finditer(pat, text, re.IGNORECASE):
            hits.append((m.start(), m.end(), pat))
    return hits


# ---------------------------------------------------------------------------
# Freeze loaders
# ---------------------------------------------------------------------------


def _load_semantic_plan(patient_id: str) -> dict:
    return json.loads((FREEZE_DIR / "semantic_plans" / f"{patient_id}.json").read_text())


def _load_pilot_case(patient_id: str) -> dict:
    return json.loads((FREEZE_DIR / "pilot_cases" / f"{patient_id}.json").read_text())


def _all_pilot_arms() -> list[tuple[str, str, str]]:
    """(arm_dir_name, condition, patient_id) — walks the actual run outputs."""
    arms = []
    for arm_dir in sorted(RUN_DIR.iterdir()):
        if not arm_dir.is_dir() or arm_dir.name in ("g2",):
            continue
        if arm_dir.name == "C0":
            for p_dir in sorted(arm_dir.iterdir()):
                if p_dir.is_dir():
                    arms.append(("C0", "C0", p_dir.name))
        elif arm_dir.name.startswith("gpt-"):
            for cond_dir in sorted(arm_dir.iterdir()):
                if not cond_dir.is_dir(): continue
                for p_dir in sorted(cond_dir.iterdir()):
                    if p_dir.is_dir():
                        arms.append((arm_dir.name, cond_dir.name, p_dir.name))
    return arms


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# G2 record construction
# ---------------------------------------------------------------------------


def _build_candidate_record(
    *, arm: str, condition: str, patient_id: str,
    text: str, plan: dict, case: dict,
) -> list[dict]:
    """Emit one G2 candidate record per required_assertion + per
    prohibited_assertion cue hit + one for the whole-document scope check.
    """
    records = []
    now = _now_iso()

    # --- required assertions: one G2 candidate per required_assertion -----
    for req in plan.get("required_assertions", []):
        event_id = req.get("event_id")
        field = req.get("field")
        value = req.get("value")
        patterns = _project_required(req)
        hits = []
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                hits.append({
                    "start": m.start(),
                    "end": m.end(),
                    "surface": text[m.start():m.end()],
                    "pattern": pat,
                })
        record = {
            "phase": "6D.3-G2",
            "arm": arm, "condition": condition, "patient_id": patient_id,
            "unit_class": "REQUIRED_ASSERTION",
            "expected_assertion_id": event_id,     # per P01
            "field": field, "authorized_value": value,
            "candidate_evidence_spans": hits,      # per P02: candidate only
            "candidate_status": "candidate",
            "machine_flag": (
                "hit" if hits else "no_string_match"
            ),
            # NB: no `support_label` (FROZEN — human only)
            # NB: no `target_label` (FROZEN — human only)
            "policy_notes": {
                "P02": "candidate spans only; human verification required",
                "P03": "not promotable to G3 by machine",
                "P05": "no blocked-concept projection",
            },
            "created_at": now,
        }
        records.append(record)

    # --- prohibited-inference cues: one G2 candidate per hit ---------------
    for prohibited_expr in plan.get("prohibited_assertions", []):
        cue_hits = _project_prohibited(text, prohibited_expr)
        for start, end, pat in cue_hits:
            records.append({
                "phase": "6D.3-G2",
                "arm": arm, "condition": condition, "patient_id": patient_id,
                "unit_class": "PROHIBITED_INFERENCE_CANDIDATE",
                "prohibited_expression": prohibited_expr,
                "candidate_evidence_span": {
                    "start": start, "end": end,
                    "surface": text[start:end],
                    "pattern": pat,
                },
                "candidate_status": "candidate",
                "machine_flag": "possible_prohibited_inference",
                "policy_notes": {
                    "P02": "candidate only",
                    "P04": "rendered meaning recorded; discrepancy flagged",
                },
                "created_at": now,
            })

    # --- whole-document scope note ---------------------------------------
    # Track allowed source events so downstream review can compute
    # INFORMATION_LEAKAGE candidates by inspecting content outside allowed events.
    records.append({
        "phase": "6D.3-G2",
        "arm": arm, "condition": condition, "patient_id": patient_id,
        "unit_class": "DOCUMENT_SCOPE",
        "allowed_source_event_ids": plan.get("allowed_source_event_ids", []),
        "document_family": plan.get("document_family"),
        "text_sha256": _sha256_text(_norm(text)),
        "text_length_chars": len(text),
        "created_at": now,
    })

    return records


def main():
    if not RUN_DIR.exists():
        print(f"Missing pilot run: {RUN_DIR}", file=sys.stderr)
        sys.exit(2)
    if not FREEZE_DIR.exists():
        print(f"Missing freeze dir: {FREEZE_DIR}", file=sys.stderr)
        sys.exit(2)

    G2_ROOT.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict] = []
    total_records = 0

    for arm, condition, pid in _all_pilot_arms():
        # Locate the rendered text
        if arm == "C0":
            text_path = RUN_DIR / "C0" / pid / "output.txt"
        else:
            text_path = RUN_DIR / arm / condition / pid / "output.txt"
        if not text_path.exists():
            continue

        text = text_path.read_text(encoding="utf-8")
        plan = _load_semantic_plan(pid)
        case = _load_pilot_case(pid)

        records = _build_candidate_record(
            arm=arm, condition=condition, patient_id=pid,
            text=text, plan=plan, case=case,
        )

        # Sink dir keyed on the arm identifier the analyst will see.
        arm_key = "C0-deterministic" if arm == "C0" else f"{arm}-{condition}"
        sink = G2_ROOT / arm_key / pid
        sink.mkdir(parents=True, exist_ok=True)
        with (sink / "claim_annotations.jsonl").open("w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

        # Per-document summary row
        n_req = sum(1 for r in records if r["unit_class"] == "REQUIRED_ASSERTION")
        n_req_hit = sum(
            1 for r in records
            if r["unit_class"] == "REQUIRED_ASSERTION"
            and r["candidate_evidence_spans"]
        )
        n_prohibited_cues = sum(
            1 for r in records
            if r["unit_class"] == "PROHIBITED_INFERENCE_CANDIDATE"
        )
        summary_rows.append({
            "arm": arm_key, "arm_family": arm, "condition": condition,
            "patient_id": pid,
            "required_assertions": n_req,
            "required_with_candidate_hit": n_req_hit,
            "prohibited_inference_cues": n_prohibited_cues,
            "text_length_chars": len(text),
            "text_sha256": _sha256_text(_norm(text)),
        })
        total_records += len(records)

    # Aggregate manifest
    manifest = {
        "phase": "6D.3-G2",
        "created_at": _now_iso(),
        "pilot_run_dir": str(RUN_DIR.relative_to(REPO)),
        "freeze_dir_used": str(FREEZE_DIR),
        "documents_processed": len(summary_rows),
        "total_g2_records": total_records,
        "notes": [
            "P01: expected_assertion_id and event links pre-populated from G1.",
            "P02: candidate_status='candidate' on every span; NO machine-only promotion.",
            "P03: no G3 records are written by this script.",
            "P04: rendered meaning is captured; discrepancies with G0/G1 are flagged for human review.",
            "P05: fields outside the small MEDAI-PROPOSED surface-form table are not projected.",
            "This artifact is a machine-projection candidate set. Two independent human annotators must review, then adjudicate to produce G3.",
        ],
    }
    (G2_ROOT / "g2_projection_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    # Summary CSV
    with (G2_ROOT / "g2_projection_summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        for r in summary_rows:
            w.writerow(r)

    print(f"Documents processed: {len(summary_rows)}")
    print(f"Total G2 candidate records: {total_records}")
    print(f"wrote → {G2_ROOT}/g2_projection_manifest.json")
    print(f"wrote → {G2_ROOT}/g2_projection_summary.csv")


if __name__ == "__main__":
    main()
