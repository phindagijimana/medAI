#!/usr/bin/env python3
"""Why do LLM evidence quotes fail the verbatim check?

For every populated field of a replayed Med42 phenotype, test whether its
``evidence_text`` is found in the note (``locate_quote``) and classify failures:

  empty        no quote at all
  value_only   quote is just the value / a short token not in the note as written
  paraphrase   quote words mostly present in the note but not in that order
  partial      the quote has a long verbatim run (>= 60% of its tokens) in the note
  fabricated   little overlap with the note

Usage:
    venv-medcat/bin/python scripts/diag_llm_quotes.py data/run_manifests_fs_test_ft_v3_polish:FT
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from services.chain_llm import ManifestLLMReasoner, flatten, locate_quote  # noqa: E402
import score_leo_vs_fs_gold as S  # noqa: E402


def norm_tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def classify(quote: str, text: str) -> tuple[str, float]:
    q = norm_tokens(quote)
    if not q:
        return "empty", 0.0
    t = norm_tokens(text)
    tset = set(t)
    cover = sum(w in tset for w in q) / len(q)
    sm = SequenceMatcher(None, q, t, autojunk=False)
    longest = sm.find_longest_match(0, len(q), 0, len(t)).size / len(q)
    if longest >= 0.6:
        return "partial", longest
    if cover >= 0.8:
        return "paraphrase", cover
    if len(q) <= 3:
        return "value_only", cover
    return "fabricated", cover


def main() -> int:
    spec = sys.argv[1] if len(sys.argv) > 1 else "data/run_manifests_fs_test_ft_v3_polish:FT"
    mdir, arm = spec.rsplit(":", 1)
    reasoner = ManifestLLMReasoner([mdir], arm=arm)
    by_field = defaultdict(Counter)
    samples = defaultdict(list)
    for pid in S.HELD_OUT:
        if not reasoner.has(pid):
            continue
        text = (S.FS_TEXT_DIR / f"{pid}.txt").read_text(encoding="utf-8")
        pheno = reasoner(text, pid, "2024-01-01")
        for it in flatten(pheno):
            q = (it.ev.get("evidence_text") or "").strip()
            if locate_quote(q, text):
                kind = "verbatim"
            else:
                kind, _ = classify(q, text)
                if len(samples[kind]) < 6:
                    samples[kind].append((pid, it.field_path, str(it.ev.get("value"))[:60], q[:140]))
            by_field[it.field_path][kind] += 1
    kinds = ["verbatim", "partial", "paraphrase", "value_only", "fabricated", "empty"]
    print(f"{'field':52s} " + " ".join(f"{k[:10]:>10s}" for k in kinds) + "   n")
    tot = Counter()
    for f, c in sorted(by_field.items()):
        n = sum(c.values())
        tot.update(c)
        print(f"{f:52s} " + " ".join(f"{c[k]:10d}" for k in kinds) + f" {n:4d}")
    n = sum(tot.values())
    print(f"{'ALL':52s} " + " ".join(f"{tot[k]:10d}" for k in kinds) + f" {n:4d}")
    for k, rows in samples.items():
        print(f"\n--- {k} ---")
        for r in rows:
            print(" ", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
