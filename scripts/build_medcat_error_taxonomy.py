#!/usr/bin/env python3
"""Phase 7 — sample F-S 40 held-out errors, categorize them, write taxonomy.

Categories (per plan §Phase 7):
  - vocabulary_miss  : concept never surfaced (extractor didn't find it)
  - negation_flip    : concept surfaced but ConText flipped it wrong
  - temporality_flip : historical/current mis-tag
  - compound_bug     : compound rule (drug_resistance / concordance) wrong
  - ambiguous_gold   : gold is arguably wrong or ambiguous
  - us_idiom_miss    : US spelling/idiom (SOAP header, spelling) not handled
  - section_miss     : SOAP section wrong (e.g. HPI misfiled as past-med-hx)
  - other            : uncategorized

Usage
-----
::

    venv-medcat/bin/python scripts/build_medcat_error_taxonomy.py \
        --predictions-dir data/run_manifests_medcat_rules_fs_test_40/ \
        --gold-dir data/fonferko_shadrach_2024/silver_labels_v0_2_1/ \
        --docs-dir data/fs_corpus/documents/ \
        --n-errors 25 \
        --out-md eval/results/medcat_error_taxonomy.md
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Fields to sample errors from (both scalar and multiset).
SCALAR_FIELDS = [
    ("clinical_seizure", "epilepsy_type"),
    ("clinical_seizure", "predominant_seizure_type"),
    ("clinical_seizure", "etiology_category"),
    ("clinical_seizure", "age_at_onset_years"),
]
MULTISET_FIELDS = [
    ("clinical_seizure", "other_seizure_types"),
    ("medication", "current_asms"),  # multiset of drugs
    ("medication", "prior_asms"),
]


def _ev_value(mod: dict | None, field: str):
    if not isinstance(mod, dict):
        return None
    ev = mod.get(field)
    if not isinstance(ev, dict):
        return None
    return ev.get("value")


def _ev_multiset_enum(mod: dict | None, field: str) -> list[str]:
    if not isinstance(mod, dict):
        return []
    lst = mod.get(field) or []
    out = []
    for ev in lst:
        if isinstance(ev, dict):
            v = ev.get("value")
            if v is not None:
                out.append(str(v).lower())
    return out


def _ev_multiset_med(mod: dict | None, field: str) -> list[str]:
    if not isinstance(mod, dict):
        return []
    out = []
    for ev in mod.get(field) or []:
        if isinstance(ev, dict):
            v = ev.get("value")
            if isinstance(v, dict):
                n = v.get("generic_name")
                if n:
                    out.append(str(n).lower())
    return out


def _categorize(field: str, gold, pred, text: str) -> str:
    """Heuristic categorization of an error."""
    tl = (text or "").lower()
    gold_l = str(gold).lower() if gold is not None else ""
    pred_l = str(pred).lower() if pred is not None else ""

    # 1. vocabulary_miss = surface form isn't in the text at all (safest heuristic:
    #    key surface tokens for the gold enum don't occur in the text)
    key_tokens: list[str] = []
    if isinstance(gold, str):
        key_tokens = [w for w in gold_l.replace("_", " ").split() if len(w) > 3]

    if pred is None and gold is not None:
        # Gold token literally absent → vocab_miss (extractor never saw it).
        # If gold IS present in text but we didn't extract → also vocab_miss
        # or context_flip depending on whether ConText might have suppressed.
        gold_tok_in_text = any(t in tl for t in key_tokens) if key_tokens else False
        if not gold_tok_in_text:
            # Try synonyms — GTCS ↔ generalized tonic clonic, etc.
            synonyms = {
                "generalized_tonic_clonic": ["gtcs", "tonic clonic", "tonic-clonic",
                                             "grand mal"],
                "focal_impaired_awareness": ["complex partial", "focal impaired"],
                "focal_aware": ["simple partial", "focal aware"],
                "absence_typical": ["absence", "petit mal"],
                "myoclonic": ["myoclon"],
                "generalized": ["generali"],
                "focal": ["focal", "partial", "temporal", "frontal"],
                "structural": ["stroke", "trauma", "lesion", "tumor",
                               "haemorrhage", "hemorrhage", "cortical", "meningi"],
                "genetic": ["genetic", "mutation", "familial"],
                "infectious": ["encephalitis", "meningitis", "infection", "hsv"],
                "immune": ["autoimmune", "autoantibody", "anti-nmda"],
                "metabolic": ["metabolic", "hypoglyc", "hyperglyc"],
                "unknown": ["unknown", "cryptogenic"],
            }
            syn = synonyms.get(gold_l, [])
            if any(s in tl for s in syn):
                return "vocabulary_miss"  # concept in text via synonym, missed
            return "vocabulary_miss"  # concept not in text at all
        else:
            # Gold token present in text but not surfaced → likely context suppression
            # or section miss.
            # Look for negation cue words within 30 chars
            for cue in ("no ", "not ", "denies", "without", "negative"):
                for t in key_tokens:
                    idx = tl.find(t)
                    if idx >= 0:
                        window = tl[max(0, idx - 30):idx]
                        if cue in window:
                            return "negation_flip"
            # Historical marker?
            for cue in ("previously", "history of", "past", "in the past",
                        "years ago", "childhood"):
                for t in key_tokens:
                    idx = tl.find(t)
                    if idx >= 0:
                        window = tl[max(0, idx - 40):idx]
                        if cue in window:
                            return "temporality_flip"
            return "section_miss"

    # 2. value mismatch — pred says X, gold says Y
    if pred is not None and gold is not None and pred_l != gold_l:
        # Field-specific rules
        if field == "epilepsy_type":
            # Focal vs generalized confusion: could be compound / seizure_type
            # → epilepsy_type inference bug.
            return "compound_bug"
        if field == "predominant_seizure_type":
            return "compound_bug"
        return "compound_bug"

    return "other"


def _collect_errors(preds: dict, gold: dict, texts: dict) -> list[dict]:
    """Return list of error records across scalar and multiset fields."""
    errors = []
    for doc_id in sorted(gold.keys()):
        if doc_id not in preds:
            continue
        pred_ph = preds[doc_id]
        gold_ph = gold[doc_id]
        text = texts.get(doc_id, "")

        # Scalars
        for module, field in SCALAR_FIELDS:
            g = _ev_value(gold_ph.get(module), field)
            p = _ev_value(pred_ph.get(module), field)
            if g is None:
                continue
            if p is None or str(p).lower() != str(g).lower():
                # Numeric tolerance for age
                if field == "age_at_onset_years" and p is not None and g is not None:
                    try:
                        if abs(float(p) - float(g)) <= 1.0:
                            continue
                    except (ValueError, TypeError):
                        pass
                cat = _categorize(field, g, p, text)
                errors.append({
                    "doc_id": doc_id,
                    "field": f"{module}.{field}",
                    "gold": g,
                    "pred": p,
                    "category": cat,
                })

        # Multisets (enum)
        for module, field in [("clinical_seizure", "other_seizure_types")]:
            g_items = set(_ev_multiset_enum(gold_ph.get(module), field))
            p_items = set(_ev_multiset_enum(pred_ph.get(module), field))
            missing = g_items - p_items
            extra = p_items - g_items
            for m in sorted(missing):
                cat = _categorize(field, m, None, text)
                errors.append({
                    "doc_id": doc_id,
                    "field": f"{module}.{field} (FN)",
                    "gold": m, "pred": None, "category": cat,
                })
            for m in sorted(extra):
                errors.append({
                    "doc_id": doc_id,
                    "field": f"{module}.{field} (FP)",
                    "gold": None, "pred": m, "category": "compound_bug",
                })

        # Multisets (medications)
        for module, field in [("medication", "current_asms"),
                              ("medication", "prior_asms")]:
            g_items = set(_ev_multiset_med(gold_ph.get(module), field))
            p_items = set(_ev_multiset_med(pred_ph.get(module), field))
            missing = g_items - p_items
            extra = p_items - g_items
            for m in sorted(missing):
                # Is the drug name in the text?
                if m in (text or "").lower():
                    cat = "temporality_flip"  # drug seen but wrong list bucket
                else:
                    cat = "vocabulary_miss"
                errors.append({
                    "doc_id": doc_id,
                    "field": f"{module}.{field} (FN)",
                    "gold": m, "pred": None, "category": cat,
                })
            for m in sorted(extra):
                # We predicted a drug not in gold — often temporality bug
                # (prior vs current) or over-extraction from text
                cat = "temporality_flip" if m in (text or "").lower() else "compound_bug"
                errors.append({
                    "doc_id": doc_id,
                    "field": f"{module}.{field} (FP)",
                    "gold": None, "pred": m, "category": cat,
                })

    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--predictions-dir", required=True)
    ap.add_argument("--gold-dir", required=True)
    ap.add_argument("--docs-dir", required=True,
                    help="Root of source text (e.g. data/fs_corpus/documents/).")
    ap.add_argument("--n-errors", type=int, default=25)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    # Load pred + gold — restrict to held-out F-S 40
    holdout = {f"EA{i:04d}" for i in range(161, 201)}
    preds = {}
    for p in Path(args.predictions_dir).glob("*.json"):
        if p.name.startswith("_"):
            continue
        if p.stem in holdout:
            preds[p.stem] = json.loads(p.read_text())
    gold = {}
    for p in Path(args.gold_dir).glob("*.json"):
        if p.stem in holdout:
            j = json.loads(p.read_text())
            ph = j.get("phenotype") if isinstance(j.get("phenotype"), dict) else j
            gold[p.stem] = ph
    docs_root = Path(args.docs_dir)
    texts = {}
    for did in holdout:
        p = docs_root / did / "progress_note" / "output.txt"
        if p.exists():
            texts[did] = p.read_text(encoding="utf-8", errors="replace")

    errors = _collect_errors(preds, gold, texts)
    print(f"Total error records collected: {len(errors)}")

    rng = random.Random(args.seed)
    if len(errors) > args.n_errors:
        sample = rng.sample(errors, args.n_errors)
    else:
        sample = errors

    # Distribution across ALL errors and across sample
    dist_all = Counter(e["category"] for e in errors)
    dist_samp = Counter(e["category"] for e in sample)

    def _fmt(g):
        if g is None:
            return "(none)"
        s = str(g)
        return s if len(s) < 60 else s[:57] + "…"

    lines = [
        "# MedCAT+Rules (arm B1') — Phase 7 first-pass error taxonomy\n",
        "*Generated by `scripts/build_medcat_error_taxonomy.py` on 40 "
        "held-out F-S letters (EA0161–EA0200).*\n",
        f"* Total error records across all fields: **{len(errors)}**",
        f"* Sample size for close-read: **{len(sample)}** "
        f"(seed={args.seed})",
        "",
        "## Distribution across ALL errors (not just sample)\n",
        "| category | count | share |",
        "|---|---:|---:|",
    ]
    tot_all = sum(dist_all.values())
    for cat, n in dist_all.most_common():
        share = 100.0 * n / tot_all if tot_all else 0.0
        lines.append(f"| {cat} | {n} | {share:.1f}% |")
    lines += ["", "## Distribution in sampled subset\n",
              "| category | count | share |",
              "|---|---:|---:|"]
    tot_s = sum(dist_samp.values())
    for cat, n in dist_samp.most_common():
        share = 100.0 * n / tot_s if tot_s else 0.0
        lines.append(f"| {cat} | {n} | {share:.1f}% |")

    lines += [
        "",
        "## Sampled error examples\n",
        "| doc | field | gold | pred | category |",
        "|---|---|---|---|---|",
    ]
    for e in sample:
        lines.append(
            f"| {e['doc_id']} | `{e['field']}` | "
            f"{_fmt(e['gold'])} | {_fmt(e['pred'])} | {e['category']} |"
        )

    # Recommendations
    top_cats = [c for c, _ in dist_all.most_common(3)]
    rec_map = {
        "vocabulary_miss": "Enrich `rules/epilepsy_ontology.py` with UMLS "
        "aliases (Phase 1d) — the primary lift; +5–15% F1 typical when UMLS "
        "clears. Also add manual synonyms for GTCS, absences, complex partial, "
        "EEG jargon (spike-wave, PLED, LPD).",
        "compound_bug": "Rework compound rules: focal→generalized inference "
        "for `epilepsy_type` when only seizure_type is present; drug bucket "
        "assignment (current vs prior); disambiguate multi-drug list ordering.",
        "temporality_flip": "Tune Phase 4 ConText — expand HISTORICAL cue "
        "list (`years ago`, `during childhood`, `in her teens`); differentiate "
        "prior vs failed vs current ASM by verb tense.",
        "negation_flip": "Extend medspaCy negation triggers (`ruled out`, "
        "`denies any`, `no history of`) and re-check section scoping (US SOAP "
        "sections).",
        "section_miss": "Sharpen `rules/us_note_structure.py` — add "
        "'HISTORY OF PRESENT ILLNESS', 'PAST MEDICAL HISTORY', 'MEDICATIONS' "
        "headers, escape-tolerant to trailing colons and case variants.",
        "us_idiom_miss": "Expand `rules/uk_to_us_lexicon.py` with more UK→US "
        "drug names and epilepsy jargon.",
        "ambiguous_gold": "Manual gold review — silver labels are "
        "deterministic and known to be imperfect. Flag and set aside; do "
        "not chase.",
        "other": "Manual review of representative examples to refine "
        "categorization.",
    }
    lines += ["", "## Phase 8 refinement recommendations (priority-ordered)\n"]
    for i, cat in enumerate(top_cats, 1):
        lines.append(f"**Priority {i} — {cat} ({dist_all[cat]} errors, "
                     f"{100.0*dist_all[cat]/tot_all:.1f}%):** "
                     f"{rec_map.get(cat, 'Investigate.')}")
        lines.append("")

    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
