#!/usr/bin/env python3
"""CLI: run the LEO chain and write Claim JSONL (P1.6).

Usage:

    venv-medcat/bin/python scripts/extract_chain_cli.py note.txt \\
        --output claims.jsonl \\
        --document-id DEMO-001

    cat note.txt | venv-medcat/bin/python scripts/extract_chain_cli.py - \\
        --output claims.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="Path to note text, or '-' for stdin")
    ap.add_argument("--output", "-o", required=True, help="Output JSONL path")
    ap.add_argument("--document-id", default="cli-doc")
    ap.add_argument("--doc-date", default=date.today().isoformat())
    ap.add_argument("--ledger-db", default="",
                    help="SQLite ledger path (default: data/ledger/evidence.sqlite)")
    ap.add_argument("--no-ledger", action="store_true",
                    help="Do not persist to ledger")
    g = ap.add_argument_group("LLM channel (Reason B); default is specialist-only")
    g.add_argument("--llm-live", action="store_true",
                   help="Run Med42-8B now (needs a GPU)")
    g.add_argument("--llm-adapter", default="",
                   help="LoRA adapter dir for --llm-live (e.g. Arm H)")
    g.add_argument("--llm-manifests", action="append", default=[],
                   help="Replay Med42 outputs from run-manifest dir(s) instead of a GPU "
                        "(document-id must be the manifest letter id, e.g. EA0161)")
    g.add_argument("--llm-arm", default="M2",
                   help="Prompt arm to run/replay (M0..M3), default M2")
    args = ap.parse_args()

    if args.input == "-":
        text = sys.stdin.read()
    else:
        p = Path(args.input)
        if not p.is_absolute():
            p = REPO / p
        text = p.read_text(encoding="utf-8")

    from services.chain_pipeline import ChainPipeline
    from services.ledger import EvidenceLedger

    ledger = None
    if not args.no_ledger:
        db = Path(args.ledger_db) if args.ledger_db else REPO / "data" / "ledger" / "evidence.sqlite"
        ledger = EvidenceLedger(db)

    reasoner = None
    if args.llm_live:
        from services.chain_llm import load_live_reasoner
        reasoner = load_live_reasoner(arm=args.llm_arm, adapter_dir=args.llm_adapter)
    elif args.llm_manifests:
        from services.chain_llm import ManifestLLMReasoner
        dirs = [Path(d) if Path(d).is_absolute() else REPO / d for d in args.llm_manifests]
        reasoner = ManifestLLMReasoner(dirs, arm=args.llm_arm)
        if not reasoner.has(args.document_id):
            print(f"[extract_chain_cli] WARNING: no {args.llm_arm} manifests for "
                  f"{args.document_id!r}; running specialist-only", file=sys.stderr)

    pipeline = ChainPipeline(llm_reasoner=reasoner)
    stats, claims = pipeline.extract(
        text,
        document_id=args.document_id,
        doc_date=args.doc_date,
        ledger=ledger,
        return_claims=True,
    )

    out = Path(args.output)
    if not out.is_absolute():
        out = REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for c in claims:
            f.write(c.model_dump_json() + "\n")

    print(
        f"[extract_chain_cli] claims={len(claims)} "
        f"accept={stats.n_accepted} review={stats.n_review} reject={stats.n_rejected} "
        f"llm[agree={stats.n_llm_agree} disagree={stats.n_llm_disagree} "
        f"only={stats.n_llm_only} unsupported={stats.n_llm_unsupported}] "
        f"→ {out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
