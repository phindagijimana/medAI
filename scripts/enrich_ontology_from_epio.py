"""Batch A D2 — enrich the epilepsy ontology from EPIO (Epilepsy Ontology).

EPIO is authored by Fraunhofer SCAI (`SCAI-BIO/EpilepsyOntology`) and published
at https://purl.obolibrary.org/obo/epio.owl (RDF/XML, ~3 MB).

BioPortal API is behind an API key gate and returned 401 for anonymous
requests during Batch A execution (2026-09-29). We fall back to parsing the
raw OWL directly — this gives us:

- prefLabel (from ``rdfs:label`` / ``obo:IAO_0000118``)
- synonyms (from ``oboInOwl:hasExactSynonym``, ``hasRelatedSynonym``, etc.)
- UMLS xrefs (from ``skos:closeMatch`` / ``oboInOwl:hasDbXref``)
- definitions (``obo:IAO_0000115``)

The script does NOT edit the ontology in-place; it emits a JSON report to
``.cache/epio/epio_enrichment_report.json`` that a subsequent patch step
folds into ``rules/epilepsy_ontology.py`` with source_provenance ``EPIO 2024``.

Idempotent — safe to re-run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_OWL = REPO_ROOT / ".cache" / "epio" / "epio.owl"
DEFAULT_OUT = REPO_ROOT / ".cache" / "epio" / "epio_enrichment_report.json"

# Namespaces used in the EPIO OWL file.
NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "obo": "http://purl.obolibrary.org/obo/",
    "oboInOwl": "http://www.geneontology.org/formats/oboInOwl#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "efo": "http://www.ebi.ac.uk/efo/",
    "epio": "https://bio.scai.fraunhofer.de/ontology/epilepsy#",
}


def _tag(prefix: str, local: str) -> str:
    return f"{{{NS[prefix]}}}{local}"


def _text_or_none(elem) -> Optional[str]:
    if elem is None:
        return None
    t = "".join(elem.itertext()).strip()
    return t or None


def _parse_epio(owl_path: Path) -> list[dict]:
    """Parse EPIO OWL, return list of concept dicts."""
    print(f"[epio-enrich] Parsing OWL {owl_path} ({owl_path.stat().st_size:,} bytes)...")
    tree = ET.parse(owl_path)
    root = tree.getroot()

    concepts: list[dict] = []
    n_total = 0

    for cls in root.findall(_tag("owl", "Class")):
        n_total += 1
        # rdf:about is the URI/IRI
        iri = cls.attrib.get(_tag("rdf", "about"))
        if not iri:
            continue

        label = _text_or_none(cls.find(_tag("rdfs", "label")))
        definition = _text_or_none(cls.find(_tag("obo", "IAO_0000115")))

        synonyms = []
        for tag_name in ("hasExactSynonym", "hasRelatedSynonym",
                          "hasBroadSynonym", "hasNarrowSynonym"):
            for e in cls.findall(_tag("oboInOwl", tag_name)):
                t = _text_or_none(e)
                if t:
                    synonyms.append(t)

        # EFO / SKOS altLabel
        for e in cls.findall(_tag("skos", "altLabel")):
            t = _text_or_none(e)
            if t:
                synonyms.append(t)
        for e in cls.findall(_tag("efo", "alternative_term")):
            t = _text_or_none(e)
            if t:
                synonyms.append(t)

        # xrefs
        xrefs = []
        for e in cls.findall(_tag("oboInOwl", "hasDbXref")):
            t = _text_or_none(e)
            if t:
                xrefs.append(t)
        for e in cls.findall(_tag("skos", "closeMatch")):
            resource = e.attrib.get(_tag("rdf", "resource"))
            if resource:
                xrefs.append(resource)
        for e in cls.findall(_tag("skos", "exactMatch")):
            resource = e.attrib.get(_tag("rdf", "resource"))
            if resource:
                xrefs.append(resource)

        # is_a parents
        parents = []
        for sub in cls.findall(_tag("rdfs", "subClassOf")):
            r = sub.attrib.get(_tag("rdf", "resource"))
            if r:
                parents.append(r)

        # UMLS CUIs from xrefs (formats: "UMLS:C1234567", or URIs)
        cuis = set()
        for x in xrefs:
            m = re.search(r"C\d{7}", x)
            if m:
                cuis.add(m.group(0))
        if cuis:
            umls_cuis = sorted(cuis)
        else:
            umls_cuis = []

        concept = {
            "iri": iri,
            "label": label,
            "definition": definition,
            "synonyms": synonyms,
            "xrefs": xrefs,
            "umls_cuis": umls_cuis,
            "parents": parents,
        }
        concepts.append(concept)

    print(f"[epio-enrich] Parsed {len(concepts):,} classes ({n_total:,} raw entries)")
    return concepts


# Manual mapping of EPIO CUIs (from hasDbXref) → our ontology (group, value_key).
# Any EPIO concept with a UMLS CUI already in our ontology auto-cross-maps
# (see main()).
def _load_our_cuis() -> dict[str, list[tuple[str, str]]]:
    """Return {cui: [(group_name, value_key)]} for every ontology entry that
    has a CUI populated. Used to auto-cross-map EPIO → us."""
    from rules.epilepsy_ontology import (
        all_enum_ontologies, supplementary_ontologies,
    )
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for group_name, ontology in list(all_enum_ontologies().items()) + list(supplementary_ontologies().items()):
        for value_key, entry in ontology.items():
            if entry.cui:
                out[entry.cui.strip().upper()].append((group_name, value_key))
    return dict(out)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--owl", default=str(DEFAULT_OWL))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    owl_path = Path(args.owl)
    if not owl_path.exists():
        print(f"[epio-enrich] ABORT: {owl_path} not found. "
              f"Download via: curl -sL -o {owl_path} https://purl.obolibrary.org/obo/epio.owl",
              file=sys.stderr)
        return 2

    concepts = _parse_epio(owl_path)

    # Filter EPIO concepts that have a UMLS CUI mapped to something we care about.
    our_cuis = _load_our_cuis()
    enrichment: dict[str, dict[str, dict]] = defaultdict(dict)
    hits = []
    for c in concepts:
        for cui in c["umls_cuis"]:
            targets = our_cuis.get(cui)
            if not targets:
                continue
            for (group, value_key) in targets:
                entry = enrichment[group].setdefault(value_key, {
                    "cui": cui,
                    "candidate_synonyms": [],
                    "definitions": [],
                    "epio_iris": [],
                })
                if c["label"]:
                    entry["candidate_synonyms"].append(c["label"])
                for s in c["synonyms"]:
                    entry["candidate_synonyms"].append(s)
                if c["definition"]:
                    entry["definitions"].append(c["definition"])
                entry["epio_iris"].append(c["iri"])
                hits.append({
                    "cui": cui, "group": group, "value_key": value_key,
                    "epio_label": c["label"],
                    "n_synonyms": len(c["synonyms"]) + (1 if c["label"] else 0),
                })

    # Dedup candidate synonyms
    for group, values in enrichment.items():
        for vkey, entry in values.items():
            seen = set()
            uniq = []
            for s in entry["candidate_synonyms"]:
                key = s.lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    uniq.append(s)
            entry["candidate_synonyms"] = uniq
            entry["definitions"] = list(dict.fromkeys(entry["definitions"]))
            entry["epio_iris"] = sorted(set(entry["epio_iris"]))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "epio_classes_parsed": len(concepts),
        "our_cuis_count": len(our_cuis),
        "hits": hits,
        "enrichment": dict(enrichment),
    }
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[epio-enrich] Wrote report to {out_path}")
    print(f"[epio-enrich] Cross-mapped hits: {len(hits)}")
    print(f"[epio-enrich] Groups touched: {sorted(enrichment.keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
