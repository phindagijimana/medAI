#!/usr/bin/env python3
"""
Phase 1a: Extract the concept-selection (CUI) seed list from ExECT-V2 dictionaries.

This produces ``references/exect_v2_cui_seed.csv`` with one row per unique UMLS
CUI referenced by the ExECT-V2 pipeline, together with provenance (which source
files referenced it) and a category tag derived from the file it came from.

Legal / attribution notes:
    * The ExECT-V2 dictionaries themselves are NOT copied into our tree; only
      CUIs, an SCTID (where directly present in the source), a single
      canonical preferred term, and count-of-surface-forms are emitted.
    * Surface strings from ExECT are treated as gray-area (UMLS-derived) and
      are NOT redistributed in the output.
    * See ``docs/MedCAT.md`` §Phase 1a and §8 for full rationale.

Author: MedAI-EPI (Vecta AI)
"""

from __future__ import annotations

import csv
import datetime as _dt
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Paths (all absolute to the repo root)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
EXECT_ROOT = REPO_ROOT / "references" / "exect_v2"
CUSTOM_UMLS_DIR = EXECT_ROOT / "Other" / "CustomUMLS"
ILAE_CSV = REPO_ROOT / "references" / "exect_v2_ilae_map.csv"
OUTPUT_CSV = REPO_ROOT / "references" / "exect_v2_cui_seed.csv"

CUI_RX = re.compile(r"^C\d{7}$")
CUI_ANY_RX = re.compile(r"C\d{7}")
SCTID_RX = re.compile(r"SNOMEDCT_US/[A-Z]{2}/(\d+)")

# ---------------------------------------------------------------------------
# Source-file catalog
# ---------------------------------------------------------------------------
# Each entry: (relative_path, category_tag, parser_key)
# parser_key values:
#   "cui_tab_surface"   -> "<CUI>\t<surface>"
#   "surface_slashcui"  -> "<surface>///<CUI>"
#   "lst_kv"            -> "<surface>\tCUI=<CUI>[\tPREF=<pref>][\tTUI=...][\tSTY=...]..."
#   "ilae_csv"          -> ILAE mapping CSV
CUSTOM_UMLS_SOURCES: List[Tuple[str, str, str]] = [
    ("Other/CustomUMLS/custom_umls.txt",           "custom_main",     "cui_tab_surface"),
    ("Other/CustomUMLS/custom_umlsNewMarkUp.txt",  "custom_main",     "surface_slashcui"),
    ("Other/CustomUMLS/epilepsy.txt",              "epilepsy",        "cui_tab_surface"),
    ("Other/CustomUMLS/seizure.txt",               "seizure",         "cui_tab_surface"),
    ("Other/CustomUMLS/seizureSlang.txt",          "seizure_slang",   "cui_tab_surface"),
    ("Other/CustomUMLS/anticonvultants.txt",       "anticonvulsant",  "cui_tab_surface"),
    ("Other/CustomUMLS/drugs.txt",                 "drug",            "cui_tab_surface"),
    ("Other/CustomUMLS/comorbidities.txt",         "comorbidity",     "cui_tab_surface"),
    ("Other/CustomUMLS/InvestResults.txt",         "invest_result",   "cui_tab_surface"),
    ("Other/CustomUMLS/BirthHistory.txt",          "birth_history",   "cui_tab_surface"),
]

# Top-level gazetteers; may or may not carry CUIs (inspected — most do via
# "surface\tCUI=Cxxxxxxx[\tPREF=...\tTUI=...\tSTY=...]").  Category is derived
# from filename; the gazetteers primarily add provenance (source_files) for
# CUIs already seen in the `.txt` dictionaries.
LST_SOURCES: List[Tuple[str, str, str]] = [
    ("epilepsy.lst",         "epilepsy",        "lst_kv"),
    ("seizure.lst",          "seizure",         "lst_kv"),
    ("drugs.lst",            "drug",            "lst_kv"),
    ("comorbidities.lst",    "comorbidity",     "lst_kv"),
    ("anticonvulscant.lst",  "anticonvulsant",  "lst_kv"),
]

