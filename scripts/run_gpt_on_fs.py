#!/usr/bin/env python3
"""Run GPT (gpt-5.6-terra) M0/M1/M2 on the 200-doc Fonferko-Shadrach corpus.

R3c-relaxed: GPT-as-extractor is only valid on F-S here because F-S notes
are real clinician-authored, so any GPT tier is fine. gpt-5.6-terra is
chosen because it authored no F-S content (there was no F-S synthesis by
GPT — F-S is Shadrach 2024's native Zenodo release). Manuscript reports
this tier choice explicitly.

Cost cap: aborts if the running spend estimate exceeds MEDAI_OPENAI_COST_CAP
(default $25 USD).

Manifests: data/run_manifests_fs_gpt/<date>/
Score afterwards with scripts/score_llm_arms_vs_fs_gold.py after temporarily
pointing its MANIFESTS at that dir (or use the adapter script we ship).

Flags:
    --limit N    Only process the first N documents (smoke test).
    --dry-run    Enumerate + report cost estimate; do not call the API.
    --arms       Comma-separated arms subset (default M0,M1,M2).
    --tier       Override the OpenAI model ID (default gpt-5.6-terra).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

os.environ.setdefault(
    "MEDAI_MANIFEST_DIR", str(REPO / "data" / "run_manifests_fs_gpt")
)

from schema import DocumentMetadata, DocumentType, SCHEMA_VERSION  # noqa: E402
from services.extract import DecodingConfig  # noqa: E402

FS_DOCS_DIR = REPO / "data" / "fs_corpus" / "documents"

# Rough per-1K-token pricing for cost cap logic. Actual bill computed post-run
# from usage; this is only for pre-flight gating.
COST_PER_1K_TOKENS_USD = float(os.environ.get("MEDAI_OPENAI_COST_PER_1K", "0.03"))
# Rough average tokens per document × 3 arms.
EST_TOKENS_PER_DOC = int(os.environ.get("MEDAI_OPENAI_EST_TOKENS_PER_DOC", "4000"))


def _fs_docs():
    """Yield (patient_id, path) tuples for all EA* progress-note documents."""
    for pt_dir in sorted(FS_DOCS_DIR.iterdir()):
        if not pt_dir.is_dir() or not pt_dir.name.startswith("EA"):
            continue
        p = pt_dir / "progress_note" / "output.txt"
        if p.exists():
            yield (pt_dir.name, p)


def _estimate_cost(n_docs: int, arms: list[str]) -> float:
    """Very rough USD estimate: n_docs × n_arms × EST_TOKENS_PER_DOC × price/1k."""
    total_tokens = n_docs * len(arms) * EST_TOKENS_PER_DOC
    return total_tokens / 1000.0 * COST_PER_1K_TOKENS_USD


def main():
    ap = argparse.ArgumentParser(description="Run GPT M0/M1/M2 on F-S 200-doc corpus.")
    ap.add_argument("--limit", type=int, default=None, help="First N docs only.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Enumerate + report cost estimate; do not call API.")
    ap.add_argument("--arms", default="M0,M1,M2",
                    help="Comma-separated arm subset (default M0,M1,M2).")
    ap.add_argument("--tier", default="gpt-5.6-terra",
                    help="OpenAI model ID (default gpt-5.6-terra — tier that "
                         "authored no F-S content, so no self-scoring circularity).")
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    docs = list(_fs_docs())
    if args.limit:
        docs = docs[: args.limit]

    est_cost = _estimate_cost(len(docs), arms)
    cost_cap = float(os.environ.get("MEDAI_OPENAI_COST_CAP", "25"))

    print("=== GPT (F-S) extractor sweep ===")
    print(f"Tier:            {args.tier}")
    print(f"Documents:       {len(docs)} (of 200 available)")
    print(f"Arms:            {arms}")
    print(f"Est. tokens/doc: {EST_TOKENS_PER_DOC} (× {len(arms)} arms)")
    print(f"Est. cost:       ${est_cost:.2f}  (cap ${cost_cap:.2f})")
    print(f"Manifests:       {os.environ['MEDAI_MANIFEST_DIR']}")

    if est_cost > cost_cap:
        raise SystemExit(
            f"ABORT: pre-flight cost estimate ${est_cost:.2f} exceeds "
            f"cap ${cost_cap:.2f}. Set MEDAI_OPENAI_COST_CAP=<higher> to override."
        )

    if args.dry_run:
        for i, (pid, p) in enumerate(docs, 1):
            print(f"  [{i:3d}] {pid} -> {p.name}")
        print("--dry-run set; not calling API.")
        return

    # Deferred imports to keep --dry-run/--help cheap.
    from services.openai_backend import OpenAIBackend
    from services.router import extract_phenotype

    backend = OpenAIBackend(model_name=args.tier)
    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=int(os.environ.get("MEDAI_MAX_NEW_TOKENS", 1024)),
        seed=0,
        constrained=False,  # OpenAI backend does not use lm-format-enforcer
    )

    n_ok = n_err = 0
    running_output_tokens = 0
    running_cost_estimate = 0.0

    for i, (pid, text_path) in enumerate(docs, 1):
        text = text_path.read_text(encoding="utf-8")
        doc = DocumentMetadata(
            doc_id=f"fs-gpt-{args.tier}-{pid}",
            patient_id=pid,
            doc_type=DocumentType.PROGRESS_NOTE,
            doc_date=date(2026, 9, 25),
        )
        for extraction_arm in arms:
            try:
                result = extract_phenotype(
                    doc=doc, source_text=text, model_backend=backend,
                    arm=extraction_arm, schema_version=SCHEMA_VERSION,
                    decoding=decoding, write_manifests=True,
                )
                n_ok += 1
                summary = result.summary()
                first = summary and list(summary.values())[0] or {}
                # Rough incremental cost tracking (does not include input tokens).
                out_tok = first.get("tokens_generated") or 0
                running_output_tokens += out_tok
                # Assume ~equal input/output for rough cap check.
                running_cost_estimate = (
                    running_output_tokens * 2 / 1000.0 * COST_PER_1K_TOKENS_USD
                )
                print(f"  [{i:3d}/{len(docs)}] {pid} {extraction_arm} "
                      f"raw={first.get('raw_valid')} final={first.get('final_valid')} "
                      f"out_tok={out_tok}  running≈${running_cost_estimate:.2f}")
                if running_cost_estimate > cost_cap:
                    raise SystemExit(
                        f"ABORT: running cost estimate ${running_cost_estimate:.2f} "
                        f"exceeded cap ${cost_cap:.2f}."
                    )
            except SystemExit:
                raise
            except Exception as e:
                n_err += 1
                print(f"  [{i:3d}/{len(docs)}] {pid} {extraction_arm} ERR: {e}",
                      file=sys.stderr)

    print(f"\nDone. ok={n_ok}, err={n_err}")
    print(f"Total output tokens: {running_output_tokens}")
    print(f"Rough total cost estimate: ${running_cost_estimate:.2f}")


if __name__ == "__main__":
    main()
