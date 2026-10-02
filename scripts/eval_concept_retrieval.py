#!/usr/bin/env python3
"""Measure ontology candidate retrieval: does the right concept appear in the top-k?

Gold = the Fonferko-Shadrach 2024 clinician-adjudicated annotations
(Zenodo 8356494).  Every ``Diagnosis``, ``Prescription`` and ``Investigations``
annotation there carries a UMLS CUI chosen by the annotators.  A mention is
the annotated text span; the gold concept is its CUI.

A retrieved candidate is a **hit** when it is that concept, i.e. when either
  * it is a UMLS candidate with the same CUI, or
  * its (system, code) is one of the codes the UMLS Metathesaurus lists under
    that CUI in HPO, SNOMED CT US or RxNorm (crosswalk fetched through the UTS
    REST API and cached in ``.cache/umls_api``).
MONDO and EPIO are not UMLS source vocabularies, so a MONDO/EPIO candidate
can never be scored a hit; mentions whose CUI has no HPO/SNOMED/RxNorm code
are reported as *unreachable* and excluded from the headline.

Outputs ``docs`` tables (markdown) and a JSON file under ``eval/results``.

    venv-medcat/bin/python scripts/eval_concept_retrieval.py            # needs UMLS_APIKEY + network on first run
    venv-medcat/bin/python scripts/eval_concept_retrieval.py --offline  # cache only

Independence caveat: ``references/exect_v2_cui_seed.csv`` (used by the
service for UMLS-system candidates) comes from the ExECT dictionaries, the
same resource the annotators used.  Hits are therefore reported in three
views: ``all`` candidates, ``release`` candidates only (HPO/SNOMED/RxNorm
from the pinned releases, independent of ExECT), and ``seed`` candidates.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

GOLD_DIR = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8356494" / "Json"
OUT_DIR = REPO / "eval" / "results"
SAB_TO_SYSTEM = {"SNOMEDCT_US": "SNOMED", "HPO": "HPO", "RXNORM": "RxNorm"}
HELD_OUT = {f"EA{i:04d}" for i in range(161, 201)}
KS = (1, 5, 10)


def load_gold() -> list[dict]:
    rows = []
    for f in sorted(GOLD_DIR.glob("*.json")):
        pid = f.stem
        for e in json.loads(f.read_text(encoding="utf-8")):
            a = e.get("attributes") or {}
            cui = (a.get("CUI") or "").strip()
            if e.get("entity") not in ("Diagnosis", "Prescription", "Investigations") or not re.fullmatch(r"C\d{7}", cui):
                continue
            text = (e.get("text") or "").replace("-", " ").strip()
            if not text:
                continue
            ent = e["entity"]
            cat = (a.get("DiagCategory") or "").lower()
            if ent == "Prescription":
                field = "medication.current_asms"
            elif ent == "Diagnosis" and cat == "epilepsy":
                field = "clinical_seizure.epilepsy_type"
            elif ent == "Diagnosis" and cat in ("multipleseizures", "singleseizure"):
                field = "clinical_seizure.predominant_seizure_type"
            else:
                field = None
            rows.append({"pid": pid, "heldout": pid in HELD_OUT, "entity": ent,
                         "diag_category": cat or None, "mention": text, "cui": cui,
                         "field_type": field})
    return rows


def crosswalk(cuis: set[str], offline: bool):
    """CUI -> ({(system, code)}, {atom names}) from UMLS atoms of HPO / SNOMED CT US / RxNorm."""
    from scripts.apply_curated_code_corrections import ATOM_SABS, CACHE, _apikey, _get
    out: dict[str, tuple[set[tuple[str, str]], set[str]]] = {}
    key = None
    for cui in sorted(cuis):
        p = CACHE / f"{cui}.json"
        if not p.exists():
            if offline:
                continue
            key = key or _apikey()
            j = _get(f"/content/current/CUI/{cui}/atoms",
                     {"sabs": ATOM_SABS, "language": "ENG", "pageSize": 200}, key)
            CACHE.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(j, indent=2), encoding="utf-8")
        atoms = json.loads(p.read_text(encoding="utf-8")).get("result") or []
        codes, names = set(), set()
        for a in atoms:
            sys_ = SAB_TO_SYSTEM.get(a.get("rootSource", ""))
            code = (a.get("code") or "").rsplit("/", 1)[-1]
            if sys_ and code and code != "NOCODE":
                codes.add((sys_, code))
                if a.get("name"):
                    names.add(a["name"].strip().lower())
        out[cui] = (codes, names)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="use the UMLS cache only")
    ap.add_argument("--out", default="eval/results/concept_retrieval")
    ap.add_argument("--match", choices=["strict", "lenient"], default="strict",
                    help="strict: candidate code must be a UMLS code of the gold CUI. "
                         "lenient: also credit a candidate whose label equals a UMLS atom name of the gold CUI "
                         "(same concept under a different but equivalent code, e.g. RxNorm valproate vs valproic acid).")
    ap.add_argument("--no-field-routing", action="store_true",
                    help="search all scopes (field_type=None) for every mention")
    args = ap.parse_args(argv)

    from services.ontology_candidates import OntologyCandidateService

    gold = load_gold()
    cuis = {g["cui"] for g in gold}
    xw = crosswalk(cuis, args.offline)
    print(f"gold mentions: {len(gold)}  distinct CUIs: {len(cuis)}  with crosswalk: "
          f"{sum(1 for c in cuis if xw.get(c, (set(),))[0])}", flush=True)

    svc = OntologyCandidateService()
    release_keys = set(svc._term_index)   # (system, id) of pinned-release terms

    def is_hit(c, cui) -> bool:
        codes, names = xw.get(cui, (set(), set()))
        if (c.system == "UMLS" and c.id == cui) or (c.system, c.id) in codes:
            return True
        return args.match == "lenient" and c.label.strip().lower() in names

    per: dict[str, dict] = defaultdict(lambda: {"n": 0, "unreachable": 0, "views": {
        v: {"hit": {k: 0 for k in KS}, "rr": 0.0} for v in ("all", "scorable", "release", "seed")}})
    misses: list[dict] = []

    def add(group: str, view: str, rank: int | None, reachable: bool):
        g = per[group]
        if view == "all":
            g["n"] += 1
            g["unreachable"] += (not reachable)
        if not reachable:
            return
        v = g["views"][view]
        if rank is not None:
            for k in KS:
                v["hit"][k] += rank <= k
            v["rr"] += 1.0 / rank

    for g in gold:
        reachable = bool(xw.get(g["cui"], (set(),))[0])
        cands = svc.get_candidates(g["mention"], None if args.no_field_routing else g["field_type"], k=10)
        views = {
            "all": cands,
            # MONDO/EPIO are not UMLS source vocabularies: a correct MONDO/EPIO candidate
            # cannot be scored a hit, yet can sit at rank 1 and push the scorable hit down.
            # "scorable" re-ranks without them so recall is not understated by that.
            "scorable": [c for c in cands if c.system in ("HPO", "SNOMED", "RxNorm", "UMLS")],
            "release": [c for c in cands if (c.system, c.id) in release_keys],
            "seed": [c for c in cands if (c.system, c.id) not in release_keys],
        }
        ranks = {}
        for name, cl in views.items():
            r = next((i for i, c in enumerate(cl, 1) if is_hit(c, g["cui"])), None)
            ranks[name] = r
        groups = ["ALL", f"entity:{g['entity']}", "split:heldout" if g["heldout"] else "split:train"]
        if g["field_type"]:
            groups.append(f"field:{g['field_type']}")
        for grp in groups:
            for name in views:
                add(grp, name, ranks[name], reachable)
        if reachable and ranks["all"] is None and len(misses) < 400:
            misses.append({"pid": g["pid"], "mention": g["mention"], "cui": g["cui"],
                           "entity": g["entity"], "gold_codes": sorted(f"{s}:{c}" for s, c in xw[g["cui"]][0])[:6],
                           "top": [f"{c.system}:{c.id}:{c.label}" for c in cands[:3]]})

    report = {"n_gold": len(gold), "n_cuis": len(cuis), "match": args.match,
              "routing": not args.no_field_routing, "groups": {}}
    for grp, g in sorted(per.items()):
        reach = g["n"] - g["unreachable"]
        row = {"n": g["n"], "reachable": reach}
        for view, v in g["views"].items():
            row[view] = {f"recall@{k}": (v["hit"][k] / reach if reach else None) for k in KS}
            row[view]["mrr@10"] = v["rr"] / reach if reach else None
        report["groups"][grp] = row
    report["miss_sample"] = misses[:60]
    report["miss_count_reachable"] = sum(1 for _ in misses)

    out = Path(args.out + ("" if args.match == "strict" else "_lenient"))
    out = out if out.is_absolute() else REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def f(x):
        return "-" if x is None else f"{x:.3f}"

    L = ["# Concept retrieval vs F-S clinician CUI gold", "",
         f"*`scripts/eval_concept_retrieval.py`. {len(gold)} annotated mentions, {len(cuis)} distinct CUIs; "
         f"field routing {'on' if not args.no_field_routing else 'off'}; match = {args.match}. Recall is over *reachable* mentions "
         "(the gold CUI has a code in HPO, SNOMED CT US or RxNorm).*", "",
         "| group | n | reachable | R@1 | R@5 | R@10 | MRR@10 | scorable R@1 | R@5 | R@10 | release-only R@5 | seed-only R@10 |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for grp, r in report["groups"].items():
        a, sc, rel, sd = r["all"], r["scorable"], r["release"], r["seed"]
        L.append(f"| {grp} | {r['n']} | {r['reachable']} | {f(a['recall@1'])} | {f(a['recall@5'])} | "
                 f"{f(a['recall@10'])} | {f(a['mrr@10'])} | {f(sc['recall@1'])} | {f(sc['recall@5'])} | "
                 f"{f(sc['recall@10'])} | {f(rel['recall@5'])} | {f(sd['recall@10'])} |")
    L += ["", "## Sample of reachable mentions with no hit in the top 10", "",
          "| letter | mention | gold CUI | gold codes | top-3 returned |", "|---|---|---|---|---|"]
    for m in report["miss_sample"][:40]:
        L.append(f"| {m['pid']} | {m['mention']} | {m['cui']} | {', '.join(m['gold_codes'][:3])} | "
                 f"{'; '.join(m['top'][:3])} |")
    out.with_suffix(".md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:16]))
    print(f"\nwrote {out.with_suffix('.json')} and {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
