#!/usr/bin/env python3
"""Research-extract strata and quote-entail letter-bootstrap (F-S 40, stored L1C).

Views only. Does not overwrite leo_paper_extras_fs40 or leo_quote_entail_fs40.
Does not flip D17 or the --quote-entail default. No GPU.

    venv-medcat/bin/python scripts/score_leo_extract_strata_fs.py
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from schema.claim import ReasonCode  # noqa: E402
from scripts import score_leo_quote_entail_fs as Q  # noqa: E402
from scripts import score_leo_vs_fs_gold as S  # noqa: E402
from scripts.score_llm_arms_vs_fs_gold import _load_fs_gold_for_doc  # noqa: E402
from services.quote_entail import quote_entails  # noqa: E402

TYPED = frozenset({"focal", "generalized", "combined_focal_generalized"})


def is_gold_unknown_convention(field_path: str, pred: Any, gold: dict) -> bool:
    """Fixed rule: typed epilepsy vs diagnosis-line gold unknown (D6)."""
    if field_path != "clinical_seizure.epilepsy_type":
        return False
    g = str(gold.get("epilepsy_type") or "").strip().lower()
    p = str(pred or "").strip().lower()
    return g == "unknown" and p in TYPED


def _ci(xs: list[float]) -> tuple[float, float]:
    xs = sorted(xs)
    return xs[int(0.025 * len(xs))], xs[min(len(xs) - 1, int(0.975 * len(xs)))]


def _fmt_ci(ci: tuple[float, float]) -> str:
    return f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def _ppv(ok: int, n: int) -> float | None:
    return (ok / n) if n else None


def _pool(pairs: list[tuple[int, int]], idx: list[int]) -> float | None:
    ok = n = 0
    for i in idx:
        o, c = pairs[i]
        ok += o
        n += c
    return _ppv(ok, n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", default="L1C=data/run_manifests_fs_test_flat_c:L1C")
    ap.add_argument("--out", default="eval/results/leo_extract_strata_fs40")
    ap.add_argument("--entail-out", default="eval/results/leo_quote_entail_bootstrap_fs40")
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    from services.chain_llm import ManifestLLMReasoner
    from services.chain_pipeline import ChainPipeline

    pids = S.HELD_OUT
    gold = {p: _load_fs_gold_for_doc(p) for p in pids}
    for g in gold.values():
        g["current_asms"] = [S.canon_drug(x) for x in g.get("current_asms") or []]
        st = g.get("predominant_seizure_type")
        g["predominant_seizure_type"] = S.GOLD_SEIZURE_TYPE_TO_ENUM.get(st, st)
    texts = {p: (S.FS_TEXT_DIR / f"{p}.txt").read_text(encoding="utf-8") for p in pids}

    label, mdir, arm = S.parse_llm(args.llm)
    reasoner = ManifestLLMReasoner([mdir], arm=arm)
    covered = [p for p in pids if reasoner.has(p)]

    base = ChainPipeline()
    base._lazy_init()
    cached = S._CachedAssembler(base._assembler)

    def make_pipe(entail: bool):
        pipe = ChainPipeline(extractor=base._extractor, assembler=cached,
                             candidate_service=base._candidate_service, llm_reasoner=reasoner)
        pipe.cfg.ground_llm_values = True
        pipe.cfg.quote_entail = entail
        return pipe

    def run(entail: bool):
        pipe = make_pipe(entail)
        per_doc = []
        all_pairs, conv_pairs, resid_pairs = [], [], []
        cells = []
        n_demoted = n_correct_demoted = 0
        for pid in covered:
            _, claims = pipe.extract(texts[pid], document_id=pid, return_claims=True)
            preds = S.native_from_claims(claims, {"accept"})
            per_doc.append(S.score_doc(preds, gold[pid]))
            a = c = r = ao = co = ro = 0
            for cl in claims:
                if any(rc.value == ReasonCode.QUOTE_NOT_ENTAILED.value for rc in cl.reason_codes):
                    n_demoted += 1
                    if S.claim_correct(cl, gold[pid]) is True:
                        n_correct_demoted += 1
                if not Q._is_research_extract(cl):
                    continue
                ok = S.claim_correct(cl, gold[pid])
                if ok is None:
                    continue
                pred = Q._pred_text(cl)
                conv = is_gold_unknown_convention(cl.field_path or "", pred, gold[pid])
                a += 1
                ao += int(ok)
                if conv:
                    c += 1
                    co += int(ok)
                else:
                    r += 1
                    ro += int(ok)
                cells.append({
                    "pid": pid,
                    "field": cl.field_path,
                    "pred": pred,
                    "gold": Q._gold_text(cl.field_path, gold[pid]),
                    "ok": bool(ok),
                    "bucket": "convention" if conv else "residual",
                    "quote_entails": quote_entails(
                        cl.field_path or "", cl.value, cl.mention.text, texts[pid]),
                    "quote": (cl.mention.text or "")[:240],
                })
            all_pairs.append((ao, a))
            conv_pairs.append((co, c))
            resid_pairs.append((ro, r))
        return {
            "per_doc": per_doc,
            "all": all_pairs,
            "convention": conv_pairs,
            "residual": resid_pairs,
            "cells": cells,
            "demoted": n_demoted,
            "correct_demoted": n_correct_demoted,
        }

    mdir_rel = str(Path(mdir).relative_to(REPO)) if Path(mdir).is_absolute() else str(mdir)

    off = run(False)
    on = run(True)
    idx_all = list(range(len(covered)))
    rng = random.Random(args.seed)

    def boot_ppv(pairs):
        xs = []
        for _ in range(args.bootstrap):
            idx = [rng.randrange(len(pairs)) for _ in range(len(pairs))]
            v = _pool(pairs, idx)
            if v is not None:
                xs.append(v)
        return {"mean": sum(xs) / len(xs), "ci": _ci(xs)}

    def boot_delta(a, b):
        xs = []
        for _ in range(args.bootstrap):
            idx = [rng.randrange(len(a)) for _ in range(len(a))]
            va, vb = _pool(a, idx), _pool(b, idx)
            if va is not None and vb is not None:
                xs.append(va - vb)
        return {"mean": sum(xs) / len(xs), "ci": _ci(xs),
                "p_le_0": sum(1 for x in xs if x <= 0) / len(xs)}

    auto_boot = S.bootstrap(
        {"auto_off": off["per_doc"], "auto_on": on["per_doc"]},
        [("auto_on", "auto_off")],
        n=args.bootstrap, seed=args.seed,
    )

    def pack_stratum(name, pairs):
        ok = sum(o for o, _ in pairs)
        n = sum(c for _, c in pairs)
        return {"name": name, "correct": ok, "scored": n, "precision": _ppv(ok, n),
                "bootstrap": boot_ppv(pairs)}

    strata_off = {k: pack_stratum(k, off[k]) for k in ("all", "convention", "residual")}
    strata_on = {k: pack_stratum(k, on[k]) for k in ("all", "convention", "residual")}
    delta_extract = {k: boot_delta(on[k], off[k]) for k in ("all", "convention", "residual")}

    auto_off = S.micro(off["per_doc"])
    auto_on = S.micro(on["per_doc"])
    misses_off = [c for c in off["cells"] if not c["ok"]]
    resid_miss = [c for c in misses_off if c["bucket"] == "residual"]
    conv_miss = [c for c in misses_off if c["bucket"] == "convention"]

    lo, hi = delta_extract["residual"]["ci"]
    decision = (
        "KEEP default off. Residual Δ extract-PPV CI includes 0 or the cost is "
        f"{on['correct_demoted']} gold-correct demotions. Exploratory on the same "
        "40 letters as 10.49; not a confirmatory flip."
        if lo <= 0 or on["correct_demoted"] > 0 else
        "Residual Δ extract-PPV lower bound > 0, but this is the same 40 as 10.49; "
        "default stays off until a confirmatory set."
    )

    report = {
        "arm": arm, "dir": mdir_rel, "n_letters": len(covered),
        "rule": "epilepsy_type gold==unknown and pred in {focal, generalized, combined}",
        "frozen_headline": "71/82 = 0.866 (leo_paper_extras_fs40; do not replace)",
        "strata_default": strata_off,
        "strata_quote_entail": strata_on,
        "auto_off": {"p": auto_off[0], "r": auto_off[1], "f1": auto_off[2]},
        "auto_on": {"p": auto_on[0], "r": auto_on[1], "f1": auto_on[2]},
        "paired_auto": {
            "delta_p": auto_boot["diff_p"]["auto_on-auto_off"],
            "delta_r": auto_boot["diff_r"]["auto_on-auto_off"],
            "delta_f1": auto_boot["diff"]["auto_on-auto_off"],
        },
        "paired_extract_ppv": delta_extract,
        "routing_entail_on": {
            "demoted": on["demoted"],
            "gold_correct_demoted": on["correct_demoted"],
        },
        "misses_default": misses_off,
        "decision": decision,
        "flip_default": False,
        "bootstrap": {"n": args.bootstrap, "seed": args.seed},
    }

    def row(name, s):
        p = s["precision"]
        return (f"| {name} | {s['correct']}/{s['scored']} | "
                f"{p:.3f} | {_fmt_ci(s['bootstrap']['ci'])} |")

    md = [
        "# Research-extract strata (F-S 40, L1C, no GPU)\n",
        "Views of the current-chain research extract (`accepted` ∧ both readers). "
        "**Frozen headline stays 71/82 = 0.866** (`leo_paper_extras_fs40`). "
        "Do not replace that number with these rows.\n",
        f"Letters: {len(covered)}. Arm {arm} from `{mdir_rel}`. "
        f"Letter-level bootstrap {args.bootstrap} draws, seed {args.seed}.\n",
        "Convention rule (fixed, not letter-by-letter): "
        "`epilepsy_type` and gold is `unknown` and pred is "
        "`focal` / `generalized` / `combined_focal_generalized` (D6).\n",
        "## Default chain (quote-entail off)\n",
        "| bucket | correct / scored | PPV | letter-bootstrap 95% CI |",
        "|---|---|---:|---|",
        row("All extract cells", strata_off["all"]),
        row("Gold-`unknown` convention", strata_off["convention"]),
        row("Residual (true shared mistakes)", strata_off["residual"]),
        "",
        f"Convention misses: {len(conv_miss)}. Residual misses: {len(resid_miss)}.\n",
        "### Residual misses\n",
        "| letter | field | pred | gold | quote entails? |",
        "|---|---|---|---|---|",
    ]
    for c in resid_miss:
        md.append(
            f"| {c['pid']} | `{c['field']}` | {c['pred']} | {c['gold']} | "
            f"{'yes' if c['quote_entails'] else '**no**'} |"
        )
    if not resid_miss:
        md.append("| — | — | — | — | — |")
    md += [
        "",
        "### Convention misses (typed vs gold `unknown`)\n",
        "| letter | pred | gold | quote entails? | quote |",
        "|---|---|---|---|---|",
    ]
    for c in conv_miss:
        q = (c["quote"] or "").replace("|", "/").replace("\n", " ")
        md.append(
            f"| {c['pid']} | {c['pred']} | {c['gold']} | "
            f"{'yes' if c['quote_entails'] else '**no**'} | {q} |"
        )
    md += [
        "",
        "Do not recode gold to match LEO. Do not train `unknown`. "
        "Do not write E from these rows.\n",
    ]

    entail_md = [
        "# Quote-entail letter-bootstrap (F-S 40, L1C, no GPU)\n",
        "Description of the 10.49 rematch. **Default stays off (D22).** "
        "Same 40 held-out letters already used in 10.49: this CI is not a "
        "confirmatory flip. Frozen extras / `leo_quote_entail_fs40` point estimates "
        "are not overwritten.\n",
        f"Letter-level bootstrap {args.bootstrap} draws, seed {args.seed}. "
        "Δ = `--quote-entail` minus default.\n",
        "## Auto-accept (field micro)\n",
        "| setting | P | R | F1 |",
        "|---|---:|---:|---:|",
        f"| default (off) | {auto_off[0]:.3f} | {auto_off[1]:.3f} | {auto_off[2]:.3f} |",
        f"| `--quote-entail` | {auto_on[0]:.3f} | {auto_on[1]:.3f} | {auto_on[2]:.3f} |",
        "",
        "| contrast | ΔP | ΔR | ΔF1 |",
        "|---|---|---|---|",
        (
            f"| entail − default | "
            f"{auto_boot['diff_p']['auto_on-auto_off']['mean']:+.3f} "
            f"{_fmt_ci(auto_boot['diff_p']['auto_on-auto_off']['ci'])} | "
            f"{auto_boot['diff_r']['auto_on-auto_off']['mean']:+.3f} "
            f"{_fmt_ci(auto_boot['diff_r']['auto_on-auto_off']['ci'])} | "
            f"{auto_boot['diff']['auto_on-auto_off']['mean']:+.3f} "
            f"{_fmt_ci(auto_boot['diff']['auto_on-auto_off']['ci'])} |"
        ),
        "",
        "## Research-extract PPV\n",
        "| bucket | default | entail on | Δ PPV (entail − default) |",
        "|---|---|---|---|",
    ]
    for k, label_k in (("all", "All extract cells"),
                       ("convention", "Gold-`unknown` convention"),
                       ("residual", "Residual")):
        a, b, d = strata_off[k], strata_on[k], delta_extract[k]
        entail_md.append(
            f"| {label_k} | {a['correct']}/{a['scored']} = {a['precision']:.3f} | "
            f"{b['correct']}/{b['scored']} = {b['precision']:.3f} | "
            f"{d['mean']:+.3f} {_fmt_ci(d['ci'])} |"
        )
    entail_md += [
        "",
        f"Demoted `quote_not_entailed`: {on['demoted']} "
        f"(of which {on['correct_demoted']} were gold-correct).\n",
        f"**Decision.** {decision} `flip_default` = false.\n",
        "The two residual extract misses on the default chain both pass the "
        "lexical entail check, so the flag does not catch true shared mistakes "
        "on this list. Precision on the mixed extract rises by dropping "
        "convention cells and gold-correct accepts.\n",
    ]

    def write_pair(stem: Path, markdown: str, payload: dict) -> None:
        stem = stem if stem.is_absolute() else REPO / stem
        stem.parent.mkdir(parents=True, exist_ok=True)
        Path(str(stem) + ".md").write_text(markdown, encoding="utf-8")
        Path(str(stem) + ".json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print("wrote", Path(str(stem) + ".md"))

    write_pair(Path(args.out), "\n".join(md), report)
    write_pair(Path(args.entail_out), "\n".join(entail_md), {
        "decision": decision, "flip_default": False,
        "paired_auto": report["paired_auto"],
        "paired_extract_ppv": delta_extract,
        "auto_off": report["auto_off"], "auto_on": report["auto_on"],
        "routing_entail_on": report["routing_entail_on"],
        "bootstrap": report["bootstrap"],
    })
    print("default extract", strata_off["all"]["correct"], "/", strata_off["all"]["scored"],
          "residual", strata_off["residual"]["correct"], "/", strata_off["residual"]["scored"])
    print("decision:", decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
