#!/usr/bin/env python3
"""Corpus-agnostic US clinical note preprocessing CLI.

Consumes any input corpus (a directory of note.txt files, a manifest.csv +
documents/ layout, or a flat file glob) and emits the preprocessed corpus
in the universal manifest v1.0 schema (see docs/CORPUS_MANIFEST_SCHEMA.md).

Preprocessing stages (all optional):
    A. Relevance scoring + filter (default: keep score >= 3.0)
    B. H&P section header canonicalization (CC:  → Chief Complaint:, etc.)
    C. ILAE 2017 legacy → modern annotation (grand mal → grand mal
       (generalized tonic-clonic))
    D. Brand → generic drug annotation (Keppra → Keppra (levetiracetam))

Shared library:  services/us_note_preprocessing.py

Supported input layouts
-----------------------

  --layout mtsamples
      data/eval_corpora/mtsamples_neuro/mt_sample_XXXX/note.txt
      (auto-emits visit_id MT_V####, patient_id MT_P####)

  --layout flat
      Any directory with *.txt files (each file → one visit).
      visit_id = filename stem; patient_id = visit_id + "_pt"

  --layout manifest
      Existing manifest.csv (must have visit_id, patient_id, note_path
      columns) + documents/ subdirectory. Preprocessed notes are written
      alongside a new manifest.

Usage
-----

MTSamples (US transcribed neurology notes, threshold 3.0):
    venv-medcat/bin/python scripts/preprocess_us_notes.py \\
        --layout mtsamples \\
        --in-dir data/eval_corpora/mtsamples_neuro \\
        --out-dir data/eval_corpora/mtsamples_neuro_preprocessed \\
        --corpus mtsamples \\
        --min-relevance-score 3.0

Flat directory of *.txt (no filter):
    venv-medcat/bin/python scripts/preprocess_us_notes.py \\
        --layout flat \\
        --in-dir data/inbox/some_us_notes \\
        --out-dir data/inbox/some_us_notes_preprocessed \\
        --corpus custom_v1 \\
        --min-relevance-score 0.0

Existing universal-manifest corpus (in-place upgrade):
    venv-medcat/bin/python scripts/preprocess_us_notes.py \\
        --layout manifest \\
        --in-dir data/eval_corpora/synth_v3 \\
        --out-dir data/eval_corpora/synth_v3_preprocessed \\
        --corpus synth_v3 \\
        --min-relevance-score 0.0
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from services.us_note_preprocessing import preprocess_note  # noqa: E402


UNIVERSAL_MANIFEST_FIELDS = [
    "visit_id", "patient_id", "corpus", "corpus_version",
    "patient_dob", "patient_sex", "patient_race", "patient_ethnicity", "patient_zip3",
    "visit_date", "visit_number", "age_at_visit",
    "note_type", "note_template", "care_setting", "provider_persona", "specialty",
    "note_char_count", "note_word_count", "note_section_count", "note_language",
    "generator_model", "generator_seed",
    "generator_tokens_in", "generator_tokens_out", "generator_cost_usd",
    "phenotype_profile",
    "note_path", "gold_path", "semantic_plan_path", "raw_source_path",
    "gold_source", "gold_conformant", "silver_labeler", "review_status",
    "epilepsy_relevance_score",
    "created_at", "created_by", "ingest_batch", "notes",
]


# ─── Input layout loaders ────────────────────────────────────────────────

def _iter_mtsamples(in_dir: Path):
    """Yield (visit_id, patient_id, raw_text, source_row_dict) for each note."""
    # Load source manifest if present, for source_url passthrough
    source_manifest: dict[str, dict] = {}
    src_manifest = in_dir / "manifest.csv"
    if src_manifest.exists():
        with src_manifest.open() as fh:
            for row in csv.DictReader(fh):
                source_manifest[row["id"]] = row

    for sample_dir in sorted(in_dir.glob("mt_sample_*")):
        if not sample_dir.is_dir():
            continue
        note_path = sample_dir / "note.txt"
        if not note_path.exists():
            continue
        m = re.match(r"mt_sample_(\d+)", sample_dir.name)
        idx = int(m.group(1)) if m else 0
        visit_id = f"MT_V{idx:04d}"
        patient_id = f"MT_P{idx:04d}"
        raw = note_path.read_text(encoding="utf-8", errors="replace")
        src_row = source_manifest.get(sample_dir.name, {})
        yield visit_id, patient_id, raw, {
            "raw_source_path": str(note_path.relative_to(REPO_ROOT)),
            "source_url": src_row.get("source_url", ""),
            "note_type": "clinic_letter",
            "care_setting": "unknown",
            "provider_persona": "attending_neurologist",
            "specialty": "neurology",
        }


def _iter_flat(in_dir: Path):
    """Yield (visit_id, patient_id, raw_text, source_row_dict) for *.txt."""
    for i, p in enumerate(sorted(in_dir.glob("*.txt")), start=1):
        visit_id = p.stem
        patient_id = f"{p.stem}_pt"
        raw = p.read_text(encoding="utf-8", errors="replace")
        yield visit_id, patient_id, raw, {
            "raw_source_path": str(p.relative_to(REPO_ROOT)),
            "note_type": "unknown",
            "care_setting": "unknown",
            "provider_persona": "unknown",
            "specialty": "unknown",
        }


def _iter_manifest(in_dir: Path):
    """Yield rows from a universal-manifest corpus."""
    manifest = in_dir / "manifest.csv"
    if not manifest.exists():
        raise SystemExit(f"--layout manifest requires {manifest} to exist")
    with manifest.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            visit_id = row["visit_id"]
            patient_id = row["patient_id"]
            note_path = in_dir / row["note_path"]
            if not note_path.exists():
                print(f"  WARN: missing {note_path}, skipping", file=sys.stderr)
                continue
            raw = note_path.read_text(encoding="utf-8", errors="replace")
            yield visit_id, patient_id, raw, row


LAYOUTS = {
    "mtsamples": _iter_mtsamples,
    "flat": _iter_flat,
    "manifest": _iter_manifest,
}


# ─── Main ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _word_count(text: str) -> int:
    return len(text.split())


def _section_count(text: str) -> int:
    return len(re.findall(r"^\s*[A-Z][A-Za-z /]{2,40}:\s*$", text, re.M))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layout", required=True, choices=list(LAYOUTS.keys()))
    ap.add_argument("--in-dir", required=True,
                    help="Input directory (semantics depend on --layout)")
    ap.add_argument("--out-dir", required=True,
                    help="Output directory (documents/ + manifest.csv written here)")
    ap.add_argument("--corpus", required=True,
                    help="Corpus name (e.g. mtsamples, synth_v3, custom_v1)")
    ap.add_argument("--corpus-version", default="v1.0_preprocessed")
    ap.add_argument("--min-relevance-score", type=float, default=3.0,
                    help="Drop notes with score below this. 0.0 disables the filter.")
    ap.add_argument("--min-chars", type=int, default=300,
                    help="Drop notes shorter than this many chars.")
    ap.add_argument("--no-canonicalize-headers", action="store_true")
    ap.add_argument("--no-annotate-ilae", action="store_true")
    ap.add_argument("--no-annotate-drugs", action="store_true")
    args = ap.parse_args()

    in_dir = REPO_ROOT / args.in_dir if not Path(args.in_dir).is_absolute() else Path(args.in_dir)
    out_dir = REPO_ROOT / args.out_dir if not Path(args.out_dir).is_absolute() else Path(args.out_dir)
    docs_out = out_dir / "documents"
    docs_out.mkdir(parents=True, exist_ok=True)

    loader = LAYOUTS[args.layout]

    manifest_rows: list[dict] = []
    n_total = 0
    n_kept = 0
    n_excluded_short = 0
    n_excluded_low_relevance = 0
    ingest_batch = f"preproc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    for visit_id, patient_id, raw_text, meta in loader(in_dir):
        n_total += 1

        if len(raw_text) < args.min_chars:
            n_excluded_short += 1
            continue

        processed, stats = preprocess_note(
            raw_text,
            canonicalize_headers=not args.no_canonicalize_headers,
            annotate_ilae=not args.no_annotate_ilae,
            annotate_drugs=not args.no_annotate_drugs,
        )

        if args.min_relevance_score > 0 and stats.score < args.min_relevance_score:
            n_excluded_low_relevance += 1
            continue

        # Write processed note
        (docs_out / f"{visit_id}.txt").write_text(processed, encoding="utf-8")

        # Passthrough carriers from source layout
        notes_txt = (
            f"n_aed_mentions={stats.n_aed_mentions}, "
            f"n_ilae_annotated={stats.n_ilae_terms_annotated}, "
            f"n_drugs_annotated={stats.n_drugs_annotated}"
        )
        if meta.get("source_url"):
            notes_txt += f", source_url={meta['source_url']}"

        manifest_rows.append({
            "visit_id": visit_id,
            "patient_id": patient_id,
            "corpus": args.corpus,
            "corpus_version": args.corpus_version,
            "patient_dob": meta.get("patient_dob", ""),
            "patient_sex": meta.get("patient_sex", ""),
            "patient_race": meta.get("patient_race", ""),
            "patient_ethnicity": meta.get("patient_ethnicity", ""),
            "patient_zip3": meta.get("patient_zip3", ""),
            "visit_date": meta.get("visit_date", ""),
            "visit_number": meta.get("visit_number", 1),
            "age_at_visit": meta.get("age_at_visit", ""),
            "note_type": meta.get("note_type", "unknown"),
            "note_template": meta.get("note_template", ""),
            "care_setting": meta.get("care_setting", "unknown"),
            "provider_persona": meta.get("provider_persona", "unknown"),
            "specialty": meta.get("specialty", "neurology"),
            "note_char_count": len(processed),
            "note_word_count": _word_count(processed),
            "note_section_count": _section_count(processed),
            "note_language": "en",
            "generator_model": meta.get("generator_model", "human_transcribed"),
            "generator_seed": meta.get("generator_seed", ""),
            "generator_tokens_in": meta.get("generator_tokens_in", ""),
            "generator_tokens_out": meta.get("generator_tokens_out", ""),
            "generator_cost_usd": meta.get("generator_cost_usd", ""),
            "phenotype_profile": meta.get("phenotype_profile", "unknown"),
            "note_path": f"documents/{visit_id}.txt",
            "gold_path": meta.get("gold_path", ""),
            "semantic_plan_path": meta.get("semantic_plan_path", ""),
            "raw_source_path": meta.get("raw_source_path", ""),
            "gold_source": meta.get("gold_source", "unknown"),
            "gold_conformant": meta.get("gold_conformant", ""),
            "silver_labeler": meta.get("silver_labeler", ""),
            "review_status": "unreviewed",
            "epilepsy_relevance_score": stats.score,
            "created_at": _now_iso(),
            "created_by": "preprocess_us_notes.py v1.0",
            "ingest_batch": ingest_batch,
            "notes": notes_txt,
        })
        n_kept += 1

    manifest_path = out_dir / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=UNIVERSAL_MANIFEST_FIELDS)
        w.writeheader()
        w.writerows(manifest_rows)

    (out_dir / "run_metadata.json").write_text(json.dumps({
        "corpus": args.corpus,
        "corpus_version": args.corpus_version,
        "input_layout": args.layout,
        "input_dir": str(in_dir),
        "min_relevance_score": args.min_relevance_score,
        "min_chars": args.min_chars,
        "stages": {
            "canonicalize_headers": not args.no_canonicalize_headers,
            "annotate_ilae": not args.no_annotate_ilae,
            "annotate_drugs": not args.no_annotate_drugs,
        },
        "totals": {
            "total_seen": n_total,
            "kept": n_kept,
            "excluded_short": n_excluded_short,
            "excluded_low_relevance": n_excluded_low_relevance,
        },
        "ingest_batch": ingest_batch,
        "created_at": _now_iso(),
    }, indent=2), encoding="utf-8")

    print(f"[preprocess-us-notes] corpus={args.corpus} layout={args.layout}")
    print(f"  Processed:      {n_total}")
    print(f"  Kept:           {n_kept}")
    print(f"  Excluded short: {n_excluded_short}")
    print(f"  Excluded lo-rel: {n_excluded_low_relevance}")
    print(f"  Manifest:       {manifest_path}")
    print(f"  Docs dir:       {docs_out}")


if __name__ == "__main__":
    main()
