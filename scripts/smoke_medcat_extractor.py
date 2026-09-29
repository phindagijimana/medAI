"""Phase 1c smoke test — runs :class:`services.medcat_extractor.MedCATExtractor`
on a single F-S train letter and prints the top-N linked entities.

Usage
-----
    venv-medcat/bin/python scripts/smoke_medcat_extractor.py [EA_ID]

Defaults to ``EA0001``. Prints char-offsets, matched surface form, CUI,
label, and linker tier for the first 15 entities.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_medcat_extractor():
    """Load ``services.medcat_extractor`` without triggering
    ``services/__init__.py`` (which imports the werkzeug-dependent
    Med42 stack we don't need for MedCAT-only runs)."""
    mod_name = "services_medcat_extractor"
    if mod_name in sys.modules:
        return sys.modules[mod_name].MedCATExtractor
    spec = importlib.util.spec_from_file_location(
        mod_name,
        REPO_ROOT / "services" / "medcat_extractor.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module.MedCATExtractor


MedCATExtractor = _load_medcat_extractor()


DEFAULT_CDB = REPO_ROOT / "data" / "medcat_cdb_epilepsy" / "cdb"
DEFAULT_DOC = REPO_ROOT / "data" / "fs_corpus" / "documents" / "EA0001" / "progress_note" / "output.txt"


def _resolve_doc(ea_id: str) -> Path:
    p = REPO_ROOT / "data" / "fs_corpus" / "documents" / ea_id / "progress_note" / "output.txt"
    if not p.exists():
        raise FileNotFoundError(f"No document at {p}")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ea_id", nargs="?", default="EA0001",
                        help="F-S letter identifier (e.g. EA0001).")
    parser.add_argument("--cdb", default=str(DEFAULT_CDB),
                        help="Path to custom CDB (folder or .zip).")
    parser.add_argument("--umls-small-pack", default=None,
                        help="Optional MedCAT model-pack path for UMLS-Small fallback.")
    parser.add_argument("--limit", type=int, default=15,
                        help="Max entities to print (default 15).")
    args = parser.parse_args(argv)

    doc_path = _resolve_doc(args.ea_id)
    text = doc_path.read_text()
    print(f"[smoke] Document: {doc_path} ({len(text):,} chars)")

    t0 = time.perf_counter()
    extractor = MedCATExtractor(
        args.cdb,
        umls_small_pack_path=args.umls_small_pack,
        verbose=True,
    )
    load_dt = time.perf_counter() - t0
    print(f"[smoke] Extractor loaded in {load_dt:.2f}s")

    t1 = time.perf_counter()
    ents = extractor.extract(text)
    extract_dt = time.perf_counter() - t1
    print(f"[smoke] Extraction took {extract_dt:.3f}s; found {len(ents)} entities")

    print()
    for i, e in enumerate(ents[: args.limit]):
        print(
            f"  [{e.char_start}:{e.char_end}] {e.text!r} -> {e.cui} "
            f"({e.label}) enum={e.enum_class}.{e.enum_value} tier={e.linker_tier} "
            f"conf={e.confidence:.2f}"
        )
    if len(ents) > args.limit:
        print(f"  ... ({len(ents) - args.limit} more)")

    # Determinism spot-check: run twice, hash outputs
    ents2 = extractor.extract(text)
    same = [
        (e1.cui, e1.char_start, e1.char_end) for e1 in ents
    ] == [
        (e2.cui, e2.char_start, e2.char_end) for e2 in ents2
    ]
    print()
    print(f"[smoke] Deterministic re-run: {'OK' if same else 'FAIL'}")

    # Char-offset spot-check
    if ents:
        e0 = ents[0]
        got = text[e0.char_start:e0.char_end]
        print(f"[smoke] Offset spot-check: text[{e0.char_start}:{e0.char_end}] = {got!r} vs entity.text = {e0.text!r} -> {'OK' if got == e0.text else 'FAIL'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