# Category priority (lower = more specific).  When a CUI appears in multiple
# categories, the highest-priority category wins for the `category` column.
# All source files still get recorded in `exect_source_files`.
CATEGORY_PRIORITY: Dict[str, int] = {
    "ilae_classification": 0,
    "seizure_slang":       1,
    "seizure":             2,
    "epilepsy":            3,
    "anticonvulsant":      4,
    "invest_result":       5,
    "birth_history":       6,
    "comorbidity":         7,
    "drug":                8,
    "custom_main":         9,
}

# Category -> comma-separated MedAI-EPI v0.2.1 schema field hints.
CATEGORY_SCHEMA_HINTS: Dict[str, str] = {
    "epilepsy":            "epilepsy.type,epilepsy.syndrome",
    "seizure":             "clinical_seizure.predominant_seizure_type",
    "seizure_slang":       "clinical_seizure.predominant_seizure_type",
    "anticonvulsant":      "medication.current_asms,medication.past_asms",
    "drug":                "medication.current_asms,medication.past_asms",
    "comorbidity":         "comorbidities",
    "invest_result":       "eeg.findings,mri.findings",
    "birth_history":       "birth_history",
    "custom_main":         "",  # heterogeneous; deferred to Phase 1b
    "ilae_classification": "clinical_seizure.predominant_seizure_type,clinical_seizure.onset",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CuiRecord:
    cui: str
    snomed_ct_id: Set[str] = field(default_factory=set)
    # Explicit PREF= labels seen in `.lst` or ILAE CSV (highest trust).
    explicit_pref_candidates: List[str] = field(default_factory=list)
    # Surface-form fallbacks used only when no explicit PREF= is ever seen.
    surface_pref_candidates: List[str] = field(default_factory=list)
    categories_seen: Set[str] = field(default_factory=set)
    source_files: Set[str] = field(default_factory=set)
    surface_forms: Set[str] = field(default_factory=set)


class ParseStats:
    def __init__(self) -> None:
        self.per_file_raw_mentions: Counter = Counter()
        self.per_file_unique_cuis: Dict[str, Set[str]] = defaultdict(set)
        self.malformed_lines: Counter = Counter()
        self.empty_or_header_lines: Counter = Counter()

    def note_raw_mention(self, source_file: str, cui: str) -> None:
        self.per_file_raw_mentions[source_file] += 1
        self.per_file_unique_cuis[source_file].add(cui)

    def note_malformed(self, source_file: str) -> None:
        self.malformed_lines[source_file] += 1


# ---------------------------------------------------------------------------
# Line-level parsers
# ---------------------------------------------------------------------------

def _norm_pref(text: str) -> str:
    """Light normalization for candidate preferred-term ranking (no external
    strings are emitted verbatim beyond the single chosen preferred_term)."""
    return text.strip()


def parse_cui_tab_surface(line: str) -> Optional[Tuple[str, str]]:
    """<CUI>\\t<surface>  ->  (cui, surface).  Returns None if malformed."""
    parts = line.rstrip("\r\n").split("\t")
    if len(parts) < 2:
        return None
    cui = parts[0].strip()
    surface = parts[1].strip()
    if not CUI_RX.match(cui) or not surface:
        return None
    return cui, surface


def parse_surface_slashcui(line: str) -> Optional[Tuple[str, str]]:
    """<surface>///<CUI>  ->  (cui, surface)."""
    line = line.rstrip("\r\n")
    if "///" not in line:
        return None
    surface, _, cui = line.rpartition("///")
    cui = cui.strip()
    surface = surface.strip()
    if not CUI_RX.match(cui) or not surface:
        return None
    return cui, surface


_LST_KV_RX = re.compile(r"(CUI|PREF|TUI|STY)=([^\t]*?)(?=(?:\s+(?:CUI|PREF|TUI|STY)=)|$)")


def parse_lst_kv(line: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """<surface>\\tCUI=<CUI>[\\tPREF=<pref>]...  ->  (cui, surface, pref?).

    Tolerates rows where CUI=/PREF= markers are separated by spaces instead
    of tabs (a small number of malformed rows in comorbidities.lst).
    """
    line = line.rstrip("\r\n")
    if not line:
        return None
    # Split off surface: everything before the first CUI= marker (with tab
    # or space).  If there's no CUI= at all, this is not a parseable row.
    m = re.search(r"[\t ]+CUI=", line)
    if not m:
        return None
    surface = line[: m.start()].strip()
    kv_blob = line[m.start():].strip()
    if not surface:
        return None
    cui: Optional[str] = None
    pref: Optional[str] = None
    for kv in _LST_KV_RX.finditer(kv_blob):
        key = kv.group(1)
        val = kv.group(2).strip().rstrip("\t").strip()
        if key == "CUI" and cui is None:
            cui = val
        elif key == "PREF" and pref is None:
            pref = val
    if not cui or not CUI_RX.match(cui):
        return None
    return cui, surface, (pref if pref else None)


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

def _add_mention(
    records: Dict[str, CuiRecord],
    stats: ParseStats,
    cui: str,
    surface: str,
    pref: Optional[str],
    sctid: Optional[str],
    source_file: str,
    category: str,
) -> None:
    rec = records.get(cui)
    if rec is None:
        rec = CuiRecord(cui=cui)
        records[cui] = rec
    rec.source_files.add(source_file)
    rec.categories_seen.add(category)
    if surface:
        rec.surface_forms.add(surface.lower().strip())
    if pref:
        rec.explicit_pref_candidates.append(_norm_pref(pref))
    if surface:
        # Kept only as a fallback; ranking prefers explicit PREF= candidates.
        rec.surface_pref_candidates.append(_norm_pref(surface))
    if sctid:
        rec.snomed_ct_id.add(sctid)
    stats.note_raw_mention(source_file, cui)


def parse_flat_file(
    records: Dict[str, CuiRecord],
    stats: ParseStats,
    path: Path,
    rel_source: str,
    category: str,
    parser_key: str,
) -> None:
    if not path.exists():
        print(f"[warn] missing source: {rel_source}", file=sys.stderr)
        return
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            if not raw.strip():
                stats.empty_or_header_lines[rel_source] += 1
                continue
            parsed = None
            pref: Optional[str] = None
            if parser_key == "cui_tab_surface":
                out = parse_cui_tab_surface(raw)
                if out is not None:
                    parsed = out  # (cui, surface)
            elif parser_key == "surface_slashcui":
                out = parse_surface_slashcui(raw)
                if out is not None:
                    parsed = out
            elif parser_key == "lst_kv":
                out = parse_lst_kv(raw)
                if out is not None:
                    parsed = (out[0], out[1])
                    pref = out[2]
            else:
                raise ValueError(f"unknown parser_key: {parser_key}")
            if parsed is None:
                stats.note_malformed(rel_source)
                continue
            cui, surface = parsed
            _add_mention(
                records=records,
                stats=stats,
                cui=cui,
                surface=surface,
                pref=pref,
                sctid=None,
                source_file=rel_source,
                category=category,
            )


def parse_ilae_csv(
    records: Dict[str, CuiRecord],
    stats: ParseStats,
    csv_path: Path,
) -> None:
    """ILAE map CSV: Column1=ILAE term, Column2=UMLS-suggested term,
    Column3=CUI, Column4=`Term [ATOM/SNOMEDCT_US/PT/<SCTID>]` (may be
    'No'/'NaN'/blank).  Only rows with a valid CUI in Column3 are kept.
    Column4 (the SCTID / SNOMED preferred-atom string) IS public factual
    data attached to the CUI in the published XLSX so we may keep the SCTID
    plus the SNOMED-preferred label (Column4 pre-bracket)."""
    rel_source = "references/exect_v2_ilae_map.csv"
    if not csv_path.exists():
        print(f"[warn] missing ILAE CSV: {csv_path}", file=sys.stderr)
        return
    df = pd.read_csv(csv_path)
    if "Column3" not in df.columns:
        print("[warn] ILAE CSV missing expected 'Column3'", file=sys.stderr)
        return
    for _, row in df.iterrows():
        raw_cui = str(row.get("Column3", "") or "").strip()
        if not CUI_RX.match(raw_cui):
            if raw_cui and raw_cui.lower() not in ("nan", ""):
                stats.note_malformed(rel_source)
            else:
                stats.empty_or_header_lines[rel_source] += 1
            continue

        col1 = str(row.get("Column1", "") or "").strip()
        col2 = str(row.get("Column2", "") or "").strip()
        col4 = str(row.get("Column4", "") or "").strip()

        # Extract SCTID from Column4 if present
        sctid: Optional[str] = None
        m = SCTID_RX.search(col4)
        if m:
            sctid = m.group(1)

        # Preferred term choice: prefer the SNOMED-preferred label from
        # Column4 (public factual data in the XLSX), else the ILAE Column1
        # term, else the UMLS Column2 term.
        pref: Optional[str] = None
        if col4 and col4.lower() not in ("no", "nan"):
            # Strip trailing "[A.../SNOMEDCT_US/.../SCTID]"
            pref = re.sub(r"\s*\[[^\]]+\]\s*$", "", col4).strip() or None
        if not pref and col1 and col1.lower() != "nan":
            pref = col1
        if not pref and col2 and col2.lower() != "nan":
            pref = col2

        surface = col1 if col1.lower() != "nan" else (col2 if col2.lower() != "nan" else (pref or ""))

        _add_mention(
            records=records,
            stats=stats,
            cui=raw_cui,
            surface=surface,
            pref=pref,
            sctid=sctid,
            source_file=rel_source,
            category="ilae_classification",
        )


# ---------------------------------------------------------------------------
# Preferred-term ranking + category resolution
# ---------------------------------------------------------------------------

_PARENS_SUFFIX_RX = re.compile(r"\s*\([^)]+\)\s*$")
_TRAILING_CODE_RX = re.compile(r"\s*\[[^\]]+\]\s*$")


def _prefer_score(text: str) -> Tuple[int, int, int]:
    """Rank candidate preferred terms.  Lower tuple = better.

    Heuristics (in priority order):
      1) Strings without a trailing "(product)" / "(substance)" / "(disorder)"
         suffix are more canonical than ones with those tags.
      2) Prefer strings without any parenthetical/bracketed suffix.
      3) Prefer moderate length (12..60 chars) over very short abbreviations
         or very long paraphrases.
      4) Prefer strings whose first character is uppercase (SNOMED-style PT).
    """
    t = text.strip()
    tl = t.lower()
    has_typed_suffix = int(any(
        tl.endswith(sfx) for sfx in (
            "(product)", "(substance)", "(disorder)", "(finding)",
            "(medicinal product)", "(qualifier value)",
        )
    ))
    has_paren = int(bool(_PARENS_SUFFIX_RX.search(t)) or bool(_TRAILING_CODE_RX.search(t)))
    n = len(t)
    length_penalty = 0 if 12 <= n <= 60 else (1 if n <= 80 else 2)
    upper_start = 0 if t[:1].isupper() else 1
    return (has_typed_suffix, has_paren, length_penalty, upper_start, n)


def _best_preferred_term(candidates: Iterable[str]) -> str:
    """Choose the most canonical-looking preferred term.  Uses only structural
    heuristics on the candidate strings; the chosen string will be a single
    label (SNOMED-preferred where available) and is treated as public factual
    data.  We do NOT emit any of the other candidates."""
    seen: List[str] = []
    seen_lower: Set[str] = set()
    for c in candidates:
        cl = c.strip().lower()
        if not cl or cl in seen_lower:
            continue
        seen_lower.add(cl)
        seen.append(c.strip())
    if not seen:
        return ""
    seen.sort(key=_prefer_score)
    return seen[0]


def _resolve_category(cats: Set[str]) -> str:
    if not cats:
        return "custom_main"
    return sorted(cats, key=lambda c: CATEGORY_PRIORITY.get(c, 99))[0]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_seed() -> Tuple[Dict[str, CuiRecord], ParseStats]:
    records: Dict[str, CuiRecord] = {}
    stats = ParseStats()

    # 1) CustomUMLS/*.txt
    for rel, category, key in CUSTOM_UMLS_SOURCES:
        parse_flat_file(records, stats, EXECT_ROOT / rel, rel, category, key)

    # 2) Top-level *.lst gazetteers (add PREF= when available)
    for rel, category, key in LST_SOURCES:
        parse_flat_file(records, stats, EXECT_ROOT / rel, rel, category, key)

    # 3) ILAE map CSV (already inside our tree)
    parse_ilae_csv(records, stats, ILAE_CSV)

    return records, stats


def write_seed_csv(
    records: Dict[str, CuiRecord],
    output_path: Path,
) -> Tuple[int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    today = _dt.date.today().isoformat()
    header_comment = (
        f"# ExECT-V2 CUI seed extracted {today} — concept-selection provenance"
        " only; synonyms are NOT redistributed. See docs/MedCAT.md §Phase 1a."
    )

    field_names = [
        "cui",
        "snomed_ct_id",
        "category",
        "preferred_term",
        "exect_source_files",
        "n_surface_forms_in_exect",
        "schema_field_hints",
    ]

    empty_pref = 0
    empty_sctid = 0
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(header_comment + "\n")
        writer = csv.DictWriter(fh, fieldnames=field_names)
        writer.writeheader()
        for cui in sorted(records.keys()):
            rec = records[cui]
            category = _resolve_category(rec.categories_seen)
            # Prefer SNOMED-style PREF= labels; fall back to surface forms
            # only when we never saw an explicit PREF=.
            pref_pool = rec.explicit_pref_candidates or rec.surface_pref_candidates
            pref = _best_preferred_term(pref_pool)
            sctid = ";".join(sorted(rec.snomed_ct_id))
            if not pref:
                empty_pref += 1
            if not sctid:
                empty_sctid += 1
            writer.writerow({
                "cui": cui,
                "snomed_ct_id": sctid,
                "category": category,
                "preferred_term": pref,
                "exect_source_files": ";".join(sorted(rec.source_files)),
                "n_surface_forms_in_exect": len(rec.surface_forms),
                "schema_field_hints": CATEGORY_SCHEMA_HINTS.get(category, ""),
            })
    return empty_pref, empty_sctid


def verify_and_report(
    records: Dict[str, CuiRecord],
    stats: ParseStats,
    output_path: Path,
    empty_pref: int,
    empty_sctid: int,
) -> None:
    # Reload with pandas for a shape check + sanity stats.
    df = pd.read_csv(output_path, comment="#")
    print("=" * 72)
    print("PARSE STATS")
    print("=" * 72)
    all_sources = sorted(
        set(list(stats.per_file_raw_mentions.keys())
            + list(stats.malformed_lines.keys())
            + list(stats.empty_or_header_lines.keys()))
    )
    total_raw = 0
    for src in all_sources:
        raw = stats.per_file_raw_mentions.get(src, 0)
        uniq = len(stats.per_file_unique_cuis.get(src, set()))
        bad = stats.malformed_lines.get(src, 0)
        empt = stats.empty_or_header_lines.get(src, 0)
        total_raw += raw
        print(f"  {src:50s}  raw={raw:6d}  unique_cuis={uniq:5d}  malformed={bad:4d}  empty/hdr={empt:4d}")
    print(f"  TOTAL raw CUI mentions across files: {total_raw}")
    print()

    # Dedup summary
    unique_cuis = len(records)
    multi_source = sum(1 for r in records.values() if len(r.source_files) >= 2)
    print(f"Unique CUIs after dedup:              {unique_cuis}")
    print(f"CUIs appearing in >= 2 source files:  {multi_source}")
    print()

    # CSV summary
    print("CSV shape:", df.shape)
    print("Category distribution:")
    for cat, n in df["category"].value_counts().items():
        print(f"  {cat:24s} {n}")
    print()
    print(f"Rows with empty snomed_ct_id: {int(df['snomed_ct_id'].isna().sum() + (df['snomed_ct_id'].astype(str) == '').sum())}")
    print(f"Rows with empty preferred_term (should be 0): {empty_pref}")

    # Sanity: CUI format
    bad_cui = df[~df["cui"].astype(str).str.match(r"^C\d{7}$")]
    print(f"Rows with malformed CUI: {len(bad_cui)}")
    if not bad_cui.empty:
        print(bad_cui.head())

    # Spot-check 10 CUIs
    import random
    random.seed(42)
    sample = df.sample(n=min(10, len(df)), random_state=42)
    print("\nSpot-check 10 CUIs:")
    for _, row in sample.iterrows():
        print(f"  {row['cui']}  [{row['category']:20s}]  pref={row['preferred_term'][:60]}")


def main() -> int:
    print(f"Repo root: {REPO_ROOT}")
    print(f"ExECT root: {EXECT_ROOT}")
    if not EXECT_ROOT.exists():
        print("[FATAL] references/exect_v2/ not found", file=sys.stderr)
        return 2
    records, stats = build_seed()
    empty_pref, empty_sctid = write_seed_csv(records, OUTPUT_CSV)
    verify_and_report(records, stats, OUTPUT_CSV, empty_pref, empty_sctid)
    size = OUTPUT_CSV.stat().st_size
    print(f"\nWrote: {OUTPUT_CSV}  ({size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
