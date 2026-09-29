"""Batch A D3 — enrich the epilepsy ontology from HPO (Human Phenotype Ontology).

Reads `.cache/hpo/hp.obo` (downloaded from https://purl.obolibrary.org/obo/hp.obo)
and extracts term labels + synonyms + xrefs for terms under the following
HPO subtrees:

- HP:0001250 Seizure                (feeds SeizureType, FocalMotorOnset, FocalNonmotorOnset)
- HP:0001249 Intellectual disability (feeds Comorbidity supplementary)
- HP:0001263 Global developmental delay (feeds Comorbidity supplementary)

The script does NOT edit the ontology in-place; instead it emits a JSON
report to `.cache/hpo/hpo_enrichment_report.json` mapping HPO IDs → schema
enum values → candidate synonyms. A separate patch (Edit-driven) then
folds high-signal candidates into ``rules/epilepsy_ontology.py``.

Idempotent. Safe to re-run — parses local OBO only.

Provenance strings written by the patch step:
- ``HPO 2024`` for each new synonym / cross-ref.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_OBO = REPO_ROOT / ".cache" / "hpo" / "hp.obo"
DEFAULT_OUT = REPO_ROOT / ".cache" / "hpo" / "hpo_enrichment_report.json"

# HPO roots we care about — each maps to zero or more schema enum groups.
ROOT_TERMS: dict[str, list[str]] = {
    "HP:0001250": ["SeizureType", "FocalMotorOnset", "FocalNonmotorOnset"],
    "HP:0001249": ["Comorbidity"],
    "HP:0001263": ["Comorbidity"],
}

# Manual mapping of HPO IDs → our ontology (group, value_key) — hand-curated.
# Keys are HPO IDs; values map to a list of (group_name, value_key) tuples.
# Each mapping was verified against `.cache/hpo/hp.obo` (HPO 2024 release) —
# only IDs where the HPO term name exactly matches the intended concept were
# retained; bogus or ambiguous IDs (Paraparesis, Fasciculations, ASD-heart,
# Cavum septum pellucidum, Febrile seizure, etc.) were removed.
HPO_TO_SCHEMA: dict[str, list[tuple[str, str]]] = {
    # ---- SeizureType (verified) ----
    # Generalized-onset seizure (root) — provides good synonyms
    "HP:0002197": [("SeizureType", "generalized_tonic_clonic")],
    # Focal-onset seizure (parent) — many "focal seizure" surface synonyms
    "HP:0007359": [("SeizureType", "focal_impaired_awareness")],
    # Focal impaired awareness seizure
    "HP:0002384": [("SeizureType", "focal_impaired_awareness")],
    # Absence seizure (typical)
    "HP:0002121": [("SeizureType", "generalized_absence_typical")],
    # Atypical absence
    "HP:0007270": [("SeizureType", "generalized_absence_atypical")],
    # Atonic seizure
    "HP:0010819": [("SeizureType", "generalized_atonic")],
    # ---- Comorbidity (verified against HPO 2024) ----
    "HP:0001249": [("Comorbidity", "intellectual_disability")],
    "HP:0001256": [("Comorbidity", "intellectual_disability")],  # ID mild
    "HP:0002342": [("Comorbidity", "intellectual_disability")],  # ID moderate
    "HP:0010864": [("Comorbidity", "intellectual_disability")],  # ID severe
    "HP:0002187": [("Comorbidity", "intellectual_disability")],  # ID profound
    "HP:0001263": [("Comorbidity", "developmental_delay")],  # GDD
    "HP:0002376": [("Comorbidity", "developmental_delay")],  # regression
    "HP:0000717": [("Comorbidity", "autism")],  # Autism
    "HP:0100543": [("Comorbidity", "cognitive_impairment")],
}


def _parse_obo(obo_path: Path) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Return (terms, parents).

    terms[hpo_id] = {
        'name': str, 'synonyms': list[str], 'def': str, 'xrefs': list[str],
        'is_obsolete': bool, 'is_a': list[str],
    }
    parents[hpo_id] = list[hpo_id]  (transitive closure computed separately)
    """
    terms: dict[str, dict] = {}
    current: Optional[dict] = None
    current_id: Optional[str] = None

    syn_re = re.compile(r'^synonym:\s+"([^"]+)"')
    def_re = re.compile(r'^def:\s+"([^"]+)"')

    with obo_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("[Term]"):
                if current is not None and current_id is not None:
                    terms[current_id] = current
                current = {
                    "name": "", "synonyms": [], "def": "", "xrefs": [],
                    "is_obsolete": False, "is_a": [],
                }
                current_id = None
            elif line.startswith("[Typedef]"):
                if current is not None and current_id is not None:
                    terms[current_id] = current
                current = None
                current_id = None
            elif current is None:
                continue
            elif line.startswith("id: "):
                current_id = line[4:].strip()
            elif line.startswith("name: "):
                current["name"] = line[6:].strip()
            elif line.startswith("synonym: "):
                m = syn_re.match(line)
                if m:
                    current["synonyms"].append(m.group(1))
            elif line.startswith("def: "):
                m = def_re.match(line)
                if m:
                    current["def"] = m.group(1)
            elif line.startswith("xref: "):
                current["xrefs"].append(line[6:].strip())
            elif line.startswith("is_obsolete:"):
                current["is_obsolete"] = "true" in line.lower()
            elif line.startswith("is_a: "):
                # "HP:0001250 ! Seizure"
                parts = line[6:].split("!", 1)
                pid = parts[0].strip()
                current["is_a"].append(pid)

        if current is not None and current_id is not None:
            terms[current_id] = current

    parents = {tid: t["is_a"][:] for tid, t in terms.items()}
    return terms, parents


