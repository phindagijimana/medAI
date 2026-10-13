#!/usr/bin/env python3
"""Error capture and false-alarm rates for LEO vs the model alone. F-S letters; no GPU.

INTERPRETING_RESULTS.md §5: of the values where the model alone is wrong against the
reference, the fraction LEO routes to review/reject (captured) vs accept (missed);
and the fraction of LEO-flagged values that were already right (false alarms).

A scored *value* is one of the seven headline fields on one letter that has gold.
The model is wrong when score_doc reports fp+fn > 0. LEO's routing for that field
uses claims on the matching path (ACCEPT / REVIEW / REJECT / silent).

    venv-medcat/bin/python scripts/score_leo_error_capture.py \\
        --llm L1C=data/run_manifests_fs_test_flat_c:L1C \\
        --out eval/results/leo_error_capture_fs40
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts import score_leo_vs_fs_gold as S  # noqa: E402
from scripts.score_llm_arms_vs_fs_gold import _load_fs_gold_for_doc  # noqa: E402

FIELD_PATH = {
    "current_asms": "medication.current_asms",
    "seizure_frequency.period": "clinical_seizure.seizure_frequency",
    "seizure_frequency.count_min": "clinical_seizure.seizure_frequency",
    "seizure_frequency.count_max": "clinical_seizure.seizure_frequency",
    "epilepsy_type": "clinical_seizure.epilepsy_type",
    "predominant_seizure_type": "clinical_seizure.predominant_seizure_type",
    "age_at_onset_years": "clinical_seizure.age_at_onset_years",
}


def _field_val(pred: dict, field: str):
    if field == "current_asms":
        return pred.get("current_asms")
    if field.startswith("seizure_frequency."):
        return pred.get(field)
    return pred.get(field)


def _gold_val(gold: dict, field: str):
    if field == "current_asms":
        return gold.get("current_asms")
    if field == "seizure_frequency.period":
        return gold.get("seizure_period")
    if field == "seizure_frequency.count_min":
        return gold.get("seizure_count_min")
    if field == "seizure_frequency.count_max":
        return gold.get("seizure_count_max")
    return gold.get(field)


def _leak_row(pid, field, llm_pred, acc, gold, claims) -> dict:
    path = FIELD_PATH[field]
    quotes = []
    for c in claims:
        fp = c.field_path
        if field == "current_asms":
            if not S._is_current_path(fp):
                continue
        elif fp != path:
            continue
        if c.validator_verdict.value != "accept":
            continue
        quotes.append({
            "value": c.value,
            "quote": (c.mention.text if c.mention else None),
            "source": "+".join(c.detectors or []),
        })
    return {
        "letter": pid,
        "field": field,
        "llm": _field_val(llm_pred, field),
        "leo_accept": _field_val(acc, field),
        "gold": _gold_val(gold, field),
        "accepted_claims": quotes,
        "note": ("gold unknown is a diagnosis-line convention — do not train unknown "
                 if field == "epilepsy_type" and _gold_val(gold, field) == "unknown"
                 else "list only; do not write a fusion rule from this hold-out row"),
    }


def _route(claims, field: str) -> str:
    path = FIELD_PATH[field]
    vs = []
    for c in claims:
        fp = c.field_path
        if field == "current_asms":
            if not S._is_current_path(fp):
                continue
        elif fp != path:
            continue
        vs.append(c.validator_verdict.value)
    if "accept" in vs:
        return "accept"
    if "review" in vs:
        return "review"
    if "reject" in vs:
        return "reject"
    return "silent"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", action="append", required=True)
    ap.add_argument("--pids", default="")
    ap.add_argument("--out", default="eval/results/leo_error_capture")
    args = ap.parse_args()

    from services.chain_llm import ManifestLLMReasoner
    from services.chain_pipeline import ChainPipeline

    pids = [p for p in args.pids.split(",") if p] or S.HELD_OUT
    gold = {p: _load_fs_gold_for_doc(p) for p in pids}
    for g in gold.values():
        g["current_asms"] = [S.canon_drug(x) for x in g.get("current_asms") or []]
        st = g.get("predominant_seizure_type")
        g["predominant_seizure_type"] = S.GOLD_SEIZURE_TYPE_TO_ENUM.get(st, st)
    texts = {p: (S.FS_TEXT_DIR / f"{p}.txt").read_text(encoding="utf-8") for p in pids}

    base = ChainPipeline()
    base._lazy_init()
    cached = S._CachedAssembler(base._assembler)

    report = {"pids": pids, "fields": S.FIELDS, "sources": {}}
    for spec in args.llm:
        label, mdir, arm = S.parse_llm(spec)
        reasoner = ManifestLLMReasoner([mdir], arm=arm)
        pipe = ChainPipeline(extractor=base._extractor, assembler=cached,
                             candidate_service=base._candidate_service, llm_reasoner=reasoner)
        pipe.cfg.ground_llm_values = True
        covered = [p for p in pids if reasoner.has(p)]
        by_field = {f: Counter() for f in S.FIELDS}
        tot = Counter()
        leaks = []
        for pid in covered:
            _, claims = pipe.extract(texts[pid], document_id=pid, return_claims=True)
            llm_pred = S.native_from_module_dicts(reasoner(texts[pid], pid, "2024-01-01"))
            acc = S.native_from_claims(claims, {"accept"})
            sc = S.score_doc(llm_pred, gold[pid])
            for field in S.FIELDS:
                if field not in sc:
                    continue
                tp, fp, fn = sc[field]
                llm_wrong = (fp + fn) > 0
                llm_right = tp > 0 and fp == 0 and fn == 0
                route = _route(claims, field)
                row = by_field[field]
                row["scored"] += 1
                tot["scored"] += 1
                if llm_wrong:
                    row["llm_wrong"] += 1
                    tot["llm_wrong"] += 1
                    if route == "accept":
                        row["wrong_accepted"] += 1
                        tot["wrong_accepted"] += 1
                        leaks.append(_leak_row(pid, field, llm_pred, acc, gold[pid], claims))
                    else:
                        row["wrong_captured"] += 1
                        tot["wrong_captured"] += 1
                        row[f"wrong_{route}"] += 1
                        tot[f"wrong_{route}"] += 1
                if llm_right:
                    row["llm_right"] += 1
                    tot["llm_right"] += 1
                    if route == "review":
                        row["right_flagged"] += 1
                        tot["right_flagged"] += 1
                if route == "review":
                    row["flagged"] += 1
                    tot["flagged"] += 1
                    if llm_right:
                        row["flag_was_right"] += 1
                        tot["flag_was_right"] += 1
                    elif llm_wrong:
                        row["flag_was_wrong"] += 1
                        tot["flag_was_wrong"] += 1

        def pack(c: Counter) -> dict:
            w, r, fl = c["llm_wrong"], c["llm_right"], c["flagged"]
            return {
                **{k: int(c[k]) for k in ("scored", "llm_wrong", "llm_right", "wrong_accepted",
                                          "wrong_captured", "wrong_review", "wrong_reject",
                                          "wrong_silent", "right_flagged", "flagged",
                                          "flag_was_right", "flag_was_wrong")},
                "capture_rate": (c["wrong_captured"] / w) if w else None,
                "missed_accept_rate": (c["wrong_accepted"] / w) if w else None,
                "false_alarm_among_right": (c["right_flagged"] / r) if r else None,
                "flag_already_right": (c["flag_was_right"] / fl) if fl else None,
            }

        block = {"arm": arm, "n_letters": len(covered), "overall": pack(tot),
                 "by_field": {f: pack(by_field[f]) for f in S.FIELDS},
                 "leaks": leaks}
        report["sources"][label] = block
        o = block["overall"]
        print(f"\n=== {label} ({arm}) {len(covered)} letters ===")
        print(f"  LLM wrong: {o['llm_wrong']}  captured (not accepted): {o['wrong_captured']} "
              f"({o['capture_rate']})  accepted anyway: {o['wrong_accepted']} ({o['missed_accept_rate']})")
        print(f"  flagged: {o['flagged']}  already right: {o['flag_was_right']} ({o['flag_already_right']})")

    out = Path(args.out)
    out = out if out.is_absolute() else REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def fmt(x):
        return "—" if x is None else f"{x:.2f}"

    md = ["# LEO error capture (F-S held-out letters; model errors vs fusion routing)\n",
          "A value is one of the seven headline fields on one letter with gold. "
          "The model is wrong when `score_doc` reports fp+fn > 0. Captured = LEO did not auto-accept "
          "(review, reject, or silent). False alarm among flags = flagged values that were already right.\n"]
    for label, b in report["sources"].items():
        o = b["overall"]
        md += [f"## {label} (arm {b['arm']}, {b['n_letters']} letters)\n",
               f"- Model-wrong values: **{o['llm_wrong']}** of {o['scored']} scored.",
               f"- Captured (not accepted): **{o['wrong_captured']}** ({fmt(o['capture_rate'])}); "
               f"of those, review {o['wrong_review']}, reject {o['wrong_reject']}, silent {o['wrong_silent']}.",
               f"- Model errors LEO auto-accepted: **{o['wrong_accepted']}** ({fmt(o['missed_accept_rate'])}).",
               f"- Flagged values that were already right: **{o['flag_was_right']}** of {o['flagged']} "
               f"({fmt(o['flag_already_right'])}).",
               "",
               "| field | scored | LLM wrong | captured | accepted anyway | flagged | flag already right |",
               "|---|---:|---:|---:|---:|---:|---:|"]
        for f, row in b["by_field"].items():
            md.append(f"| `{f}` | {row['scored']} | {row['llm_wrong']} | {row['wrong_captured']} | "
                      f"{row['wrong_accepted']} | {row['flagged']} | {row['flag_was_right']} |")
        md.append("")
        leaks = b.get("leaks") or []
        md += [
            "### Accepted model-wrong cells (the leak)",
            "",
            "Hold-out list only. **Do not write E/fusion rules from these rows.** "
            "Eight epilepsy-type rows are typed vs gold `unknown` (convention, not a broken reader). "
            "ASM / frequency rows are the extract holes to fix on EA0001–160.",
            "",
            "| letter | field | gold | leo accept | llm | source |",
            "|---|---|---|---|---|---|",
        ]
        for row in leaks:
            src = ",".join(sorted({q["source"] for q in row.get("accepted_claims") or []} or ["?"]))
            md.append(
                f"| {row['letter']} | `{row['field']}` | {row['gold']!r} | "
                f"{row['leo_accept']!r} | {row['llm']!r} | {src} |"
            )
        md.append("")
    out.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    print("wrote", out.with_suffix(".json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
