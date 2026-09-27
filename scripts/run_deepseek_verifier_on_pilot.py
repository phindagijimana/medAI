#!/usr/bin/env python3
"""B5: DeepSeek verifier over the R4e-i tuned-Med42 pilot extractions.

Uses services/llm_verifier.py with DeepSeek-R1-Distill-Llama-8B as the
verifier and the tuned-unconstrained arm (variant "tuned") as the
extractor being verified. This is inference-only, no fine-tune contamination
(the tuned adapter was trained on synth-v1 + F-S, not on pilot; and
DeepSeek never saw any of these documents).

Emits eval/results/deepseek_verifier_on_pilot.csv with columns:
    doc_id, field_path, extractor_value, extractor_evidence,
    verifier_supported, evidence_matches, laterality_consistent,
    negation_consistent, temporal_consistent, verifier_confidence

Also emits a small confusion-matrix-style summary printed to stdout.

Fallback: if DeepSeek verifier output cannot be parsed as JSON on more
than 30% of calls, print a warning and suggest re-running with
`--verifier gpt-5.6-terra` (inference-only OpenAI, no fine-tune
contamination).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from schema import DocumentMetadata, DocumentType  # noqa: E402
from services.extract import DecodingConfig  # noqa: E402
from services.llm_verifier import verify_phenotype  # noqa: E402

RUN_DIR = REPO / "data" / "episynth_pilot" / "run_001"
FREEZE_DIR = REPO / "data" / "MedAI_Phase6D1_v2_GPT_MultiGenerator_PreRun_Freeze"
TUNED_MANIFESTS = REPO / "data" / "run_manifests_pilot_tuned"
OUT_CSV = REPO / "eval" / "results" / "deepseek_verifier_on_pilot.csv"


def _load_pilot_doc(pid: str, arm_dir: str, cond_dir: str = "") -> tuple[str, DocumentType]:
    """Return (source_text, doc_type) for one pilot document."""
    if cond_dir:
        p = RUN_DIR / arm_dir / cond_dir / pid / "output.txt"
    else:
        p = RUN_DIR / arm_dir / pid / "output.txt"
    plan = json.loads(
        (FREEZE_DIR / "semantic_plans" / f"{pid}.json").read_text()
    )
    fam = plan.get("document_family", "epilepsy_clinic_letter")
    dt = DocumentType.EEG_REPORT if fam == "eeg_report" else DocumentType.PROGRESS_NOTE
    return p.read_text(encoding="utf-8"), dt


def _iter_tuned_extractions():
    """Load parsed phenotypes from the R4e-i tuned-unconstrained manifests."""
    for f in TUNED_MANIFESTS.rglob("*.json"):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not m.get("final_valid"):
            continue
        parsed = m.get("parsed_value")
        if not parsed:
            continue
        yield m, parsed


def main():
    ap = argparse.ArgumentParser(description="B5 DeepSeek verifier on pilot tuned outputs.")
    ap.add_argument("--verifier", default="deepseek",
                    choices=["deepseek", "gpt-5.6-terra"],
                    help="Verifier backend (default deepseek).")
    ap.add_argument("--limit", type=int, default=None, help="First N manifests only.")
    args = ap.parse_args()

    if not TUNED_MANIFESTS.exists():
        raise SystemExit(
            f"{TUNED_MANIFESTS} does not exist — run the R4e-i variant sweep first."
        )

    if args.verifier == "deepseek":
        from services.deepseek_backend import DeepSeekBackend
        backend = DeepSeekBackend()
        backend.load()
    else:
        from services.openai_backend import OpenAIBackend
        backend = OpenAIBackend(model_name=args.verifier)

    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=256, seed=0, constrained=False,
    )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    n_calls = n_parse_fail = 0
    verdict_confusion = Counter()

    manifests_iter = list(_iter_tuned_extractions())
    if args.limit:
        manifests_iter = manifests_iter[: args.limit]
    print(f"Manifests to verify: {len(manifests_iter)}")

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "manifest_run_id", "doc_id", "arm", "module", "field_path",
            "extractor_value", "extractor_evidence",
            "verifier_supported", "evidence_matches",
            "laterality_consistent", "negation_consistent",
            "temporal_consistent", "verifier_confidence",
            "verifier_rationale",
        ])

        for m, parsed in manifests_iter:
            doc_id = m.get("source_doc_id", "")
            arm = m.get("arm", "")
            # For each manifest we need the source_text; the tuned manifests
            # embed source doc_id like "pilot-tuned-<render_arm>-<cond>-<pid>".
            source_text = m.get("source_text_snippet") or ""
            if not source_text:
                # Reconstruct from doc_id — parse "pilot-tuned-{render}-{cond}-{pid}"
                parts = doc_id.split("-")
                pid = parts[-1]
                cond = parts[-2] if len(parts) >= 4 else ""
                render = "-".join(parts[2:-2]) if len(parts) > 4 else "C0"
                try:
                    source_text, _ = _load_pilot_doc(pid, render, cond)
                except Exception:
                    continue

            # Build a minimal phenotype dict for the verifier — it walks modules.
            phen_dict = parsed if isinstance(parsed, dict) and "document" in parsed else \
                {"document": {"doc_id": doc_id}, m.get("prompt_id", "unknown").split(".")[0]: parsed}

            verdicts = verify_phenotype(
                verifier_backend=backend, source_text=source_text,
                phenotype=phen_dict, decoding=decoding,
            )
            for v in verdicts:
                d = v.as_dict()
                n_calls += 1
                if d.get("verifier_confidence") == "unknown" and \
                   d.get("verifier_rationale", "").startswith("verifier_error"):
                    n_parse_fail += 1
                verdict_confusion[(d.get("supported"), d.get("verifier_confidence"))] += 1
                w.writerow([
                    m.get("run_id", "")[:12], doc_id, arm,
                    d["field_path"].split(".")[0], d["field_path"],
                    "(see manifest)", "(see manifest)",
                    d.get("supported"), d.get("evidence_matches"),
                    d.get("laterality_consistent"), d.get("negation_consistent"),
                    d.get("temporal_consistent"), d.get("verifier_confidence"),
                    d.get("verifier_rationale", ""),
                ])

    print(f"\nTotal verifier calls: {n_calls}")
    print(f"Verifier parse-fail:  {n_parse_fail}")
    if n_calls and n_parse_fail / n_calls > 0.30 and args.verifier == "deepseek":
        print("WARNING: DeepSeek parse-fail rate exceeds 30% — fall back to GPT verifier:")
        print("    venv/bin/python scripts/run_deepseek_verifier_on_pilot.py --verifier gpt-5.6-terra")

    print("\nConfusion (supported × verifier_confidence):")
    for (sup, conf), n in sorted(verdict_confusion.items(), key=lambda x: -x[1]):
        print(f"  supported={sup!s:>5}  confidence={conf:<10}  n={n}")
    print(f"\nwrote → {OUT_CSV}")


if __name__ == "__main__":
    main()
