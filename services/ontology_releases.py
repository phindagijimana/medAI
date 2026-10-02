"""Resolve pinned ontology releases recorded in data/ontologies/MANIFEST.json.

The manifest is written by ``scripts/fetch_ontologies.py``.  Everything that
reads an ontology file should go through here so that the release recorded
in a Claim is the release that was actually parsed.

    from services.ontology_releases import release_path, release_tag
    obo = release_path("hpo")      # Path to the pinned hp.obo
    tag = release_tag("hpo")       # "hpo:2026-09-01"
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "data" / "ontologies" / "MANIFEST.json"


class OntologyReleaseMissing(FileNotFoundError):
    pass


@lru_cache(maxsize=1)
def manifest() -> dict:
    if not MANIFEST.exists():
        raise OntologyReleaseMissing(
            f"{MANIFEST} not found. Run scripts/fetch_ontologies.py first.")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _entry(source: str) -> dict:
    m = manifest()
    if source not in m:
        raise OntologyReleaseMissing(
            f"'{source}' not in {MANIFEST.name}. Run scripts/fetch_ontologies.py --only {source}.")
    return m[source]


def release_path(source: str) -> Path:
    """Path to the pinned file (OBO/OWL) or, for zipped releases, the extracted directory."""
    e = _entry(source)
    p = REPO / (e.get("extracted_to") or e["files"][0]["path"])
    if not p.exists():
        raise OntologyReleaseMissing(f"{source}: pinned path {p} is missing on disk.")
    return p


def release_tag(source: str) -> str:
    """Stable identifier for Claims / run manifests, e.g. 'hpo:2026-09-01'."""
    return f"{source}:{_entry(source)['release']}"


def available() -> list[str]:
    try:
        return sorted(manifest())
    except OntologyReleaseMissing:
        return []


__all__ = ["OntologyReleaseMissing", "available", "manifest", "release_path", "release_tag"]