def _descendants(root: str, parents: dict[str, list[str]]) -> set[str]:
    """Return the set of all HPO IDs whose ``is_a`` chain includes ``root``."""
    # Build reverse: child_of[parent] = list of children
    child_of: dict[str, list[str]] = defaultdict(list)
    for cid, plist in parents.items():
        for p in plist:
            child_of[p].append(cid)

    out: set[str] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        for child in child_of.get(node, ()):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--obo", default=str(DEFAULT_OBO))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    obo_path = Path(args.obo)
    if not obo_path.exists():
        print(f"[hpo-enrich] ABORT: {obo_path} not found. "
              f"Download via: curl -sL -o {obo_path} https://purl.obolibrary.org/obo/hp.obo",
              file=sys.stderr)
        return 2

    print(f"[hpo-enrich] Parsing OBO from {obo_path}...")
    terms, parents = _parse_obo(obo_path)
    print(f"[hpo-enrich] Parsed {len(terms):,} HPO terms")

    subtrees: dict[str, set[str]] = {}
    for root in ROOT_TERMS:
        subtrees[root] = _descendants(root, parents) | {root}
        print(f"[hpo-enrich] Root {root} ({terms.get(root, {}).get('name', '?')}) "
              f"→ {len(subtrees[root])} terms")

    # Group by target enum
    enrichment: dict[str, dict[str, dict]] = defaultdict(dict)
    manual_hits: list[dict] = []

    for hpo_id, mappings in HPO_TO_SCHEMA.items():
        t = terms.get(hpo_id)
        if not t:
            continue
        if t["is_obsolete"]:
            continue
        candidate_syns = [t["name"]] + list(t["synonyms"])
        # deduplicate case-insensitively, keep original casing
        seen = set()
        deduped = []
        for s in candidate_syns:
            key = s.lower().strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append(s)
        for (group, value_key) in mappings:
            entry = enrichment[group].setdefault(value_key, {
                "hpo_ids": [], "candidate_synonyms": [],
                "definitions": [], "umls_xrefs": [],
            })
            entry["hpo_ids"].append(hpo_id)
            entry["candidate_synonyms"].extend(deduped)
            if t["def"]:
                entry["definitions"].append(t["def"])
            for x in t["xrefs"]:
                if x.startswith("UMLS:"):
                    entry["umls_xrefs"].append(x.replace("UMLS:", ""))
            manual_hits.append({
                "hpo_id": hpo_id,
                "hpo_name": t["name"],
                "group": group,
                "value_key": value_key,
                "n_new_synonyms": len(deduped),
            })

    # Deduplicate synonyms in each enrichment entry
    for group, values in enrichment.items():
        for vkey, entry in values.items():
            uniq = []
            seen = set()
            for s in entry["candidate_synonyms"]:
                key = s.lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    uniq.append(s)
            entry["candidate_synonyms"] = uniq
            entry["umls_xrefs"] = sorted(set(entry["umls_xrefs"]))
            entry["hpo_ids"] = sorted(set(entry["hpo_ids"]))
            entry["definitions"] = list(dict.fromkeys(entry["definitions"]))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "hpo_terms_parsed": len(terms),
        "root_terms": {
            root: {
                "name": terms.get(root, {}).get("name", "?"),
                "subtree_size": len(subtrees[root]),
                "target_enum_groups": groups,
            }
            for root, groups in ROOT_TERMS.items()
        },
        "manual_mapped_terms": len(HPO_TO_SCHEMA),
        "enrichment": dict(enrichment),
        "hits": manual_hits,
    }
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[hpo-enrich] Wrote report to {out_path}")

    total_syns = sum(
        len(e["candidate_synonyms"])
        for values in enrichment.values() for e in values.values()
    )
    print(f"[hpo-enrich] Total candidate synonyms: {total_syns}")
    print(f"[hpo-enrich] Groups touched: {sorted(enrichment.keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
