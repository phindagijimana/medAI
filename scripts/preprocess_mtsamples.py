"""Preprocess MTSamples neurology notes for epilepsy phenotyping evaluation.

Pipeline stages:
  A. Epilepsy relevance filter (density + AED mentions + HPI position)
  B. Section header canonicalization (CC: → Chief Complaint:, HX: → HPI:)
  C. Modern ILAE terminology annotation (grand mal → grand mal (generalized tonic-clonic))
  D. Brand-generic drug annotation (Dilantin → Dilantin (phenytoin))
  E. Universal manifest.csv emission

Input:  data/eval_corpora/mtsamples_neuro/mt_sample_XXXX/note.txt (78 notes)
Output: data/eval_corpora/mtsamples_neuro_preprocessed/
          ├── manifest.csv                          (universal schema v1.0)
          ├── documents/{visit_id}.txt              (normalized notes)
          └── README.md

Usage:
    venv-medcat/bin/python scripts/preprocess_mtsamples.py \\
        --in-dir data/eval_corpora/mtsamples_neuro \\
        --out-dir data/eval_corpora/mtsamples_neuro_preprocessed \\
        --min-relevance-score 3.0
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ─── Stage A: Relevance scoring ──────────────────────────────────────────

_EPILEPSY_KEYWORDS = re.compile(
    r"\b(epilep|seizur|convuls|ictal|antiepilep|antiseizure|anticonvuls|"
    r"postictal|EEG|EMU|LTM|status\s+epilepticus|SE\b)",
    re.IGNORECASE,
)

_AED_KEYWORDS = re.compile(
    r"\b(lamotrigine|Lamictal|levetiracetam|Keppra|carbamazepine|Tegretol|"
    r"valproate|valproic|Depakote|Depakene|topiramate|Topamax|phenytoin|"
    r"Dilantin|zonisamide|Zonegran|oxcarbazepine|Trileptal|lacosamide|Vimpat|"
    r"brivaracetam|Briviact|perampanel|Fycompa|clobazam|Onfi|phenobarbital|"
    r"gabapentin|Neurontin|pregabalin|Lyrica|ethosuximide|Zarontin|"
    r"rufinamide|Banzel|clonazepam|Klonopin|midazolam|Nayzilam|"
    r"acetazolamide|Diamox|felbamate|Felbatol|primidone|Mysoline|"
    r"eslicarbazepine|Aptiom|cenobamate|Xcopri)\b",
    re.IGNORECASE,
)

_HPI_SECTION = re.compile(
    r"\b(CC:|Chief\s+Complaint:|HX:|HPI:|History\s+of\s+Present\s+Illness:|Reason\s+for\s+Visit:)",
    re.IGNORECASE,
)


def compute_relevance_score(text: str) -> tuple[float, dict]:
    """Return (score, details). Score >= 3.0 considered epilepsy-primary."""
    epi_hits = _EPILEPSY_KEYWORDS.findall(text)
    aed_hits = _AED_KEYWORDS.findall(text)
    n_chars = max(len(text), 1)

    density = (len(epi_hits) / n_chars) * 1000  # per 1000 chars

    # HPI-position boost: epilepsy mentioned near start (within first 40% of note)
    hpi_boost = 1.0
    hpi_match = _HPI_SECTION.search(text)
    if hpi_match:
        # Check if any epilepsy keyword appears within 500 chars of HPI marker
        window = text[hpi_match.start():hpi_match.start() + 500]
        if _EPILEPSY_KEYWORDS.search(window):
            hpi_boost = 2.0

    aed_boost = min(len(aed_hits), 5) * 0.5  # cap at 2.5

    score = density * hpi_boost + aed_boost

    return score, {
        "n_epilepsy_keywords": len(epi_hits),
        "n_aed_mentions": len(aed_hits),
        "n_chars": n_chars,
        "density_per_1k_chars": round(density, 3),
        "hpi_boost": hpi_boost,
        "aed_boost": aed_boost,
        "score": round(score, 3),
    }


# ─── Stage B: Section header canonicalization ────────────────────────────

_HEADER_MAP = [
    (re.compile(r"^\s*CC\s*:", re.M), "Chief Complaint:"),
    (re.compile(r"^\s*HX\s*:", re.M), "History of Present Illness:"),
    (re.compile(r"^\s*PMH\s*:", re.M), "Past Medical History:"),
    (re.compile(r"^\s*PMHX\s*:", re.M), "Past Medical History:"),
    (re.compile(r"^\s*BIRTH\s+HX\s*:", re.M), "Birth History:"),
    (re.compile(r"^\s*SHX\s*:", re.M), "Social History:"),
    (re.compile(r"^\s*FHX\s*:", re.M), "Family History:"),
    (re.compile(r"^\s*MEDS\s*:", re.M), "Medications:"),
    (re.compile(r"^\s*EXAM\s*:", re.M), "Physical Examination:"),
    (re.compile(r"^\s*Impression\s*:", re.M), "Assessment:"),
    (re.compile(r"^\s*COURSE\s*:", re.M), "Clinical Course:"),
    (re.compile(r"^\s*Studies\s*:", re.M), "Diagnostic Studies:"),
    (re.compile(r"^\s*A/P\s*:", re.M), "Assessment and Plan:"),
    (re.compile(r"^\s*SUMMARY\s*:", re.M), "Assessment and Plan:"),
    (re.compile(r"^\s*ROS\s*:", re.M), "Review of Systems:"),
]


def canonicalize_sections(text: str) -> tuple[str, int]:
    """Normalize section headers to canonical US EHR forms. Return (new_text, n_replacements)."""
    n = 0
    for pattern, replacement in _HEADER_MAP:
        text, count = pattern.subn(replacement, text)
        n += count
    return text, n


# ─── Stage C: Modern ILAE terminology annotation ─────────────────────────

_ILAE_LEGACY_TO_MODERN = [
    (re.compile(r"\bpsychomotor\s+seizures?\b", re.I),
     "psychomotor seizures (focal impaired awareness seizures)"),
    (re.compile(r"\bcomplex\s+partial\s+seizures?\b", re.I),
     "complex partial seizures (focal impaired awareness seizures)"),
    (re.compile(r"\bsimple\s+partial\s+seizures?\b", re.I),
     "simple partial seizures (focal aware seizures)"),
    (re.compile(r"\bpetit\s+mal\b", re.I),
     "petit mal (typical absence)"),
    (re.compile(r"\bgrand\s+mal\b", re.I),
     "grand mal (generalized tonic-clonic)"),
    (re.compile(r"\bsecondarily\s+generali[sz]ed\b", re.I),
     "secondarily generalized (focal to bilateral tonic-clonic)"),
]


def annotate_ilae_terms(text: str) -> tuple[str, int]:
    """Add modern ILAE 2017 equivalents alongside historical terms. Non-destructive."""
    n = 0
    for pattern, replacement in _ILAE_LEGACY_TO_MODERN:
        # Only replace if the modern equivalent isn't already present
        if replacement not in text:
            text, count = pattern.subn(replacement, text)
            n += count
    return text, n


# ─── Stage D: Brand-generic drug annotation ──────────────────────────────

_BRAND_TO_GENERIC = [
    (re.compile(r"\bDilantin\b(?!\s*\()", re.I), "Dilantin (phenytoin)"),
    (re.compile(r"\bTegretol\b(?!\s*\()", re.I), "Tegretol (carbamazepine)"),
    (re.compile(r"\bDepakene\b(?!\s*\()", re.I), "Depakene (valproic acid)"),
    (re.compile(r"\bDepakote\b(?!\s*\()", re.I), "Depakote (divalproex)"),
    (re.compile(r"\bKeppra\b(?!\s*\()", re.I), "Keppra (levetiracetam)"),
    (re.compile(r"\bLamictal\b(?!\s*\()", re.I), "Lamictal (lamotrigine)"),
    (re.compile(r"\bTopamax\b(?!\s*\()", re.I), "Topamax (topiramate)"),
    (re.compile(r"\bTrileptal\b(?!\s*\()", re.I), "Trileptal (oxcarbazepine)"),
    (re.compile(r"\bVimpat\b(?!\s*\()", re.I), "Vimpat (lacosamide)"),
    (re.compile(r"\bZonegran\b(?!\s*\()", re.I), "Zonegran (zonisamide)"),
    (re.compile(r"\bBanzel\b(?!\s*\()", re.I), "Banzel (rufinamide)"),
    (re.compile(r"\bAptiom\b(?!\s*\()", re.I), "Aptiom (eslicarbazepine)"),
    (re.compile(r"\bFycompa\b(?!\s*\()", re.I), "Fycompa (perampanel)"),
    (re.compile(r"\bBriviact\b(?!\s*\()", re.I), "Briviact (brivaracetam)"),
    (re.compile(r"\bXcopri\b(?!\s*\()", re.I), "Xcopri (cenobamate)"),
    (re.compile(r"\bOnfi\b(?!\s*\()", re.I), "Onfi (clobazam)"),
    (re.compile(r"\bMysoline\b(?!\s*\()", re.I), "Mysoline (primidone)"),
    (re.compile(r"\bDiamox\b(?!\s*\()", re.I), "Diamox (acetazolamide)"),
    (re.compile(r"\bFelbatol\b(?!\s*\()", re.I), "Felbatol (felbamate)"),
    (re.compile(r"\bZarontin\b(?!\s*\()", re.I), "Zarontin (ethosuximide)"),
    (re.compile(r"\bNeurontin\b(?!\s*\()", re.I), "Neurontin (gabapentin)"),
    (re.compile(r"\bLyrica\b(?!\s*\()", re.I), "Lyrica (pregabalin)"),
    (re.compile(r"\bKlonopin\b(?!\s*\()", re.I), "Klonopin (clonazepam)"),
    (re.compile(r"\bNayzilam\b(?!\s*\()", re.I), "Nayzilam (midazolam)"),
]


def annotate_drug_names(text: str) -> tuple[str, int]:
    """Add generic name in parens after brand names. Skip if already annotated."""
    n = 0
    for pattern, replacement in _BRAND_TO_GENERIC:
        text, count = pattern.subn(replacement, text)
        n += count
    return text, n


# ─── Main preprocessing pipeline ─────────────────────────────────────────

def process_one_note(text: str) -> tuple[str, dict]:
    """Apply all preprocessing stages. Return (processed_text, stats)."""
    stats = {}
    score, relevance_stats = compute_relevance_score(text)
    stats.update(relevance_stats)

    text, n_sections = canonicalize_sections(text)
    stats["n_section_headers_normalized"] = n_sections

    text, n_ilae = annotate_ilae_terms(text)
    stats["n_ilae_terms_annotated"] = n_ilae

    text, n_drugs = annotate_drug_names(text)
    stats["n_drugs_annotated"] = n_drugs

    return text, stats


def _visit_id_from_sample(doc_id: str) -> str:
    """mt_sample_0004 → MT_V0004."""
    m = re.match(r"mt_sample_(\d+)", doc_id)
    if m:
        return f"MT_V{int(m.group(1)):04d}"
    return doc_id


def _patient_id_from_sample(doc_id: str) -> str:
    """MTSamples has one visit per patient. Use doc-derived patient ID."""
    m = re.match(r"mt_sample_(\d+)", doc_id)
    if m:
        return f"MT_P{int(m.group(1)):04d}"
    return doc_id + "_pt"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", default="data/eval_corpora/mtsamples_neuro")
    ap.add_argument("--out-dir", default="data/eval_corpora/mtsamples_neuro_preprocessed")
    ap.add_argument("--min-relevance-score", type=float, default=3.0,
                    help="Notes scoring below this threshold are excluded")
    ap.add_argument("--min-chars", type=int, default=300)
    args = ap.parse_args()

    in_dir = REPO_ROOT / args.in_dir
    out_dir = REPO_ROOT / args.out_dir
    docs_out = out_dir / "documents"
    docs_out.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    n_total = 0
    n_kept = 0
    n_excluded_low_relevance = 0
    n_excluded_short = 0

    for sample_dir in sorted(in_dir.glob("mt_sample_*")):
        if not sample_dir.is_dir():
            continue
        note_path = sample_dir / "note.txt"
        if not note_path.exists():
            continue
        n_total += 1

        raw_text = note_path.read_text(encoding="utf-8", errors="replace")

        # Length filter
        if len(raw_text) < args.min_chars:
            n_excluded_short += 1
            continue

        processed, stats = process_one_note(raw_text)

        # Relevance filter
        if stats["score"] < args.min_relevance_score:
            n_excluded_low_relevance += 1
            continue

        visit_id = _visit_id_from_sample(sample_dir.name)
        patient_id = _patient_id_from_sample(sample_dir.name)

        # Save processed note
        (docs_out / f"{visit_id}.txt").write_text(processed, encoding="utf-8")

        # Get metadata from original manifest if it exists
        source_url = None
        orig_manifest = in_dir / "manifest.csv"
        if orig_manifest.exists():
            with orig_manifest.open() as fh:
                for row in csv.DictReader(fh):
                    if row.get("id") == sample_dir.name:
                        source_url = row.get("source_url")
                        break

        manifest_rows.append({
            "visit_id": visit_id,
            "patient_id": patient_id,
            "corpus": "mtsamples",
            "corpus_version": "v1.0_preprocessed",
            "patient_dob": "",
            "patient_sex": "",
            "patient_race": "",
            "patient_ethnicity": "",
            "patient_zip3": "",
            "visit_date": "",
            "visit_number": 1,
            "age_at_visit": "",
            "note_type": "clinic_letter",
            "note_template": "",
            "care_setting": "unknown",
            "provider_persona": "attending_neurologist",
            "specialty": "neurology",
            "note_char_count": len(processed),
            "note_word_count": len(processed.split()),
            "note_section_count": stats["n_section_headers_normalized"],
            "note_language": "en",
            "generator_model": "human_transcribed",
            "generator_seed": "",
            "generator_tokens_in": "",
            "generator_tokens_out": "",
            "generator_cost_usd": "",
            "phenotype_profile": "unknown",
            "note_path": f"documents/{visit_id}.txt",
            "gold_path": "",  # populated after silver-labeling
            "semantic_plan_path": "",
            "raw_source_path": str(note_path.relative_to(REPO_ROOT)),
            "gold_source": "gpt_silver",
            "gold_conformant": "",
            "silver_labeler": "",
            "review_status": "unreviewed",
            "epilepsy_relevance_score": stats["score"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "preprocess_mtsamples.py v1.0",
            "ingest_batch": f"mtsamples_preproc_{datetime.now().strftime('%Y%m%d')}",
            "notes": (
                f"n_aed_mentions={stats['n_aed_mentions']}, "
                f"n_ilae_annotated={stats['n_ilae_terms_annotated']}, "
                f"n_drugs_annotated={stats['n_drugs_annotated']}, "
                f"source_url={source_url or ''}"
            ),
        })
        n_kept += 1

    # Write universal manifest
    manifest_path = out_dir / "manifest.csv"
    if manifest_rows:
        with manifest_path.open("w") as fh:
            w = csv.DictWriter(fh, fieldnames=list(manifest_rows[0].keys()))
            w.writeheader()
            w.writerows(manifest_rows)

    # Write README
    (out_dir / "README.md").write_text(
        f"# MTSamples Preprocessed Corpus\n\n"
        f"**Source:** `{args.in_dir}` (78 MTSamples neurology notes)\n"
        f"**Pipeline:** `scripts/preprocess_mtsamples.py`\n"
        f"**Schema:** `docs/CORPUS_MANIFEST_SCHEMA.md`\n\n"
        f"## Stats\n\n"
        f"- Total input notes: {n_total}\n"
        f"- Excluded (too short, < {args.min_chars} chars): {n_excluded_short}\n"
        f"- Excluded (low epilepsy relevance, score < {args.min_relevance_score}): {n_excluded_low_relevance}\n"
        f"- **Kept: {n_kept}**\n\n"
        f"## Preprocessing stages applied\n\n"
        f"1. Epilepsy relevance filter (density × HPI-position boost + AED-mention bonus)\n"
        f"2. Section header canonicalization (CC:→Chief Complaint:, HX:→HPI:, etc.)\n"
        f"3. Modern ILAE 2017 terminology annotation (grand mal → grand mal (generalized tonic-clonic))\n"
        f"4. Brand-generic drug annotation (Dilantin → Dilantin (phenytoin))\n\n"
        f"## Next steps\n\n"
        f"1. Silver-label with `scripts/silver_label_mtsamples.py` pointing at `{args.out_dir}`\n"
        f"2. Score B1' MedCAT+Rules against silver labels\n\n"
        f"Attribution: mtsamples.com (research use, attribution required)\n",
        encoding="utf-8",
    )

    print(f"[mtsamples-preproc] Processed {n_total} notes")
    print(f"  → Kept:                       {n_kept}")
    print(f"  → Excluded (too short):       {n_excluded_short}")
    print(f"  → Excluded (low relevance):   {n_excluded_low_relevance}")
    print(f"  → Manifest:                   {manifest_path}")
    print(f"  → Preprocessed docs:          {docs_out}")


if __name__ == "__main__":
    main()
