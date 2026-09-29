"""Phase 1c — Build the MedAI-EPI custom MedCAT Concept Database (CDB).

Reads :mod:`rules.epilepsy_ontology` (Phase 1b output, 24 enum ontologies +
4 supplementary ontologies, 255 total ``ConceptEntry`` rows) and emits a
MedCAT 2.x CDB compatible with :class:`medcat.cat.CAT`.

Outputs
-------
- ``data/medcat_cdb_epilepsy/concepts.csv`` — the intermediate concept CSV
  fed into :class:`medcat.model_creation.cdb_maker.CDBMaker`. One row per
  (cui, synonym).
- ``data/medcat_cdb_epilepsy/cdb/`` — the built CDB in folder format
  (dill-serialised parts, native MedCAT 2.x layout). MedCAT's ``CDB.load``
  auto-detects folder vs. zip.
- ``data/medcat_cdb_epilepsy/cdb.zip`` — same CDB zipped for portability.
- ``data/medcat_cdb_epilepsy/build_report.json`` — build stats.

Design decisions
----------------
- **Placeholder CUIs**: entries with neither ``cui`` nor ``sctid`` in the
  ontology (e.g. ``RULES_ONLY`` enum values, catch-all "not_documented"
  rows) are given a synthetic CUI of the form
  ``X-<Enum>-<value>`` so their synonyms are still matchable. These are
  clearly namespaced (leading ``X-``) so a downstream cleanup pass can
  filter them out before UMLS-Full merge (Phase 1d).
- **Semantic types (type_ids)**: mapped 1:1 from enum name → ``T-<Enum>``.
  We use our own T- prefix so we never collide with UMLS TUIs. Supplementary
  ontologies (Medication, EtiologyDetails, Comorbidity, BirthHistory) also
  get their own T- prefixes.
- **name_status**: ``P`` for the primary label (canonical ``entry.label``),
  ``A`` for aliases (each synonym in ``entry.synonyms``). If the label
  itself is not already in the synonyms list, we add it as ``P``.
- **ontologies**: ``SNOMED`` if ``sctid`` is present, else ``MEDAI_EPI``
  for placeholder concepts.

Idempotency: rerunning overwrites the CSV and CDB atomically. No state is
kept between runs.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rules.epilepsy_ontology import (  # noqa: E402
    ConceptEntry,
    RULES_ONLY_ENUMS,
    all_enum_ontologies,
    supplementary_ontologies,
    total_concept_count,
)


DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "medcat_cdb_epilepsy"

# Phase 2 fix (§Deliverable 7): the six RULES_ONLY enums are compound-derived
# from linguistic context (ConText) or cross-modality comparison and NOT
# span-linkable. Including their placeholder ``X-<Enum>-<value>`` CUIs in
# the CDB caused false-positive hits on generic hedges such as "has" /
# "current" / "definite" that leaked into ``LinkedEntity`` results. Phase 2
# excludes them from the CDB build so those enums stay medspaCy-populated.
_EXCLUDED_ENUM_GROUPS: frozenset[str] = frozenset(RULES_ONLY_ENUMS.keys())


def _cui_for(entry: ConceptEntry, group_name: str, value_key: str) -> str:
    """Return a CUI string for a ConceptEntry.

    Precedence: explicit ``entry.cui`` > synthetic placeholder derived
    from (group, value_key). We never use SCTIDs as CUIs (they use a
    different namespace).

    All CUIs are upper-cased — MedCAT's CDBMaker upper-cases every
    ingested CUI, so we do it here for the CSV so callers can reverse-
    lookup deterministically.
    """
    if entry.cui:
        return entry.cui.strip().upper()
    safe = value_key.replace(" ", "_").replace("/", "_")
    return f"X-{group_name}-{safe}".upper()


def _ontology_tag(entry: ConceptEntry) -> str:
    if entry.sctid:
        return "SNOMED"
    if entry.cui:
        return "UMLS"
    return "MEDAI_EPI"


def _iter_concept_rows():
    """Yield (group_name, value_key, entry) triples across enum + supplementary ontologies.

    RULES_ONLY enum groups (see ``_EXCLUDED_ENUM_GROUPS``) are skipped so
    their synthetic placeholder CUIs never enter the CDB — those enums are
    populated by medspaCy ConText, not by CUI-linking.
    """
    for group_name, ontology in all_enum_ontologies().items():
        if group_name in _EXCLUDED_ENUM_GROUPS:
            continue
        for value_key, entry in ontology.items():
            yield group_name, value_key, entry
    for group_name, ontology in supplementary_ontologies().items():
        if group_name in _EXCLUDED_ENUM_GROUPS:
            continue
        for value_key, entry in ontology.items():
            yield group_name, value_key, entry


def build_concept_dataframe() -> pd.DataFrame:
    """Assemble the CDBMaker-compatible dataframe from the ontology.

    Deduplicates (cui, name_lower) pairs. Returns a dataframe with columns:
    ``cui, name, name_status, ontologies, type_ids, description``.
    """
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for group_name, value_key, entry in _iter_concept_rows():
        cui = _cui_for(entry, group_name, value_key)
        ontology_tag = _ontology_tag(entry)
        type_id = f"T-{group_name}"

        # Primary label first
        label = entry.label.strip()
        if label:
            key = (cui, label.lower())
            if key not in seen:
                seen.add(key)
                rows.append({
                    "cui": cui,
                    "name": label,
                    "name_status": "P",
                    "ontologies": ontology_tag,
                    "type_ids": type_id,
                    "description": (
                        f"{group_name}.{value_key} — {label}"
                    ),
                })

        # Then all synonyms as aliases
        for syn in entry.synonyms:
            syn_clean = syn.strip()
            if not syn_clean:
                continue
            key = (cui, syn_clean.lower())
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "cui": cui,
                "name": syn_clean,
                "name_status": "A",
                "ontologies": ontology_tag,
                "type_ids": type_id,
                "description": "",
            })

    df = pd.DataFrame(rows, columns=[
        "cui", "name", "name_status", "ontologies", "type_ids", "description",
    ])
    return df


def build_cdb(concept_df: pd.DataFrame, output_dir: Path, verbose: bool = True):
    """Compile the CDB via MedCAT's CDBMaker and save to disk.

    MedCAT 2.x has two on-disk formats: a folder (dill-serialised parts)
    or a ``.zip`` archive. We emit both — the folder at ``cdb/`` for fast
    load, the zip at ``cdb.zip`` for portability / redistribution.
    """
    from medcat.config.config import Config
    from medcat.model_creation.cdb_maker import CDBMaker

    config = Config()
    # Loosen the linker so an untrained CDB still fires on exact-name
    # matches (dict-mode). We keep the ML linker path available for
    # Phase 2 once we have a trained MetaCAT.
    config.components.linking.similarity_threshold = 0.0
    config.components.linking.filter_before_disamb = False
    # Preserve short names such as "LEV", "LTG", "CBZ" — the ontology
    # ships several 3-letter medication abbreviations.
    config.components.ner.min_name_len = 2
    config.components.ner.check_upper_case_names = True
    config.components.ner.upper_case_limit_len = 2

    maker = CDBMaker(config)
    cdb = maker.prepare_csvs([concept_df])

    cdb_dir = output_dir / "cdb"
    cdb_zip = output_dir / "cdb.zip"

    # Idempotent: wipe any prior artefacts.
    if cdb_dir.exists():
        shutil.rmtree(cdb_dir)
    if cdb_zip.exists():
        cdb_zip.unlink()

    cdb_dir.mkdir(parents=True, exist_ok=False)
    cdb.save(str(cdb_dir), overwrite=True)
    cdb.save(str(cdb_zip), overwrite=True)

    if verbose:
        info = cdb.get_basic_info()
        print(f"[build_medcat_cdb] CDB saved to folder {cdb_dir}")
        print(f"[build_medcat_cdb] CDB saved to zip    {cdb_zip}")
        print(f"[build_medcat_cdb] CDB basic info: {info}")

    return cdb, cdb_dir


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


def _report(
    concept_df: pd.DataFrame,
    cdb_path: Path,
    build_seconds: float,
    output_dir: Path,
) -> dict:
    n_rows = len(concept_df)
    n_unique_cuis = concept_df["cui"].nunique()
    n_placeholder_cuis = int(concept_df["cui"].str.startswith("X-").sum())
    n_real_cuis = n_unique_cuis - int(
        concept_df.loc[concept_df["cui"].str.startswith("X-"), "cui"].nunique()
    )
    n_snomed_rows = int((concept_df["ontologies"] == "SNOMED").sum())
    cdb_size_bytes = _dir_size(cdb_path)
    zip_path = output_dir / "cdb.zip"
    zip_size = zip_path.stat().st_size if zip_path.exists() else 0
    return {
        "phase": "2 (rebuild)",
        "concept_csv_rows": int(n_rows),
        "unique_cuis_total": int(n_unique_cuis),
        "unique_real_cuis": int(n_real_cuis),
        "unique_placeholder_cuis": int(n_placeholder_cuis),
        "excluded_enum_groups": sorted(_EXCLUDED_ENUM_GROUPS),
        "snomed_tagged_rows": int(n_snomed_rows),
        "cdb_folder_path": str(cdb_path),
        "cdb_folder_size_bytes": int(cdb_size_bytes),
        "cdb_zip_path": str(zip_path),
        "cdb_zip_size_bytes": int(zip_size),
        "ontology_total_concept_entries": int(total_concept_count()),
        "build_seconds": round(build_seconds, 3),
        "output_dir": str(output_dir),
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Where to write concepts.csv + cdb.dat (default: data/medcat_cdb_epilepsy).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Emit concepts.csv but skip the CDBMaker build step.",
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[build_medcat_cdb] Assembling concept dataframe...")
    df = build_concept_dataframe()
    csv_path = output_dir / "concepts.csv"
    df.to_csv(csv_path, index=False)
    print(f"[build_medcat_cdb] Wrote {len(df):,} rows to {csv_path}")
    print(
        f"[build_medcat_cdb] Unique CUIs: {df['cui'].nunique():,} "
        f"({df['cui'].str.startswith('X-').sum():,} placeholder rows)"
    )

    if args.dry_run:
        print("[build_medcat_cdb] Dry-run mode; skipping CDBMaker step.")
        return 0

    t0 = time.perf_counter()
    _, cdb_path = build_cdb(df, output_dir=output_dir, verbose=True)
    dt = time.perf_counter() - t0

    report = _report(df, cdb_path, build_seconds=dt, output_dir=output_dir)
    report_path = output_dir / "build_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    print("[build_medcat_cdb] BUILD REPORT:")
    for k, v in report.items():
        print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
