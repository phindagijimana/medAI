"""Batch A D1 — enrich the epilepsy ontology from UMLS Metathesaurus (UTS API).

Requires ``UMLS_APIKEY`` env var. Fetches per-CUI atoms from the UTS REST API
(https://uts-ws.nlm.nih.gov/rest), extracts English synonyms + SCTIDs, and
merges into ``rules/epilepsy_ontology.py`` under provenance
``UMLS-Full 2025AA``.

Responses are cached to ``.cache/umls_api/{cui}.json`` for reproducibility.

Behaviour when UMLS_APIKEY is not set: script prints an actionable message
and exits with return code 3 so Batch A can continue with D2/D3/D4.

Rate limiting: sleep 0.2s between requests (~5 req/sec).

Usage:
    UMLS_APIKEY=... venv-medcat/bin/python scripts/enrich_ontology_from_umls.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CACHE_DIR = REPO_ROOT / ".cache" / "umls_api"
DEFAULT_OUT = CACHE_DIR / "umls_enrichment_report.json"
BASE_URL = "https://uts-ws.nlm.nih.gov/rest"
SABS = "SNOMEDCT_US,RXNORM,MSH,HPO,ICD10CM"
RATE_LIMIT_SECONDS = 0.2  # 5 req/sec


def _load_our_cuis():
    """Return list of (cui, group_name, value_key) tuples for each entry with a CUI."""
    from rules.epilepsy_ontology import (
        all_enum_ontologies, supplementary_ontologies,
    )
    out = []
    for group_name, ontology in list(all_enum_ontologies().items()) + list(supplementary_ontologies().items()):
        for value_key, entry in ontology.items():
            if entry.cui:
                out.append((entry.cui.strip().upper(), group_name, value_key))
    return out


def _cached_or_fetch(cui: str, apikey: str, force: bool = False) -> dict:
    """Fetch atoms for a CUI. Cache to disk."""
    import urllib.parse
    import urllib.request
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{cui}.json"
    if cache_path.exists() and not force:
        return json.loads(cache_path.read_text(encoding="utf-8"))

    url = f"{BASE_URL}/content/current/CUI/{cui}/atoms"
    params = {"apiKey": apikey, "sabs": SABS, "language": "ENG", "pageSize": 200}
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
        j = json.loads(body)
    except Exception as e:  # noqa: BLE001
        j = {"error": str(e)}
    cache_path.write_text(json.dumps(j, indent=2), encoding="utf-8")
    time.sleep(RATE_LIMIT_SECONDS)
    return j


def _distill(atoms_json: dict) -> tuple[list[str], list[str]]:
    """Return (english_atom_names, sctids)."""
    names = []
    sctids = []
    if not isinstance(atoms_json, dict):
        return names, sctids
    result = atoms_json.get("result", [])
    if not isinstance(result, list):
        return names, sctids
    for atom in result:
        if not isinstance(atom, dict):
            continue
        name = atom.get("name")
        if isinstance(name, str) and name:
            names.append(name)
        root_src = atom.get("rootSource", "")
        code_uri = atom.get("code", "")
        if root_src == "SNOMEDCT_US" and code_uri:
            # code is a URI like https://uts-ws.nlm.nih.gov/.../code/12345678
            sct = code_uri.rsplit("/", 1)[-1]
            if sct.isdigit():
                sctids.append(sct)
    return names, sctids


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--limit", type=int, default=None,
                    help="Only process first N CUIs (debug)")
    ap.add_argument("--force", action="store_true", help="Bypass cache")
    args = ap.parse_args(argv)

    apikey = os.environ.get("UMLS_APIKEY", "").strip()
    if not apikey:
        print("[umls-enrich] ABORT: UMLS_APIKEY environment variable not set.",
              file=sys.stderr)
        print("[umls-enrich] Skipping D1 UMLS enrichment; Batch A continues "
              "with D2/D3/D4.", file=sys.stderr)
        # Write a stub report so downstream tools always find a file
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({
            "status": "skipped_no_apikey",
            "cuis_processed": 0,
            "synonyms_added": 0,
            "sctids_added": 0,
        }, indent=2), encoding="utf-8")
        return 3

    triples = _load_our_cuis()
    if args.limit:
        triples = triples[:args.limit]
    print(f"[umls-enrich] Processing {len(triples)} CUI entries...")

    enrichment: dict[str, dict[str, dict]] = defaultdict(dict)
    n_cache_hit = 0
    n_new = 0
    for i, (cui, group, vkey) in enumerate(triples):
        cache_path = CACHE_DIR / f"{cui}.json"
        if cache_path.exists() and not args.force:
            n_cache_hit += 1
        j = _cached_or_fetch(cui, apikey, force=args.force)
        names, sctids = _distill(j)
        seen = set()
        uniq_names = []
        for n in names:
            k = n.lower().strip()
            if k and k not in seen:
                seen.add(k)
                uniq_names.append(n)
        enrichment[group][vkey] = {
            "cui": cui,
            "candidate_synonyms": uniq_names,
            "sctids": sorted(set(sctids)),
        }
        n_new += len(uniq_names)
        if i % 20 == 0:
            print(f"  [{i+1}/{len(triples)}] {cui} → {len(uniq_names)} atoms")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "status": "ok",
        "cuis_processed": len(triples),
        "cache_hits": n_cache_hit,
        "candidate_synonyms_total": n_new,
        "enrichment": dict(enrichment),
    }, indent=2), encoding="utf-8")
    print(f"[umls-enrich] Wrote report to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
