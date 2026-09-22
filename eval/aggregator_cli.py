"""CLI entry point for the eval aggregator (paper §20 reproducibility).

Usage:
    python -m eval.aggregator_cli \
        --manifests data/run_manifests \
        --gold data/gold \
        --out out/eval_report.json \
        [--filter-arm M2]

Reads all run manifests, optionally pairs with gold labels, produces per-arm
`ArmSummary` and writes a single JSON report. Designed to run inside the
Dockerfile.eval container without any ML dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .aggregator import aggregate_manifests, load_gold


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifests", type=Path, required=True,
                    help="Directory containing run manifests (JSON per inference)")
    ap.add_argument("--gold", type=Path, default=None,
                    help="Directory containing gold JSON files keyed by doc_id (optional)")
    ap.add_argument("--out", type=Path, default=None,
                    help="Write the summary JSON to this path (else stdout)")
    ap.add_argument("--filter-arm", type=str, default=None,
                    help="Only include manifests from this arm")
    args = ap.parse_args()

    if not args.manifests.exists():
        print(f"error: manifests dir not found: {args.manifests}", file=sys.stderr)
        return 2

    gold = load_gold(args.gold) if args.gold else {}
    summaries = aggregate_manifests(args.manifests, gold=gold,
                                    filter_arm=args.filter_arm)

    if not summaries:
        print("(no manifests found)", file=sys.stderr)
        return 1

    payload = {arm: s.to_dict() for arm, s in summaries.items()}
    dump = json.dumps(payload, indent=2)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(dump, encoding="utf-8")
        # Terse console summary
        for arm, s in summaries.items():
            print(f"{arm}: n_documents={s.n_documents}  "
                  f"raw_valid_rate={s.raw_validity_rate:.3f}  "
                  f"final_valid_rate={s.final_validity_rate:.3f}  "
                  f"unsupported_claim_rate={s.unsupported_claim_rate:.3f}")
        print(f"\nfull report → {args.out}")
    else:
        print(dump)

    return 0


if __name__ == "__main__":
    sys.exit(main())
