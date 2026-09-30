#!/usr/bin/env python3
"""Emit MedCATTrainer-format silver labels for MetaCAT training.

Walks a corpus of clinical notes, runs MedCAT to get concept spans, and
attaches per-span meta-annotations for the four ExECT-V2 tasks:

    Presence     — affirmed | negated
    Experiencer  — patient  | family | other
    Temporality  — current  | past | hypothetical
    Certainty    — definite | probable | possible

Labels are derived from two sources:
  1. medspaCy ConText attributes on each MedCAT LinkedEntity
     (is_negated, is_family, is_historical, is_hypothetical) — used
     as-is, since these are the same signals the current B1' pipeline
     produces at ~0.85 F1 on shared fields.
  2. Semantic plans (synth-v3) or clinician silver (F-S train 160)
     — used to OVERRIDE ConText for entities whose CUI aligns with a
     plan/silver assertion.  This gives MetaCAT training examples where
     the label is anchored to an authoritative source, not just to
     ConText's own rules.

Output format: MedCATTrainer JSON export (verbatim MedCAT 2.9 schema,
see medcat.data.mctexport.MedCATTrainerExport):

    {"projects": [{
       "name": "synth_v3_polish",
       "id":   "auto",
       "cuis": "",
       "documents": [
         {"id": "...", "name": "P004000_V01", "text": "...",
          "annotations": [
             {"cui": "C0086237", "start": 42, "end": 51,
              "value": "epilepsy",
              "meta_anns": {
                "Presence":   {"name": "Presence",   "value": "affirmed", "acc": 1.0, "validated": true},
                "Experiencer":{"name": "Experiencer","value": "patient", "acc": 1.0, "validated": true},
                "Temporality":{"name": "Temporality","value": "current", "acc": 1.0, "validated": true},
                "Certainty":  {"name": "Certainty",  "value": "definite","acc": 1.0, "validated": true}
              }}
          ]}
       ]
    }]}

Two projects can be emitted in one file: one for synth-v3-polish, one
for F-S train 160 (the latter using B1' rule outputs as the silver
source).

Usage:

    # Synth-v3 polish (assumes corpus + targets exist)
    venv-medcat/bin/python scripts/emit_metacat_silver.py \\
        --sources synth-v3-polish \\
        --out data/metacat_training/silver.json

    # F-S train 160 (uses B1' outputs on the train slice)
    venv-medcat/bin/python scripts/emit_metacat_silver.py \\
        --sources fs-train-160 \\
        --out data/metacat_training/fs_train_silver.json

    # Combined (both projects in one file)
    venv-medcat/bin/python scripts/emit_metacat_silver.py \\
        --sources synth-v3-polish,fs-train-160 \\
        --out data/metacat_training/combined_silver.json

    # Sanity check
    venv-medcat/bin/python scripts/emit_metacat_silver.py \\
        --sources synth-v3-polish --limit 5 --dry-run

Requires the venv-medcat interpreter (medspacy + MedCAT).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


# ─── Constants ────────────────────────────────────────────────────────────

DEFAULT_CDB = REPO / "data" / "medcat_cdb_epilepsy" / "cdb"

SYNTH_V3_POLISH_CORPUS = REPO / "data" / "eval_corpora" / "synth_v3_polish"
SYNTH_V3_POLISH_PATIENTS = REPO / "data" / "episynth_corpus" / "v3_polish" / "patients"

FS_ROOT = REPO / "data" / "fs_corpus"
FS_DOCS = FS_ROOT / "documents"
FS_SILVER_ROOT = REPO / "data" / "fonferko_shadrach_2024" / "silver_labels_v0_2_1"

TASKS = ["Presence", "Experiencer", "Temporality", "Certainty"]
DEFAULT_LABELS = {
    "Presence":    "affirmed",
    "Experiencer": "patient",
    "Temporality": "current",
    "Certainty":   "definite",
}


# ─── ConText → meta-annotation mapping ────────────────────────────────────

def _labels_from_context(ent) -> dict[str, str]:
    """Map medspaCy ConText booleans on a LinkedEntity to meta-annotation values."""
    d = dict(DEFAULT_LABELS)
    if getattr(ent, "is_negated", False):
        d["Presence"] = "negated"
    if getattr(ent, "is_family", False):
        d["Experiencer"] = "family"
    if getattr(ent, "is_hypothetical", False):
        d["Temporality"] = "hypothetical"
    elif getattr(ent, "is_historical", False):
        d["Temporality"] = "past"
    return d


# ─── Plan-level overrides for synth-v3 ────────────────────────────────────
#
# Every plan assertion (required_assertions[i]) carries a v0.2.1 Evidence[T]-
# style dict with `certainty` and `temporal_status`.  We use those to
# override ConText for concept spans whose surface text overlaps the plan
# evidence text.

def _load_plan(patient_id: str) -> dict | None:
    p = SYNTH_V3_POLISH_PATIENTS / f"{patient_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def _plan_overrides(ent, plan: dict | None) -> dict[str, str] | None:
    """If the entity's span or CUI aligns with a plan assertion, return the
    plan's certainty/temporal labels.  Otherwise return None (fall through
    to ConText).
    """
    if plan is None:
        return None
    ent_text = (getattr(ent, "text", "") or "").lower()
    if not ent_text:
        return None
    for req in plan.get("required_assertions", []):
        val = req.get("value")
        # Only DENIED_FINDINGS carry an explicit negation intent.
        if req.get("field") == "DENIED_FINDINGS" and isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.lower() in ent_text:
                    return {"Presence": "negated", "Experiencer": "patient",
                            "Temporality": "current", "Certainty": "definite"}
        if req.get("field") == "FAMILY_HISTORY" and isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    cond = (item.get("condition") or "").lower()
                    if cond and cond in ent_text:
                        return {"Presence": "affirmed", "Experiencer": "family",
                                "Temporality": "past", "Certainty": "definite"}
        if req.get("field") == "PRIOR_ASMS" and isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    name = (item.get("generic_name") or "").lower()
                    if name and name in ent_text:
                        return {"Presence": "affirmed", "Experiencer": "patient",
                                "Temporality": "past", "Certainty": "definite"}
        if req.get("field") == "HEDGED_FINDINGS" and isinstance(val, list):
            for item in val:
                if isinstance(item, tuple) or isinstance(item, list):
                    phrase, certainty = item[0], item[1] if len(item) > 1 else "possible"
                    if isinstance(phrase, str) and phrase.lower() in ent_text.lower():
                        return {"Presence": "affirmed", "Experiencer": "patient",
                                "Temporality": "current",
                                "Certainty": certainty}
    return None


# ─── Per-source annotation builders ───────────────────────────────────────

def _build_synth_v3_polish_docs(extractor, limit: int | None) -> list[dict]:
    """Iterate over the synth-v3-polish manifest and emit MedCATTrainer docs."""
    manifest = SYNTH_V3_POLISH_CORPUS / "manifest.csv"
    if not manifest.exists():
        print(f"[emit-metacat] SKIP synth-v3-polish — {manifest} not found",
              file=sys.stderr)
        return []
    with manifest.open() as fh:
        rows = list(csv.DictReader(fh))
    if limit:
        rows = rows[:limit]
    docs = []
    for row in rows:
        note_path = SYNTH_V3_POLISH_CORPUS / row["note_path"]
        if not note_path.exists():
            continue
        text = note_path.read_text()
        if not text.strip():
            continue
        plan = _load_plan(row["patient_id"])
        entities, _spacy_doc = extractor.extract_with_context(text, _nlp)
        annotations = _entities_to_annotations(entities, plan)
        if not annotations:
            continue
        docs.append({
            "id": row["visit_id"],
            "name": row["visit_id"],
            "last_modified": _now_iso(),
            "text": text,
            "annotations": annotations,
        })
    return docs


def _build_fs_train_docs(extractor, limit: int | None) -> list[dict]:
    """F-S train 160 (EA0001..EA0160)."""
    if not FS_DOCS.exists():
        print(f"[emit-metacat] SKIP fs-train-160 — {FS_DOCS} not found",
              file=sys.stderr)
        return []
    train_pids = [f"EA{i:04d}" for i in range(1, 161)]
    if limit:
        train_pids = train_pids[:limit]
    docs = []
    for pid in train_pids:
        pid_dir = FS_DOCS / pid
        if not pid_dir.is_dir():
            continue
        # F-S has one output.txt per patient/doc_type; take the first.
        for doc_dir in sorted(pid_dir.iterdir()):
            out = doc_dir / "output.txt" if doc_dir.is_dir() else None
            if not out or not out.exists():
                continue
            text = out.read_text()
            if not text.strip():
                continue
            entities, _ = extractor.attach_context(text)
            annotations = _entities_to_annotations(entities, plan=None)
            if not annotations:
                continue
            docs.append({
                "id": f"{pid}_{doc_dir.name}",
                "name": f"{pid}_{doc_dir.name}",
                "last_modified": _now_iso(),
                "text": text,
                "annotations": annotations,
            })
            break  # one doc per patient is enough for MetaCAT training
    return docs


def _entities_to_annotations(entities, plan) -> list[dict]:
    out = []
    for ent in entities:
        cs, ce = getattr(ent, "char_start", None), getattr(ent, "char_end", None)
        if cs is None or ce is None:
            continue
        cui = getattr(ent, "cui", "") or ""
        text_surface = getattr(ent, "text", "") or ""
        # Base labels from ConText
        labels = _labels_from_context(ent)
        # Plan-level override (synth-v3 only) — trust the plan over ConText
        override = _plan_overrides(ent, plan)
        if override:
            labels.update(override)
        out.append({
            "start": int(cs),
            "end":   int(ce),
            "cui":   cui,
            "value": text_surface,
            "id":    f"{cs}_{ce}",
            "validated": True,
            "meta_anns": {
                name: {"name": name, "value": labels[name],
                       "acc": 1.0, "validated": True}
                for name in TASKS
            },
        })
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", default="synth-v3-polish",
                    help="Comma-separated: synth-v3-polish, fs-train-160")
    ap.add_argument("--out", default="data/metacat_training/silver.json")
    ap.add_argument("--cdb", default=str(DEFAULT_CDB))
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap on docs per source (for smoke test)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print counts + first doc annotation summary, do not write")
    args = ap.parse_args()

    print(f"[emit-metacat] Loading MedCAT extractor from {args.cdb}", flush=True)
    from services.medcat_extractor import MedCATExtractor
    from rules.context_config import build_medspacy_pipeline
    extractor = MedCATExtractor(args.cdb, verbose=False)
    global _nlp
    _nlp = build_medspacy_pipeline()

    all_projects = []
    for src in [s.strip() for s in args.sources.split(",") if s.strip()]:
        print(f"[emit-metacat] === Source: {src} ===", flush=True)
        if src == "synth-v3-polish":
            docs = _build_synth_v3_polish_docs(extractor, args.limit)
        elif src == "fs-train-160":
            docs = _build_fs_train_docs(extractor, args.limit)
        else:
            print(f"[emit-metacat] WARN unknown source: {src}", file=sys.stderr)
            continue
        n_ann = sum(len(d["annotations"]) for d in docs)
        print(f"[emit-metacat]   docs: {len(docs)}   total annotations: {n_ann}")
        # Label distribution report
        by_task_label = {t: {} for t in TASKS}
        for d in docs:
            for a in d["annotations"]:
                for t in TASKS:
                    v = a["meta_anns"][t]["value"]
                    by_task_label[t][v] = by_task_label[t].get(v, 0) + 1
        for t in TASKS:
            dist = ", ".join(f"{v}={n}" for v, n in sorted(by_task_label[t].items(),
                                                            key=lambda x: -x[1]))
            print(f"[emit-metacat]   {t}: {dist}")

        all_projects.append({
            "name": src,
            "id":   src,
            "cuis": "",
            "documents": docs,
        })

    export = {"projects": all_projects}

    if args.dry_run:
        # Show first doc's first 3 annotations
        for proj in all_projects:
            if not proj["documents"]:
                continue
            d = proj["documents"][0]
            print(f"\n[emit-metacat] Sample from {proj['name']} → {d['name']} "
                  f"(text len={len(d['text'])}):")
            for a in d["annotations"][:3]:
                print(f"  span [{a['start']}:{a['end']}] '{a['value'][:30]}' cui={a['cui']}")
                print(f"    labels: " + ", ".join(
                    f"{t}={a['meta_anns'][t]['value']}" for t in TASKS))
        return 0

    out = Path(args.out)
    if not out.is_absolute():
        out = REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[emit-metacat] Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
