"""Phase 2 / 3a end-to-end smoke test — MedCAT + medspaCy → EpilepsyPhenotype.

Runs :class:`services.phenotype_assembler.PhenotypeAssembler` on F-S train
letter(s), prints the entities + their ConText flags, per-field P1 rule
extractions, and validates the produced
:class:`schema.ontology.EpilepsyPhenotype` through Pydantic's
``model_validate``.

Usage
-----
    venv-medcat/bin/python scripts/smoke_phase2_pipeline.py [EA_ID]
    venv-medcat/bin/python scripts/smoke_phase2_pipeline.py --phase3a

Exit code is non-zero on any of:
- extractor / assembler raising,
- Pydantic validation failing,
- zero entities produced,
- --phase3a: primary doc has <3 of 8 P1 fields populated.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Silence PyRuSH debug spam (medspaCy sentencizer) that would otherwise
# swamp the smoke output.
try:  # pragma: no cover
    from loguru import logger as _lg
    _lg.remove()
except Exception:
    pass

from schema.enums import Certainty, DocumentType  # noqa: E402
from schema.ontology import EpilepsyPhenotype  # noqa: E402
from services.medcat_extractor import MedCATExtractor  # noqa: E402
from services.phenotype_assembler import PhenotypeAssembler  # noqa: E402


DEFAULT_CDB = REPO_ROOT / "data" / "medcat_cdb_epilepsy" / "cdb"

# Phase 3a: the 8 P1 fields; "populated" = value not None AND certainty
# != NOT_DOCUMENTED (or list-valued and non-empty).
P1_FIELDS = [
    ("clinical_seizure", "epilepsy_type"),
    ("clinical_seizure", "predominant_seizure_type"),
    ("clinical_seizure", "seizure_frequency"),
    ("clinical_seizure", "age_at_onset_years"),
    ("clinical_seizure", "etiology_category"),
    ("medication", "current_asms"),
    ("mri", "findings"),
    ("eeg", "ied_findings"),
]
DEFAULT_DOCS = ["EA0001", "EA0025", "EA0050", "EA0075", "EA0100"]


def _is_populated(pheno: EpilepsyPhenotype, module_name: str, field: str) -> bool:
    mod = getattr(pheno, module_name, None)
    if mod is None:
        return False
    val = getattr(mod, field, None)
    if val is None:
        return False
    if isinstance(val, list):
        if len(val) > 0:
            return True
        # For MRI/EEG list fields, also count the boolean convenience
        # signals (normal/negative) — a normal MRI is still "extracted".
        if module_name == "mri" and field == "findings":
            for sib in ("overall_normal", "mri_negative_for_epilepsy",
                        "hippocampal_sclerosis", "focal_cortical_dysplasia"):
                s = getattr(mod, sib, None)
                if s is not None and getattr(s, "value", None) is not None \
                   and getattr(s, "certainty", None) != Certainty.NOT_DOCUMENTED:
                    return True
        if module_name == "eeg" and field == "ied_findings":
            for sib in ("background", "ied_present"):
                s = getattr(mod, sib, None)
                if s is not None and getattr(s, "value", None) is not None \
                   and getattr(s, "certainty", None) != Certainty.NOT_DOCUMENTED:
                    return True
        return False
    return (getattr(val, "value", None) is not None and
            getattr(val, "certainty", None) != Certainty.NOT_DOCUMENTED)


def _summarise_phase3a(pheno: EpilepsyPhenotype) -> tuple[int, list[str]]:
    hits = 0
    lines: list[str] = []
    for module_name, field in P1_FIELDS:
        pop = _is_populated(pheno, module_name, field)
        mark = "+" if pop else "-"
        mod = getattr(pheno, module_name, None)
        v = getattr(mod, field, None) if mod is not None else None
        if pop:
            hits += 1
            if isinstance(v, list):
                summary = f"{len(v)} entry(ies)"
                if v and hasattr(v[0], "value") and v[0].value is not None:
                    summary += f" e.g. {v[0].value!r}"[:90]
            else:
                summary = f"{v.value!r}"[:90]
        else:
            summary = "not_documented"
        lines.append(f"    [{mark}] {module_name}.{field:30s} : {summary}")
    return hits, lines


def _resolve_doc(ea_id: str) -> Path:
    p = REPO_ROOT / "data" / "fs_corpus" / "documents" / ea_id / "progress_note" / "output.txt"
    if not p.exists():
        raise FileNotFoundError(f"No document at {p}")
    return p


def _run_phase3a(args) -> int:
    """Phase 3a smoke — 5 F-S train letters, per-field summary."""
    print(f"[smoke3a] Loading MedCAT + medspaCy pipeline …")
    extractor = MedCATExtractor(args.cdb, verbose=False)
    assembler = PhenotypeAssembler(extractor)
    n_rules = len(assembler._rules)
    print(f"[smoke3a] {n_rules} field rules registered")

    total_pop = 0
    total_slots = 0
    per_doc_hits: list[int] = []
    for ea_id in DEFAULT_DOCS:
        p = REPO_ROOT / "data" / "fs_corpus" / "documents" / ea_id / "progress_note" / "output.txt"
        if not p.exists():
            print(f"[smoke3a] SKIP {ea_id}: no doc")
            continue
        text = p.read_text()
        print(f"\n[smoke3a] ▶ {ea_id} ({len(text):,} chars)")
        pheno = assembler.process(
            text, doc_id=ea_id, doc_type=DocumentType.PROGRESS_NOTE,
            doc_date=date(2020, 1, 1), patient_id=ea_id,
        )
        try:
            EpilepsyPhenotype.model_validate(pheno.model_dump(mode="json"))
        except Exception as e:
            print(f"[smoke3a] FAIL {ea_id}: Pydantic re-validate: {e}")
            return 2
        hits, lines = _summarise_phase3a(pheno)
        for ln in lines:
            print(ln)
        print(f"    → P1 population: {hits}/{len(P1_FIELDS)} fields")
        per_doc_hits.append(hits)
        total_pop += hits
        total_slots += len(P1_FIELDS)

    n_docs = len(per_doc_hits)
    if n_docs == 0:
        print("[smoke3a] FAIL: no docs")
        return 2
    avg = total_pop / n_docs
    print(f"\n[smoke3a] Summary: {total_pop}/{total_slots} P1 fields populated "
          f"across {n_docs} docs (avg {avg:.1f}/{len(P1_FIELDS)} per doc)")
    if per_doc_hits[0] < 3:
        print(f"[smoke3a] FAIL: primary doc {DEFAULT_DOCS[0]} only "
              f"{per_doc_hits[0]}/{len(P1_FIELDS)} fields populated")
        return 3
    print("[smoke3a] PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ea_id", nargs="?", default="EA0001",
                        help="F-S letter identifier (e.g. EA0001).")
    parser.add_argument("--cdb", default=str(DEFAULT_CDB))
    parser.add_argument("--limit", type=int, default=20,
                        help="Max entities to print (default 20).")
    parser.add_argument("--phase3a", action="store_true",
                        help="Run Phase-3a extended smoke over 5 F-S train "
                             "letters and print per-field population.")
    args = parser.parse_args(argv)

    if args.phase3a:
        return _run_phase3a(args)

    doc_path = _resolve_doc(args.ea_id)
    text = doc_path.read_text()
    print(f"[smoke2] Document: {doc_path} ({len(text):,} chars)")

    t0 = time.perf_counter()
    extractor = MedCATExtractor(args.cdb, verbose=False)
    assembler = PhenotypeAssembler(extractor)
    load_dt = time.perf_counter() - t0
    stats = assembler.pipeline_stats()
    print(
        f"[smoke2] Loaded extractor + medspaCy pipeline in {load_dt:.2f}s"
    )
    print(
        f"[smoke2] medspaCy defaults={stats.get('medspacy_default_rules')}, "
        f"US-additions={stats.get('us_additions')}, "
        f"ExECT-consulted={stats.get('exect_consulted_triggers')}"
    )

    t1 = time.perf_counter()
    pheno = assembler.process(
        text,
        doc_id=args.ea_id,
        doc_type=DocumentType.PROGRESS_NOTE,
        doc_date=date(2020, 1, 1),
        patient_id=args.ea_id,
    )
    dt = time.perf_counter() - t1
    print(f"[smoke2] End-to-end process() took {dt:.3f}s")

    # Pydantic validation round-trip.
    dumped = pheno.model_dump(mode="json")
    revalidated = EpilepsyPhenotype.model_validate(dumped)
    print(
        f"[smoke2] EpilepsyPhenotype Pydantic validation: PASS "
        f"(schema_version={revalidated.schema_version})"
    )

    entities = getattr(pheno, "_entities", [])
    print(f"[smoke2] Entities found: {len(entities)}")

    print()
    ctx_count = 0
    neg_seen = None
    hist_seen = None
    hyp_seen = None
    fam_seen = None
    for i, e in enumerate(entities[: args.limit]):
        flags = []
        if e.is_negated:
            flags.append("NEG")
            neg_seen = neg_seen or e
        if e.is_historical:
            flags.append("HIST")
            hist_seen = hist_seen or e
        if e.is_hypothetical:
            flags.append("HYP")
            hyp_seen = hyp_seen or e
        if e.is_family:
            flags.append("FAM")
            fam_seen = fam_seen or e
        if flags:
            ctx_count += 1
        tag = ",".join(flags) if flags else "-"
        print(
            f"  [{e.char_start}:{e.char_end}] {e.text!r} -> "
            f"{e.enum_class}.{e.enum_value} tier={e.linker_tier} "
            f"flags=[{tag}]"
        )
    if len(entities) > args.limit:
        print(f"  ... ({len(entities) - args.limit} more)")

    print()
    print(
        f"[smoke2] Entities with any ConText flag: {ctx_count} / "
        f"{min(len(entities), args.limit)} shown"
    )
    if neg_seen:
        print(f"[smoke2] Example NEGATED: {neg_seen.text!r} @ [{neg_seen.char_start}:{neg_seen.char_end}]")
        print(f"           sentence: {neg_seen.sentence_text.strip()[:160]!r}")
    if hist_seen:
        print(f"[smoke2] Example HISTORICAL: {hist_seen.text!r} @ [{hist_seen.char_start}:{hist_seen.char_end}]")
    if hyp_seen:
        print(f"[smoke2] Example HYPOTHETICAL: {hyp_seen.text!r} @ [{hyp_seen.char_start}:{hyp_seen.char_end}]")
    if fam_seen:
        print(f"[smoke2] Example FAMILY: {fam_seen.text!r} @ [{fam_seen.char_start}:{fam_seen.char_end}]")

    if not entities:
        print("[smoke2] FAIL: 0 entities", file=sys.stderr)
        return 2
    if not any(
        e.is_negated or e.is_historical or e.is_hypothetical or e.is_family
        for e in entities
    ):
        print(
            "[smoke2] WARNING: no ConText flags fired on this document. "
            "Check pipeline wiring.",
            file=sys.stderr,
        )

    # ------------------------------------------------------------------
    # Phase 3a per-field summary — run on all 5 default sample docs so a
    # single bare invocation exercises the whole rules registry against
    # multiple F-S train letters.
    # ------------------------------------------------------------------
    print()
    print(f"[smoke3a] Rules loaded: {len(assembler._rules)}")

    total_pop = 0
    total_slots = 0
    per_doc_hits: list[int] = []
    docs_to_check = DEFAULT_DOCS if args.ea_id == "EA0001" else [args.ea_id]
    for ea in docs_to_check:
        try:
            p = _resolve_doc(ea)
        except FileNotFoundError:
            continue
        if ea == args.ea_id:
            pheno_i = pheno
        else:
            pheno_i = assembler.process(
                p.read_text(), doc_id=ea, doc_type=DocumentType.PROGRESS_NOTE,
                doc_date=date(2020, 1, 1), patient_id=ea,
            )
            try:
                EpilepsyPhenotype.model_validate(pheno_i.model_dump(mode="json"))
            except Exception as e:
                print(f"[smoke3a] FAIL {ea}: {e}")
                return 2
        hits, lines = _summarise_phase3a(pheno_i)
        print(f"\n[smoke3a] ▶ {ea}")
        # Show SeizureType / Medication / MriFinding / IedType entities for debug.
        ents_i = getattr(pheno_i, "_entities", [])
        interesting = [e for e in ents_i
                       if e.enum_class in ("SeizureType", "Medication", "MriFinding",
                                           "IedType", "EegBackground", "Awareness",
                                           "EpilepsyType", "EtiologyCategory")]
        print(f"    entities ({len(interesting)} interesting of {len(ents_i)}):")
        for e in interesting[:25]:
            flags = []
            if e.is_negated: flags.append("NEG")
            if e.is_historical: flags.append("HIST")
            if e.is_hypothetical: flags.append("HYP")
            if e.is_family: flags.append("FAM")
            tag = ",".join(flags) if flags else "-"
            print(f"      [{e.char_start}:{e.char_end}] {e.text!r:>34s} -> "
                  f"{e.enum_class}.{e.enum_value} [{tag}]")
        for ln in lines:
            print(ln)
        print(f"    → {hits}/{len(P1_FIELDS)} P1 fields populated")
        per_doc_hits.append(hits)
        total_pop += hits
        total_slots += len(P1_FIELDS)

    if per_doc_hits:
        avg = total_pop / len(per_doc_hits)
        print(f"\n[smoke3a] Summary: {total_pop}/{total_slots} P1 fields populated "
              f"across {len(per_doc_hits)} docs (avg {avg:.1f}/{len(P1_FIELDS)} per doc)")

    print()
    print("[smoke2] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
