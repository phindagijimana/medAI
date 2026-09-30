#!/usr/bin/env python3
"""Phase 7 — corpus-agnostic runner for the MedCAT+Rules pipeline (arm B1').

For every document in the requested corpus this script:

1.  Locates the source text file (corpus-specific layout).
2.  Runs :class:`services.phenotype_assembler.PhenotypeAssembler`.
3.  Serialises the resulting :class:`EpilepsyPhenotype` to JSON.
4.  Writes ``<out-dir>/<doc_id>.json`` alongside a run manifest.

Corpora supported::

    fs_test_40           F-S 40 held-out (EA0161..EA0200)
    synth_v1_eval_100    Synthetic v1 evaluation corpus (102 docs)
    mtsamples_neuro      MTSamples neurology subset (78 notes, no gold)

Usage
-----
::

    venv-medcat/bin/python scripts/run_medcat_rules_on_corpus.py \
        --corpus fs_test_40 \
        --out-dir data/run_manifests_medcat_rules_fs_test_40/
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Silence loguru / PyRuSH debug noise; suppress before any medcat imports.
os.environ.setdefault("LOGURU_LEVEL", "WARNING")
try:  # pragma: no cover
    from loguru import logger as _lg
    _lg.remove()
except Exception:
    pass

from schema.enums import DocumentType  # noqa: E402
from services.medcat_extractor import MedCATExtractor  # noqa: E402
from services.phenotype_assembler import PhenotypeAssembler  # noqa: E402


DEFAULT_CDB = REPO_ROOT / "data" / "medcat_cdb_epilepsy" / "cdb"


# ---------------------------------------------------------------------------
# Corpus loaders — each yields (doc_id, text_path, doc_type)
# ---------------------------------------------------------------------------


def _fs_test_40_docs() -> Iterator[tuple[str, Path, str]]:
    """40 held-out F-S letters, EA0161..EA0200."""
    for i in range(161, 201):
        doc_id = f"EA{i:04d}"
        p = REPO_ROOT / "data" / "fs_corpus" / "documents" / doc_id / \
            "progress_note" / "output.txt"
        if p.exists():
            yield doc_id, p, "progress_note"


def _synth_v1_eval_100_docs() -> Iterator[tuple[str, Path, str]]:
    """Read manifest.csv and yield each doc referenced there."""
    manifest = REPO_ROOT / "data" / "eval_corpora" / "synth_v1_eval_100" / \
        "manifest.csv"
    if not manifest.exists():
        return
    with manifest.open() as fh:
        r = csv.DictReader(fh)
        for row in r:
            doc_id = row["id"]
            src = REPO_ROOT / row["source_path"]
            doc_type = row.get("doc_type", "progress_note")
            if src.exists():
                yield doc_id, src, doc_type


def _mtsamples_docs() -> Iterator[tuple[str, Path, str]]:
    """Yield mtsamples note.txt files."""
    base = REPO_ROOT / "data" / "eval_corpora" / "mtsamples_neuro"
    for d in sorted(base.glob("mt_sample_*")):
        p = d / "note.txt"
        if p.exists():
            yield d.name, p, "progress_note"


def _synth_v2_eval_100_docs() -> Iterator[tuple[str, Path, str]]:
    """Yield synth-v2 held-out docs (P002250-P002299 patients, both doc types)."""
    base = REPO_ROOT / "data" / "episynth_corpus" / "v2" / "documents"
    for i in range(2250, 2300):
        pid = f"P{i:06d}"
        for doc_dir in sorted((base / pid).glob("*")) if (base / pid).exists() else []:
            out = doc_dir / "output.txt"
            if out.exists():
                yield f"{pid}_{doc_dir.name}", out, doc_dir.name


def _synthea_epilepsy_docs() -> Iterator[tuple[str, Path, str]]:
    """Yield Synthea epilepsy-mentioning encounter notes."""
    base = REPO_ROOT / "data" / "eval_corpora" / "synthea_epilepsy" / "documents"
    for p in sorted(base.glob("*.txt")):
        yield p.stem, p, "progress_note"


CORPUS_LOADERS = {
    "fs_test_40": _fs_test_40_docs,
    "synth_v1_eval_100": _synth_v1_eval_100_docs,
    "mtsamples_neuro": _mtsamples_docs,
    "synth_v2_eval_100": _synth_v2_eval_100_docs,
    "synthea_epilepsy": _synthea_epilepsy_docs,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _parse_doc_type(s: str) -> DocumentType:
    try:
        return DocumentType(s)
    except ValueError:
        return DocumentType.PROGRESS_NOTE


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True, choices=list(CORPUS_LOADERS.keys()))
    ap.add_argument("--out-dir", required=True,
                    help="Directory to write per-doc JSON phenotype outputs.")
    ap.add_argument("--n", type=int, default=None,
                    help="Optional cap on number of docs (smoke test).")
    ap.add_argument("--cdb", default=str(DEFAULT_CDB),
                    help="Path to MedCAT CDB directory.")
    ap.add_argument("--doc-date", default="2020-01-01",
                    help="Fallback doc_date (YYYY-MM-DD) if not in corpus.")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc_date = date.fromisoformat(args.doc_date)

    print(f"[run] Loading MedCAT extractor from {args.cdb}", flush=True)
    extractor = MedCATExtractor(args.cdb, verbose=False)
    print(f"[run] Building PhenotypeAssembler", flush=True)
    assembler = PhenotypeAssembler(extractor)
    n_rules = len(assembler._rules)
    print(f"[run] {n_rules} field rules registered", flush=True)

    loader = CORPUS_LOADERS[args.corpus]
    docs = list(loader())
    if args.n is not None:
        docs = docs[: args.n]
    print(f"[run] Corpus '{args.corpus}': {len(docs)} document(s) to process",
          flush=True)

    manifest_rows = []
    t0 = time.time()
    n_ok = n_fail = 0
    for i, (doc_id, path, doc_type_str) in enumerate(docs, start=1):
        t_doc = time.time()
        text = path.read_text(encoding="utf-8", errors="replace")
        doc_type = _parse_doc_type(doc_type_str)
        # Extract patient_id: F-S → doc_id; synth-v1 → strip suffix; mtsamples → id.
        if args.corpus == "synth_v1_eval_100":
            patient_id = doc_id.split("_")[0]
        else:
            patient_id = doc_id
        try:
            pheno = assembler.process(
                text, doc_id=doc_id, doc_type=doc_type,
                doc_date=doc_date, patient_id=patient_id,
            )
            d = pheno.model_dump(mode="json")
            (out_dir / f"{doc_id}.json").write_text(
                json.dumps(d, indent=2), encoding="utf-8",
            )
            dt = time.time() - t_doc
            manifest_rows.append({
                "doc_id": doc_id, "src_path": str(path.relative_to(REPO_ROOT)),
                "chars": len(text), "duration_s": round(dt, 3),
                "status": "ok",
            })
            n_ok += 1
        except Exception as e:  # pragma: no cover - defensive
            dt = time.time() - t_doc
            manifest_rows.append({
                "doc_id": doc_id, "src_path": str(path.relative_to(REPO_ROOT)),
                "chars": len(text), "duration_s": round(dt, 3),
                "status": f"error: {type(e).__name__}: {str(e)[:200]}",
            })
            n_fail += 1
            print(f"[run]   ERR {doc_id}: {type(e).__name__}: {e}", flush=True)
            continue
        if i % 10 == 0 or i == len(docs):
            print(f"[run]   {i}/{len(docs)} done "
                  f"(elapsed {time.time()-t0:.1f}s)", flush=True)

    # Write manifest
    if manifest_rows:
        manifest_p = out_dir / "_manifest.csv"
        with manifest_p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(manifest_rows[0].keys()))
            w.writeheader()
            for r in manifest_rows:
                w.writerow(r)

    print(f"[run] Done: {n_ok} OK, {n_fail} FAILED in {time.time()-t0:.1f}s",
          flush=True)
    print(f"[run] Outputs → {out_dir}", flush=True)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
