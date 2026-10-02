#!/usr/bin/env python3
"""Score LEO (LLM + EpExtra + Ontology) against Fonferko-Shadrach native gold.

Uses the *same* gold, fields and primitives as
``scripts/score_llm_arms_vs_fs_gold.py`` so the LEO rows sit in the same
table as the Med42 arms (M0-M3, Arm H).  Seven fields: ``current_asms``
(multiset), seizure-frequency ``period`` / ``count_min`` / ``count_max``,
``epilepsy_type``, ``predominant_seizure_type``, ``age_at_onset_years``.

For each LLM source (a directory of Med42 run manifests plus an arm) the
script evaluates four systems on the letters that source covers:

    llm          Med42-8B alone (smart-repaired, as in the arm table)
    specialist   EpExtra alone (B1', run through the LEO claim path)
    leo_auto     LEO claims routed ACCEPT (what is trusted with no human)
    leo_review   LEO claims routed ACCEPT or REVIEW (what a reviewer sees)

plus paired bootstrap differences (resampling letters), claim-level
precision by detector agreement, and the safety counters the paper
reports (review rate, unsupported LLM claims, ontology-grounded rate).

Run (needs medcat, hence venv-medcat; no GPU)::

    venv-medcat/bin/python scripts/score_leo_vs_fs_gold.py \\
        --llm base_M2=data/run_manifests_fs_test_base:M2 \\
        --llm armH_M2=data/run_manifests_fs_test_tuned_v3_polish:M2 \\
        --out eval/results/leo_vs_fs_gold
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from enum import Enum
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.score_llm_arms_vs_fs_gold import (  # noqa: E402
    _f1, _load_fs_gold_for_doc, _pred_current_asms, _pred_ev_value,
    _pred_seizfreq, _score_multiset, _score_scalar,
)

FS_GOLD_DIR = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8356494" / "Json"
FS_TEXT_DIR = (REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8381080"
               / "Gold1-200_corrected_spelling")

# Held-out test split: EA0161..EA0200 (scripts/finetune_lora_epi.py,
# _fs_pairs_train_test(seed=0); same contract as score_medcat_vs_gold.py).
HELD_OUT = [f"EA{i:04d}" for i in range(161, 201)]

FIELDS = ["current_asms", "seizure_frequency.period", "seizure_frequency.count_min",
          "seizure_frequency.count_max", "epilepsy_type",
          "predominant_seizure_type", "age_at_onset_years"]
SYSTEMS = ["llm", "specialist", "leo_auto", "leo_review"]
# Extra views of epilepsy_type, reported but NOT part of the micro-F1 (amendment D5):
#   typed    only letters whose gold type is not "unknown"; a predicted "unknown" counts as no claim
#   abstain  a missing prediction counts as "unknown"
# Why: the gold type is a keyword rule over the diagnosis text and defaults to "unknown" when the
# text names no type (plain "epilepsy"): 25 of 38 held-out letters.  The base-model prompt has no
# "unknown" value, so the native view caps every LLM arm.
EXTRA_FIELDS = ["epilepsy_type|typed", "epilepsy_type|abstain"]


# The arm scorer's gold normaliser emits three seizure-type labels that are not
# in the schema enum (``SeizureType``), so no schema-conformant system could
# ever match them.  Map them onto the enum here (finding F4 in
# docs/EVAL_PROTOCOL_LEO.md).  This is a deliberate deviation from
# score_llm_arms_vs_fs_gold.py and applies to every system alike.
GOLD_SEIZURE_TYPE_TO_ENUM = {
    "absence_typical": "generalized_absence_typical",
    "myoclonic": "generalized_myoclonic",
    "atonic": "generalized_atonic",
}

# Synthetic-corpus scorer (scripts/score_leo_vs_synth_gold.py) sets this True: its gold writes
# "seizure-free" as count 0, so a prediction ``seizure_free=True`` with no counts reads as count 0.
# The F-S scorer leaves it False, so its numbers are unchanged.
SEIZURE_FREE_AS_ZERO = False
# Does an as-needed rescue drug (claims at medication.rescue_medication) count as a current ASM?
# F-S gold (ExECT guideline): yes.  Synthetic gold: no (maintenance regimen only).  See
# docs/SCOPE_DECISIONS.md D6.  Acute administrations never count.
RESCUE_FIELD_PATH = "medication.rescue_medication"
RESCUE_AS_CURRENT = True


def _is_current_path(fp) -> bool:
    return fp == "medication.current_asms" or (RESCUE_AS_CURRENT and fp == RESCUE_FIELD_PATH)


def _freq_counts(val: dict) -> tuple:
    cmin, cmax = val.get("count_min"), val.get("count_max")
    if SEIZURE_FREE_AS_ZERO and val.get("seizure_free") is True and cmin is None and cmax is None:
        return 0.0, 0.0
    return cmin, cmax


# ─── Prediction builders ─────────────────────────────────────────────────

def canon_drug(name: str) -> str:
    """Drug-name key used by the F-S gold (rules.fields.medication).

    Applied to gold, LLM and EpExtra alike so that "sodium valproate" and
    "valproate" are the same drug for every system.  This is slightly more
    lenient to the LLM than the arm table (which compares raw strings), so
    LLM-alone numbers here can differ from the published arm table.
    """
    from rules.fields.medication import canonicalize_drug_name
    return canonicalize_drug_name(name or "")


def _plain(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


# scored-field name -> claim field_path (the fusion policy is keyed by claim path)
_CLAIM_PATH = {
    "epilepsy_type": "clinical_seizure.epilepsy_type",
    "predominant_seizure_type": "clinical_seizure.predominant_seizure_type",
    "age_at_onset_years": "clinical_seizure.age_at_onset_years",
    "seizure_frequency.period": "clinical_seizure.seizure_frequency",
    "seizure_frequency.count_min": "clinical_seizure.seizure_frequency",
    "seizure_frequency.count_max": "clinical_seizure.seizure_frequency",
}


def native_from_module_dicts(pheno: Optional[dict]) -> dict:
    """LLM-alone prediction, extracted exactly as the arm scorer does."""
    cs = (pheno or {}).get("clinical_seizure") or {}
    med = (pheno or {}).get("medication") or {}
    sf = _pred_seizfreq(cs) if cs else {"period": None, "count_min": None, "count_max": None}
    if SEIZURE_FREE_AS_ZERO and cs:
        v = (cs.get("seizure_frequency") or {}).get("value")
        if isinstance(v, dict) and v.get("seizure_free") is True and sf["count_min"] is None \
                and sf["count_max"] is None:
            sf = dict(sf, count_min=0.0, count_max=0.0)
    return {
        "current_asms": [canon_drug(x) for x in _pred_current_asms(med)] if med else [],
        "seizure_frequency.period": None if sf["period"] == "unspecified" else sf["period"],
        "seizure_frequency.count_min": sf["count_min"],
        "seizure_frequency.count_max": sf["count_max"],
        "epilepsy_type": _pred_ev_value(cs, "epilepsy_type") if cs else None,
        "predominant_seizure_type": _pred_ev_value(cs, "predominant_seizure_type") if cs else None,
        "age_at_onset_years": _pred_ev_value(cs, "age_at_onset_years") if cs else None,
    }


def native_from_claims(claims: list, verdicts: set[str],
                       require_detector: Optional[str] = None) -> dict:
    """Project claims onto the seven scored fields.

    ``verdicts`` selects which routing outcomes count as a prediction.
    ``require_detector='epextra'`` restricts to claims the specialist made
    (the specialist-alone system).  For scalar fields the first claim in
    priority order ACCEPT > REVIEW wins.
    """
    out: dict = {k: None for k in FIELDS}
    out["current_asms"] = []
    rank = {"accept": 0, "review": 1}
    picked: dict[str, tuple[int, Any]] = {}
    for c in claims:
        v = c.validator_verdict.value
        if v not in verdicts or c.field_path is None:
            continue
        if require_detector and require_detector not in c.detectors:
            continue
        val = _plain(c.value)
        fp = c.field_path
        if _is_current_path(fp):
            name = (val or {}).get("generic_name") if isinstance(val, dict) else None
            if name:
                out["current_asms"].append(canon_drug(str(name)))
        elif fp == "clinical_seizure.seizure_frequency" and isinstance(val, dict):
            cmin, cmax = _freq_counts(val)
            cand = {
                "seizure_frequency.period": (str(val.get("period")).lower()
                                             if val.get("period") not in (None, "unspecified") else None),
                "seizure_frequency.count_min": cmin,
                "seizure_frequency.count_max": cmax,
            }
            if "seizure_frequency" not in picked or rank[v] < picked["seizure_frequency"][0]:
                picked["seizure_frequency"] = (rank[v], cand)
        elif fp in ("clinical_seizure.epilepsy_type", "clinical_seizure.predominant_seizure_type",
                    "clinical_seizure.age_at_onset_years"):
            key = fp.split(".", 1)[1]
            if key not in picked or rank[v] < picked[key][0]:
                picked[key] = (rank[v], val)
    for key in ("epilepsy_type", "predominant_seizure_type", "age_at_onset_years"):
        if key in picked:
            out[key] = picked[key][1]
    if "seizure_frequency" in picked:
        out.update(picked["seizure_frequency"][1])
    return out


# ─── Scoring ─────────────────────────────────────────────────────────────

def score_doc(pred: dict, gold: dict) -> dict[str, tuple[int, int, int]]:
    """{field: (tp, fp, fn)} for one letter; fields without gold are absent."""
    res: dict[str, tuple[int, int, int]] = {}

    def put(name: str, s):
        if s is not None:
            res[name] = (s[0], s[1], s[2])

    put("current_asms", _score_multiset(pred.get("current_asms"), gold.get("current_asms")))
    put("seizure_frequency.period",
        _score_scalar(pred.get("seizure_frequency.period"), gold.get("seizure_period")))
    put("seizure_frequency.count_min",
        _score_scalar(pred.get("seizure_frequency.count_min"), gold.get("seizure_count_min"), tolerance=0))
    put("seizure_frequency.count_max",
        _score_scalar(pred.get("seizure_frequency.count_max"), gold.get("seizure_count_max"), tolerance=0))
    put("epilepsy_type", _score_scalar(pred.get("epilepsy_type"), gold.get("epilepsy_type")))
    put("predominant_seizure_type",
        _score_scalar(pred.get("predominant_seizure_type"), gold.get("predominant_seizure_type")))
    g_et, p_et = gold.get("epilepsy_type"), pred.get("epilepsy_type")
    if g_et is not None:
        put("epilepsy_type|abstain", _score_scalar(p_et if p_et is not None else "unknown", g_et))
        if g_et != "unknown":
            put("epilepsy_type|typed", _score_scalar(None if p_et == "unknown" else p_et, g_et))
    put("age_at_onset_years",
        _score_scalar(pred.get("age_at_onset_years"), gold.get("age_at_onset_years"), tolerance=1.0))
    return res


def micro(per_doc: list[dict[str, tuple[int, int, int]]], idx: Optional[list[int]] = None):
    idx = range(len(per_doc)) if idx is None else idx
    tp = fp = fn = 0
    for i in idx:
        for k, (t, f, n) in per_doc[i].items():
            if k in FIELDS:
                tp += t; fp += f; fn += n
    return _f1(tp, fp, fn)


def per_field(per_doc):
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for d in per_doc:
        for k, (t, f, n) in d.items():
            a = agg[k]; a[0] += t; a[1] += f; a[2] += n; a[3] += 1
    out = {}
    for k in FIELDS + EXTRA_FIELDS:
        if k in agg:
            t, f, n, docs = agg[k]
            p, r, f1 = _f1(t, f, n)
            out[k] = {"n": docs, "tp": t, "fp": f, "fn": n, "p": p, "r": r, "f1": f1}
    return out


def bootstrap(per_doc_by_sys: dict[str, list], pairs: list[tuple[str, str]],
              n: int = 2000, seed: int = 0) -> dict:
    """Doc-level bootstrap: CI per system micro-F1 and paired differences."""
    rng = random.Random(seed)
    m = len(next(iter(per_doc_by_sys.values())))
    f1s = {s: [] for s in per_doc_by_sys}
    diffs = {p: [] for p in pairs}
    for _ in range(n):
        idx = [rng.randrange(m) for _ in range(m)]
        cur = {s: micro(pd, idx)[2] for s, pd in per_doc_by_sys.items()}
        for s, v in cur.items():
            f1s[s].append(v)
        for a, b in pairs:
            diffs[(a, b)].append(cur[a] - cur[b])

    def ci(xs):
        xs = sorted(xs)
        return xs[int(0.025 * len(xs))], xs[min(len(xs) - 1, int(0.975 * len(xs)))]

    return {
        "f1_ci": {s: ci(v) for s, v in f1s.items()},
        "diff": {f"{a}-{b}": {"mean": sum(v) / len(v), "ci": ci(v),
                              "p_le_0": sum(1 for x in v if x <= 0) / len(v)}
                 for (a, b), v in diffs.items()},
    }


# ─── Claim-level precision by detector agreement ─────────────────────────

def claim_correct(claim, gold: dict) -> Optional[bool]:
    """Is one claim right? None when the gold has no reference for its field."""
    fp = claim.field_path
    val = _plain(claim.value)
    if _is_current_path(fp):
        g = gold.get("current_asms") or []
        if not g:
            return None
        name = (val or {}).get("generic_name") if isinstance(val, dict) else None
        return bool(name) and canon_drug(str(name)) in {canon_drug(x) for x in g}
    if fp == "clinical_seizure.epilepsy_type":
        g = gold.get("epilepsy_type")
        return None if g is None else str(val).strip().lower() == str(g).lower()
    if fp == "clinical_seizure.predominant_seizure_type":
        g = gold.get("predominant_seizure_type")
        return None if g is None else str(val).strip().lower() == str(g).lower()
    if fp == "clinical_seizure.age_at_onset_years":
        g = gold.get("age_at_onset_years")
        try:
            return None if g is None else abs(float(val) - float(g)) <= 1.0
        except (TypeError, ValueError):
            return False
    if fp == "clinical_seizure.seizure_frequency" and isinstance(val, dict):
        checks = []
        per = val.get("period")
        if gold.get("seizure_period") is not None:
            checks.append(str(per).lower() == gold["seizure_period"])
        cmin, cmax = _freq_counts(val)
        for v, gk in ((cmin, "seizure_count_min"), (cmax, "seizure_count_max")):
            if gold.get(gk) is not None:
                checks.append(v is not None and float(v) == float(gold[gk]))
        return None if not checks else all(checks)
    return None


def claim_bootstrap(claims_all, gold: dict, n: int = 2000, seed: int = 0) -> dict:
    """Letter-level bootstrap of claim precision by category, and of agree minus each other category."""
    per_letter: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for pid, c in claims_all:
        ok = claim_correct(c, gold[pid])
        if ok is not None:
            cell = per_letter[pid][claim_category(c)]
            cell[0] += int(ok); cell[1] += 1
    pids = sorted(per_letter)
    cats = ["agree", "disagree", "llm_only", "specialist_only"]
    rng = random.Random(seed)
    prec: dict[str, list[float]] = {c: [] for c in cats}
    diff: dict[str, list[float]] = {f"agree-{c}": [] for c in cats if c != "agree"}
    for _ in range(n):
        tot = {c: [0, 0] for c in cats}
        for _i in range(len(pids)):
            lt = per_letter[pids[rng.randrange(len(pids))]]
            for c in cats:
                if c in lt:
                    tot[c][0] += lt[c][0]; tot[c][1] += lt[c][1]
        p = {c: (tot[c][0] / tot[c][1] if tot[c][1] else None) for c in cats}
        for c in cats:
            if p[c] is not None:
                prec[c].append(p[c])
        for c in cats:
            if c != "agree" and p["agree"] is not None and p[c] is not None:
                diff[f"agree-{c}"].append(p["agree"] - p[c])

    def ci(xs):
        xs = sorted(xs)
        return None if len(xs) < 50 else (xs[int(0.025 * len(xs))], xs[min(len(xs) - 1, int(0.975 * len(xs)))])
    return {"precision": {c: ci(v) for c, v in prec.items()},
            "agree_minus": {k: {"ci": ci(v), "mean": (sum(v) / len(v) if v else None)} for k, v in diff.items()}}


def claim_category(claim) -> str:
    d = set(claim.detectors)
    if d == {"llm"}:
        return "llm_only"
    if "llm" in d:
        return "agree"
    if any(r.value == "source_disagreement" for r in claim.reason_codes):
        return "disagree"
    return "specialist_only"


# ─── Main ────────────────────────────────────────────────────────────────

def parse_llm(spec: str):
    label, rest = spec.split("=", 1)
    path, arm = rest.rsplit(":", 1)
    return label, (REPO / path if not Path(path).is_absolute() else Path(path)), arm


class _CachedAssembler:
    """Run the specialist once per note; reused across LLM sources."""

    def __init__(self, inner):
        self._inner = inner
        self._cache: dict = {}

    def process(self, text, **kw):
        key = (hash(text), kw.get("doc_id"))
        if key not in self._cache:
            self._cache[key] = self._inner.process(text, **kw)
        return self._cache[key]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", action="append", required=True,
                    help="label=manifest_dir:ARM (repeatable)")
    ap.add_argument("--out", default="eval/results/leo_vs_fs_gold")
    ap.add_argument("--pids", default="", help="comma list; default = 40 held-out letters")
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--disagree-llm", default="",
                    help="comma list of field paths where the LLM value wins a scalar disagreement "
                         "(policy chosen on development letters only)")
    ap.add_argument("--maintenance-only", action="store_true",
                    help="rescue drugs do not count as current ASMs (default: they do, as in the F-S gold)")
    ap.add_argument("--no-ground", action="store_true",
                    help="do not locate spans for LLM-only values (reproduces the leo-v0.2 numbers)")
    args = ap.parse_args(argv)
    global RESCUE_AS_CURRENT
    if args.maintenance_only:
        RESCUE_AS_CURRENT = False

    from services.chain_llm import ManifestLLMReasoner
    from services.chain_pipeline import ChainPipeline

    pids = [p for p in args.pids.split(",") if p] or HELD_OUT
    gold = {p: _load_fs_gold_for_doc(p) for p in pids}
    for g in gold.values():
        g["current_asms"] = [canon_drug(x) for x in g.get("current_asms") or []]
        st = g.get("predominant_seizure_type")
        g["predominant_seizure_type"] = GOLD_SEIZURE_TYPE_TO_ENUM.get(st, st)
    texts = {p: (FS_TEXT_DIR / f"{p}.txt").read_text(encoding="utf-8") for p in pids}

    base = ChainPipeline()
    base._lazy_init()
    cached = _CachedAssembler(base._assembler)

    # Specialist-alone claims come from a run with no LLM channel, so no fusion policy can change them.
    pipe0 = ChainPipeline(extractor=base._extractor, assembler=cached,
                          candidate_service=base._candidate_service, llm_reasoner=None)
    spec_claims = {pid: pipe0.extract(texts[pid], document_id=pid, return_claims=True)[1] for pid in pids}

    report: dict = {"pids": pids, "rescue_as_current": RESCUE_AS_CURRENT, "sources": {}}
    per_doc_by_label: dict[str, tuple[list[str], dict]] = {}
    for spec in args.llm:
        label, mdir, arm = parse_llm(spec)
        reasoner = ManifestLLMReasoner([mdir], arm=arm)
        covered = [p for p in pids if reasoner.has(p)]
        print(f"\n=== {label}: {arm} from {mdir}  covers {len(covered)}/{len(pids)} letters ===",
              flush=True)
        if not covered:
            continue
        pipe = ChainPipeline(
            extractor=base._extractor, assembler=cached,
            candidate_service=base._candidate_service, llm_reasoner=reasoner,
        )
        pipe.cfg.ground_llm_values = not args.no_ground
        pipe.cfg.disagree_primary = {
            _CLAIM_PATH.get(f, f): "llm" for f in args.disagree_llm.split(",") if f}
        per_doc: dict[str, list] = {s: [] for s in SYSTEMS}
        claims_all: list[tuple[str, Any]] = []
        totals = Counter()
        n_valid = n_populated = 0
        from services.ft_extract import is_degenerate
        for pid in covered:
            stats, claims = pipe.extract(
                texts[pid], document_id=pid, return_claims=True)
            llm_pheno = reasoner(texts[pid], pid, "2024-01-01")
            n_valid += llm_pheno is not None
            n_populated += llm_pheno is not None and not is_degenerate(llm_pheno)
            preds = {
                "llm": native_from_module_dicts(llm_pheno),
                "specialist": native_from_claims(spec_claims[pid], {"accept", "review"}, "epextra"),
                "leo_auto": native_from_claims(claims, {"accept"}),
                "leo_review": native_from_claims(claims, {"accept", "review"}),
            }
            for s in SYSTEMS:
                per_doc[s].append(score_doc(preds[s], gold[pid]))
            for c in claims:
                claims_all.append((pid, c))
            totals.update({
                "claims": stats.n_claims_emitted, "accept": stats.n_accepted,
                "review": stats.n_review, "reject": stats.n_rejected,
                "llm_agree": stats.n_llm_agree, "llm_disagree": stats.n_llm_disagree,
                "specialist_only": stats.n_specialist_only, "llm_only": stats.n_llm_only,
                "llm_unsupported": stats.n_llm_unsupported,
                "acute_rerouted": stats.n_acute_rerouted,
                "rescue_routed": stats.n_rescue_routed,
                "specialist_only_unconfirmed": stats.n_specialist_only_unconfirmed,
                "empty_frequency_dropped": stats.n_empty_frequency_dropped,
            })

        block: dict = {"arm": arm, "dir": str(mdir), "n_letters": len(covered),
                       "n_llm_phenotype_valid": n_valid,
                       "n_llm_phenotype_populated": n_populated, "systems": {}}
        # Audit trail: every drug moved out of current_asms by a role rule, with the gold's verdict.
        block["routed_drugs"] = []
        for pid_, c_ in claims_all:
            if c_.field_path in ("medication.acute_administration", RESCUE_FIELD_PATH):
                v_ = _plain(c_.value)
                nm_ = canon_drug(str((v_ or {}).get("generic_name", ""))) if isinstance(v_, dict) else ""
                block["routed_drugs"].append({
                    "pid": pid_, "role": c_.field_path.rsplit(".", 1)[1], "drug": nm_,
                    "quote": c_.mention.text, "gold_lists_as_current": nm_ in {
                        canon_drug(x) for x in gold[pid_].get("current_asms") or []}})
        pairs = [("leo_auto", "llm"), ("leo_review", "llm"), ("leo_review", "specialist"),
                 ("leo_auto", "specialist")]
        boot = bootstrap(per_doc, pairs, n=args.bootstrap)
        for s in SYSTEMS:
            p, r, f1 = micro(per_doc[s])
            block["systems"][s] = {
                "micro_p": p, "micro_r": r, "micro_f1": f1,
                "f1_ci": boot["f1_ci"][s], "per_field": per_field(per_doc[s]),
            }
        block["paired_diff_micro_f1"] = boot["diff"]

        # Claim-level precision by category (only claims with gold reference).
        cat: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])   # correct, scored, total
        for pid, c in claims_all:
            k = claim_category(c)
            cat[k][2] += 1
            ok = claim_correct(c, gold[pid])
            if ok is not None:
                cat[k][1] += 1
                cat[k][0] += int(ok)
        block["claim_precision_ci"] = claim_bootstrap(claims_all, gold, n=args.bootstrap)
        block["claim_precision_by_category"] = {
            k: {"correct": v[0], "scored": v[1], "total": v[2],
                "precision": (v[0] / v[1]) if v[1] else None}
            for k, v in sorted(cat.items())
        }
        grounded = sum(1 for _, c in claims_all if c.concept.system != "MEDAI-ENUM")
        n_claims = totals["claims"]
        proposed_by_llm = totals["llm_agree"] + totals["llm_disagree"] + totals["llm_only"] + totals["llm_unsupported"]
        block["safety"] = {
            "claims": n_claims,
            "accept_rate": totals["accept"] / n_claims if n_claims else None,
            "review_rate": totals["review"] / n_claims if n_claims else None,
            "reject_rate": totals["reject"] / n_claims if n_claims else None,
            "ontology_grounded_rate": grounded / n_claims if n_claims else None,
            "llm_proposed_unmatched": totals["llm_only"] + totals["llm_unsupported"],
            "llm_unsupported_quote": totals["llm_unsupported"],
            "llm_unsupported_rate_of_unmatched": (
                totals["llm_unsupported"] / (totals["llm_only"] + totals["llm_unsupported"])
                if (totals["llm_only"] + totals["llm_unsupported"]) else None),
            "counts": dict(totals),
        }
        report["sources"][label] = block
        per_doc_by_label[label] = (covered, per_doc)

        print(f"{'system':<12} {'microP':>7} {'microR':>7} {'microF1':>8}   95% CI")
        for s in SYSTEMS:
            b = block["systems"][s]
            print(f"{s:<12} {b['micro_p']:>7.3f} {b['micro_r']:>7.3f} {b['micro_f1']:>8.3f}   "
                  f"[{b['f1_ci'][0]:.3f}, {b['f1_ci'][1]:.3f}]")
        for k, d in block["paired_diff_micro_f1"].items():
            print(f"  Δ micro-F1 {k:<22} {d['mean']:+.3f}  CI [{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}]")
        print("  claim precision by category:",
              {k: (round(v['precision'], 3) if v['precision'] is not None else None, v['scored'])
               for k, v in block["claim_precision_by_category"].items()})
        print("  safety:", {k: (round(v, 3) if isinstance(v, float) else v)
                            for k, v in block["safety"].items() if k != "counts"})

    report["cross"] = cross_contrasts(per_doc_by_label, n=args.bootstrap)
    for k, v in report["cross"].items():
        print(f"  cross {k:<40} {v['mean']:+.3f}  CI [{v['ci'][0]:+.3f}, {v['ci'][1]:+.3f}]")

    out = Path(args.out)
    if not out.is_absolute():
        out = REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_md(report, out.with_suffix(".md"))
    print(f"\nwrote {out.with_suffix('.json')} and {out.with_suffix('.md')}")
    return 0


def cross_contrasts(per_doc_by_label: dict, n: int = 2000, seed: int = 0) -> dict:
    """Paired letter-level bootstrap of micro-F1 differences between systems of different sources.

    ``llm[X]-llm[Y]`` for every pair of sources (same letters only),
    ``llm[X]-specialist`` and ``leo_review[X]-llm[X]`` per source.
    """
    labels = list(per_doc_by_label)
    out: dict = {}
    pairs: list[tuple[str, str, list[str], list, list]] = []
    for lab in labels:
        pids, pd = per_doc_by_label[lab]
        pairs.append((f"llm[{lab}]-specialist", lab, pids, [d for d in pd["llm"]], [d for d in pd["specialist"]]))
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            pa, da = per_doc_by_label[a]
            pb, db = per_doc_by_label[b]
            common = [p for p in pa if p in pb]
            if len(common) < 10:
                continue
            xa = [da["llm"][pa.index(p)] for p in common]
            xb = [db["llm"][pb.index(p)] for p in common]
            pairs.append((f"llm[{a}]-llm[{b}]", a, common, xa, xb))
    rng = random.Random(seed)
    for name, _lab, pids, xa, xb in pairs:
        m = len(pids)
        vals = []
        for _ in range(n):
            idx = [rng.randrange(m) for _ in range(m)]
            vals.append(micro(xa, idx)[2] - micro(xb, idx)[2])
        vals.sort()
        out[name] = {"mean": sum(vals) / len(vals), "n_letters": m,
                     "ci": (vals[int(0.025 * n)], vals[min(n - 1, int(0.975 * n))])}
    return out


def _write_md(report: dict, path: Path) -> None:
    L = ["# LEO vs Fonferko-Shadrach native gold", "",
         "*Generated by `scripts/score_leo_vs_fs_gold.py`.  Held-out letters EA0161-EA0200; "
         "seven native-gold fields (see script docstring).  `llm` = Med42-8B alone, "
         "`specialist` = EpExtra alone, `leo_auto` = claims routed ACCEPT, "
         "`leo_review` = ACCEPT + REVIEW.*", "",
         "Current-ASM view: " + ("maintenance + rescue (rescue drugs count as current)"
                                if report.get("rescue_as_current", True)
                                else "maintenance only (rescue drugs do not count)")
         + "; acute administrations never count.", ""]
    for label, b in report["sources"].items():
        L += [f"## {label}  (arm {b['arm']}, {b['n_letters']} letters, "
              f"{b['n_llm_phenotype_valid']} with a schema-valid LLM phenotype, "
              f"{b['n_llm_phenotype_populated']} with at least one populated field)", "",
              "| system | micro P | micro R | micro F1 | 95% CI |", "|---|---:|---:|---:|---|"]
        for s in SYSTEMS:
            x = b["systems"][s]
            L.append(f"| {s} | {x['micro_p']:.3f} | {x['micro_r']:.3f} | {x['micro_f1']:.3f} | "
                     f"[{x['f1_ci'][0]:.3f}, {x['f1_ci'][1]:.3f}] |")
        L += ["", "Paired difference in micro-F1 (letters resampled):", "",
              "| contrast | mean | 95% CI |", "|---|---:|---|"]
        for k, d in b["paired_diff_micro_f1"].items():
            L.append(f"| {k} | {d['mean']:+.3f} | [{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}] |")
        L += ["", "Per-field F1:", "",
              "| field | n | " + " | ".join(SYSTEMS) + " |", "|---|---:|" + "---:|" * len(SYSTEMS)]
        for fld in FIELDS + EXTRA_FIELDS:
            row = [b["systems"][s]["per_field"].get(fld) for s in SYSTEMS]
            n = next((r["n"] for r in row if r), 0)
            L.append(f"| `{fld}`{' (extra view, not in micro)' if fld in EXTRA_FIELDS else ''} | {n} | " +
                     " | ".join(f"{r['f1']:.3f}" if r else "-" for r in row) + " |")
        L += ["", "Claim precision by detector agreement (claims with a gold reference):", "",
              "| category | scored | precision |", "|---|---:|---:|"]
        for k, v in b["claim_precision_by_category"].items():
            pr = f"{v['precision']:.3f}" if v["precision"] is not None else "-"
            L.append(f"| {k} | {v['scored']} / {v['total']} | {pr} |")
        cc = b.get("claim_precision_ci")
        if cc:
            L += ["", "Letter-level bootstrap, claim precision 95% CI: " + "; ".join(
                f"{k} [{v[0]:.2f}, {v[1]:.2f}]" for k, v in cc["precision"].items() if v) + ".",
                  "Agree minus other category: " + "; ".join(
                f"{k} {d['mean']:+.2f} [{d['ci'][0]:+.2f}, {d['ci'][1]:+.2f}]"
                for k, d in cc["agree_minus"].items() if d["ci"]) + "."]
        sf = b["safety"]
        fmt = lambda x: "-" if x is None else f"{x:.3f}"
        L += ["", f"Safety: accept {fmt(sf['accept_rate'])}, review {fmt(sf['review_rate'])}, "
              f"reject {fmt(sf['reject_rate'])}; ontology-grounded {fmt(sf['ontology_grounded_rate'])}; "
              f"LLM claims without a specialist match {sf['llm_proposed_unmatched']} of which "
              f"{sf['llm_unsupported_quote']} had a quote not in the note.", ""]
    if report.get("cross"):
        L += ["## Paired contrasts across systems and sources (micro-F1, letters resampled)", "",
              "| contrast | letters | mean | 95% CI |", "|---|---:|---:|---|"]
        for k, v in report["cross"].items():
            L.append(f"| {k} | {v['n_letters']} | {v['mean']:+.3f} | [{v['ci'][0]:+.3f}, {v['ci'][1]:+.3f}] |")
        L.append("")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
