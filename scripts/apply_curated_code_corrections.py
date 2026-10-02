#!/usr/bin/env python3
"""Apply data/curated/curated_code_corrections.csv to rules/epilepsy_ontology.py.

Each CSV row changes one ``cui`` or ``sctid`` of one (group, key) entry:

    field=sctid  new=<SCTID> | ""            new code, or remove the code
    field=cui    new=from_sctid               CUI of the entry's (new) SCTID, via UTS
                 new=search:<string>          first exact-match UTS concept for <string>
                 new=none                     remove the CUI

Every new SCTID must be active in the pinned SNOMED CT release, and every new
CUI is fetched (atoms cached in .cache/umls_api/<CUI>.json, the same cache the
curated-code audit reads), so the audit re-checks the result.  Each change is
recorded in the entry's ``source_provenance``.  Re-running is a no-op.

    venv/bin/python scripts/apply_curated_code_corrections.py --dry-run
    venv/bin/python scripts/apply_curated_code_corrections.py

Requires UMLS_APIKEY (read from the environment or .env; never printed).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

CSV_PATH = REPO / "data" / "curated" / "curated_code_corrections.csv"
ONTOLOGY = REPO / "rules" / "epilepsy_ontology.py"
CACHE = REPO / ".cache" / "umls_api"
UTS = "https://uts-ws.nlm.nih.gov/rest"
ATOM_SABS = "SNOMEDCT_US,RXNORM,MSH,HPO,ICD10CM"
DATE = "2026-10-01"


def _apikey() -> str:
    key = os.environ.get("UMLS_APIKEY", "").strip()
    env = REPO / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("UMLS_APIKEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("UMLS_APIKEY not set (environment or .env)")
    return key


def _get(path: str, params: dict, key: str) -> dict:
    url = f"{UTS}{path}?{urllib.parse.urlencode({**params, 'apiKey': key})}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise SystemExit(f"UTS {path}: HTTP {e.code}") from None
        body = {"result": [], "status": 404}
    time.sleep(0.2)
    return body


def _cui_for_sctid(sctid: str, key: str) -> str:
    j = _get("/search/current", {"string": sctid, "inputType": "sourceUi", "searchType": "exact",
                                 "sabs": "SNOMEDCT_US", "returnIdType": "concept"}, key)
    hits = [r["ui"] for r in j.get("result", {}).get("results", []) if r.get("ui", "").startswith("C")]
    if len(hits) != 1:
        raise SystemExit(f"SCTID {sctid}: expected one UMLS concept, got {hits}")
    return hits[0]


def _cui_for_string(s: str, key: str) -> str:
    j = _get("/search/current", {"string": s, "searchType": "exact"}, key)
    hits = [r["ui"] for r in j.get("result", {}).get("results", []) if r.get("ui", "").startswith("C")]
    if not hits:
        raise SystemExit(f"no UMLS concept for {s!r}")
    return hits[0]


def _cache_atoms(cui: str, key: str) -> list[str]:
    p = CACHE / f"{cui}.json"
    if not p.exists():
        j = _get(f"/content/current/CUI/{cui}/atoms",
                 {"sabs": ATOM_SABS, "language": "ENG", "pageSize": 200}, key)
        CACHE.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(j, indent=2), encoding="utf-8")
    atoms = json.loads(p.read_text(encoding="utf-8")).get("result") or []
    return [a["name"] for a in atoms if a.get("name")]


def _group_vars(src: str) -> dict[str, str]:
    return dict(re.findall(r'^\s+"(\w+)": ([A-Z_]+_ONTOLOGY),$', src, re.M))


def _entry_span(src: str, var: str, key: str) -> tuple[int, int]:
    start = src.index(f"\n{var}: dict[str, ConceptEntry] = {{")
    end = src.index("\n}\n", start)
    m = re.search(rf'\n    "{re.escape(key)}": ConceptEntry\(.*?\n    \),', src[start:end], re.S)
    if not m:
        raise SystemExit(f"{var}[{key!r}] not found")
    return start + m.start(), start + m.end()


def _set_field(entry: str, field: str, value: str | None) -> str:
    lit = f'"{value}"' if value else "None"
    new, n = re.subn(rf'\b{field}=(None|"[^"]*")', f"{field}={lit}", entry, count=1)
    if not n:
        raise SystemExit(f"no {field}= in entry:\n{entry[:200]}")
    return new


def _add_provenance(entry: str, note: str) -> str:
    m = re.search(r"source_provenance=\[(.*?)\]", entry, re.S)
    if not m:
        raise SystemExit(f"no source_provenance in entry:\n{entry[:200]}")
    body = m.group(1).rstrip().rstrip(",")
    sep = ",\n            " if "\n" in body else ", "
    return entry[:m.start(1)] + body + sep + json.dumps(note) + entry[m.end(1):]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from rules.epilepsy_ontology import all_enum_ontologies, supplementary_ontologies
    from services.ontology_loaders import _snomed_lookup_uncached, semantic_tag
    from services.ontology_releases import release_tag

    live = {**all_enum_ontologies(), **supplementary_ontologies()}
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    new_sct = {r["new"] for r in rows if r["field"] == "sctid" and r["new"]}
    sct = _snomed_lookup_uncached(new_sct)
    bad = [s for s in new_sct if not sct.get(s, {}).get("active")]
    if bad:
        raise SystemExit(f"SCTIDs not active in {release_tag('snomed')}: {bad}")

    target_sct = {(r["group"], r["key"]): r["new"] or None for r in rows if r["field"] == "sctid"}
    key = None
    src = ONTOLOGY.read_text(encoding="utf-8")
    gvars = _group_vars(src)
    changed = 0
    for r in rows:
        g, k, field, old = r["group"], r["key"], r["field"], r["old"] or None
        entry_obj = live[g][k]
        a, b = _entry_span(src, gvars[g], k)
        # Compare with the source, not the live entry: UMLS overrides may fill a removed SCTID.
        current = re.search(rf'\b{field}=(?:None|"([^"]*)")', src[a:b]).group(1)
        if field == "sctid":
            new = r["new"] or None
            name = f"{new} {sct[new]['fsn']}" if new else "removed"
        else:
            if r["new"] == "none":
                new = None
            else:
                key = key or _apikey()
                if r["new"] == "from_sctid":
                    s = target_sct.get((g, k)) or entry_obj.sctid
                    if not s:
                        raise SystemExit(f"{g}.{k}: from_sctid but entry has no SCTID")
                    new = _cui_for_sctid(s, key)
                else:
                    new = _cui_for_string(r["new"].split(":", 1)[1], key)
                _cache_atoms(new, key)
            name = new or "removed"
        if current == new:
            continue
        if (current or None) != old:
            raise SystemExit(f"{g}.{k}.{field}: expected {old!r}, found {current!r}")
        entry = _set_field(src[a:b], field, new)
        source = release_tag("snomed") if field == "sctid" else "UMLS UTS REST (current)"
        entry = _add_provenance(entry, f"corrected {DATE}: {field} {old or 'None'} -> {new or 'None'} "
                                       f"({source}; data/curated/curated_code_corrections.csv)")
        src = src[:a] + entry + src[b:]
        changed += 1
        tag = f" [{semantic_tag(sct[new]['fsn'])}]" if field == "sctid" and new else ""
        print(f"{g}.{k}.{field}: {old} -> {name}{tag}")

    print(f"{changed} changes")
    if changed and not args.dry_run:
        ONTOLOGY.write_text(src, encoding="utf-8")
        print(f"wrote {ONTOLOGY.relative_to(REPO)}")


if __name__ == "__main__":
    main()
