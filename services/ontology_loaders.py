"""Load epilepsy-relevant subsets of the pinned ontology releases.

Reads the files recorded in data/ontologies/MANIFEST.json (see
``services.ontology_releases``) and returns flat ``OntologyTerm`` records
that ``services.ontology_candidates`` can score.  Only the subtrees below
are kept; full SNOMED CT alone is 540k concepts.

    scope           sources (root concept)
    ─────────────   ───────────────────────────────────────────────────────
    seizure         HPO  HP:0001250 Seizure        SNOMED 91175000 Seizure
    epilepsy        MONDO:0005027 epilepsy, MONDO:0015650 epilepsy syndrome,
                    SNOMED 128613002 Seizure disorder
    epio            EPIO native classes (seizure types, EEG patterns, syndromes)
    eeg             HPO  HP:0002353 EEG abnormality
    mri             HPO  HP:0012443 Abnormal brain morphology
    comorbidity     HPO  HP:0001249 Intellectual disability,
                         HP:0001263 Global developmental delay
    medication      RxNorm ingredients in rules/asm_lexicon.py (ATC N03A,
                    curated ASMs, rescue and off-label drugs) with brand +
                    salt-form synonyms

SNOMED terms are labelled with their US English preferred term and carry only
US-acceptable synonyms; only disorders and findings are kept.

Parsing the RF2 / RRF releases takes ~1 minute, so the result is cached
under data/ontologies/_index/, keyed by a hash of the manifest.  A new
release (scripts/fetch_ontologies.py) invalidates the cache automatically.

    from services.ontology_loaders import load_terms
    terms = load_terms()          # list[OntologyTerm]
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from services.ontology_releases import (
    MANIFEST, OntologyReleaseMissing, available, release_path, release_tag,
)

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parent.parent
INDEX_DIR = REPO / "data" / "ontologies" / "_index"
INDEX_FORMAT = 3


@dataclass
class OntologyTerm:
    system: str                 # "HPO" | "MONDO" | "EPIO" | "SNOMED" | "RxNorm"
    id: str
    label: str
    scope: str                  # see module docstring
    synonyms: list[str] = field(default_factory=list)
    definition: Optional[str] = None
    parents: list[str] = field(default_factory=list)
    is_obsolete: bool = False
    replaced_by: Optional[str] = None
    release: str = ""


OBO_SUBSETS: list[tuple[str, str, str, str]] = [
    # (manifest source, system, root id, scope)
    ("hpo", "HPO", "HP:0001250", "seizure"),
    ("hpo", "HPO", "HP:0002353", "eeg"),
    ("hpo", "HPO", "HP:0012443", "mri"),
    ("hpo", "HPO", "HP:0001249", "comorbidity"),
    ("hpo", "HPO", "HP:0001263", "comorbidity"),
    ("mondo", "MONDO", "MONDO:0005027", "epilepsy"),
    ("mondo", "MONDO", "MONDO:0015650", "epilepsy"),
]

# Order matters: a concept under both roots takes the first scope listed, and
# epilepsy disorders also descend from Seizure (finding).
SNOMED_SUBSETS: list[tuple[str, str]] = [
    ("128613002", "epilepsy"),
    ("91175000", "seizure"),
]

_SCT_ACTIVE_ISA = "116680003"
_SCT_FSN = "900000000000003001"
_SCT_SYNONYM = "900000000000013009"
_SCT_US_ENGLISH = "900000000000509007"
_SCT_PREFERRED = "900000000000548007"
_SCT_ACCEPTABLE = "900000000000549004"
_SCT_REPLACED_BY = "900000000000526001"
_SCT_SAME_AS = "900000000000527005"
_SCT_SEMANTIC_TAG = re.compile(r"\s*\(([^()]*)\)\s*$")
# Subtrees under Seizure / Seizure disorder also hold a few situations and
# observables; only disorders and findings are retrievable phenotypes.
SNOMED_KEEP_TAGS = {"disorder", "finding"}


# ─── OBO (HPO, MONDO) ────────────────────────────────────────────────────

_OBO_SYN = re.compile(r'^synonym:\s*"((?:[^"\\]|\\.)*)"\s+(EXACT|RELATED|BROAD|NARROW)')
_OBO_DEF = re.compile(r'^def:\s*"((?:[^"\\]|\\.)*)"')


def _parse_obo(path: Path) -> dict[str, dict]:
    terms: dict[str, dict] = {}
    cur: Optional[dict] = None
    with path.open(encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("["):
                cur = {"synonyms": [], "parents": []} if line == "[Term]" else None
                continue
            if cur is None or not line:
                continue
            if line.startswith("id: "):
                cur["id"] = line[4:].strip()
                terms[cur["id"]] = cur
            elif line.startswith("name: "):
                cur["label"] = line[6:].strip()
            elif line.startswith("is_a: "):
                # MONDO appends axiom annotations: "is_a: MONDO:1 {source=...} ! label"
                cur["parents"].append(line[6:].split()[0])
            elif line.startswith("is_obsolete: true"):
                cur["is_obsolete"] = True
            elif line.startswith("replaced_by: "):
                cur["replaced_by"] = line[13:].strip()
            elif line.startswith("synonym:"):
                m = _OBO_SYN.match(line)
                # BROAD synonyms are too general to retrieve on (e.g. "fit").
                if m and m.group(2) != "BROAD":
                    cur["synonyms"].append(m.group(1).replace('\\"', '"'))
            elif line.startswith("def:"):
                m = _OBO_DEF.match(line)
                if m:
                    cur["definition"] = m.group(1).replace('\\"', '"')
    return terms


def _descendants(roots: Iterable[str], parents: dict[str, list[str]]) -> set[str]:
    children: dict[str, list[str]] = defaultdict(list)
    for child, ps in parents.items():
        for p in ps:
            children[p].append(child)
    seen: set[str] = set()
    stack = [r for r in roots if r in parents or r in children]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(children.get(n, ()))
    return seen


def _load_obo_subsets() -> list[OntologyTerm]:
    out: list[OntologyTerm] = []
    by_source: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for source, system, root, scope in OBO_SUBSETS:
        by_source[source].append((system, root, scope))

    for source, subsets in by_source.items():
        if source not in available():
            logger.warning("ontology release %s not fetched; skipping", source)
            continue
        raw = _parse_obo(release_path(source))
        tag = release_tag(source)
        parents = {tid: t["parents"] for tid, t in raw.items()}
        emitted: set[str] = set()
        for system, root, scope in subsets:
            keep = _descendants([root], parents)
            # Obsolete terms have no is_a; keep them when their replacement is in
            # scope so the verifier can flag OBSOLETE_CODE instead of missing them.
            keep |= {tid for tid, t in raw.items()
                     if t.get("is_obsolete") and t.get("replaced_by") in keep}
            for tid in sorted(keep):
                t = raw[tid]
                if tid in emitted or "label" not in t:
                    continue
                emitted.add(tid)
                out.append(OntologyTerm(
                    system=system, id=tid, label=t["label"], scope=scope,
                    synonyms=sorted(set(t["synonyms"])), definition=t.get("definition"),
                    parents=t["parents"], is_obsolete=bool(t.get("is_obsolete")),
                    replaced_by=t.get("replaced_by"), release=tag,
                ))
    return out


# ─── EPIO (OWL) ──────────────────────────────────────────────────────────

_EPIO_NATIVE = "https://bio.scai.fraunhofer.de/ontology/"
_OBO_PURL = "http://purl.obolibrary.org/obo/"
# Text-mining bins and animal / statistical model classes are not clinical concepts.
_EPIO_EXCLUDE = re.compile(r"TM_BIN|\bmodel$", re.I)


def _epio_id(iri: str) -> str:
    """Native EPIO IRI → local name (may contain '/'); OBO PURL → CURIE (HP:0001250)."""
    if iri.startswith(_EPIO_NATIVE):
        return re.sub(r"^epilepsy#?", "", iri[len(_EPIO_NATIVE):])
    if iri.startswith(_OBO_PURL):
        return iri[len(_OBO_PURL):].replace("_", ":", 1)
    return iri


def _load_epio() -> list[OntologyTerm]:
    if "epio" not in available():
        logger.warning("ontology release epio not fetched; skipping")
        return []
    from scripts.enrich_ontology_from_epio import _parse_epio

    tag = release_tag("epio")
    out = []
    # Classes imported into EPIO from HPO / MONDO come from their own releases.
    for c in _parse_epio(release_path("epio")):
        label = c.get("label")
        if not c["iri"].startswith(_EPIO_NATIVE) or not label or _EPIO_EXCLUDE.search(label):
            continue
        out.append(OntologyTerm(
            system="EPIO", id=_epio_id(c["iri"]), label=label, scope="epio",
            synonyms=sorted(set(c["synonyms"])), definition=c.get("definition"),
            parents=[_epio_id(p) for p in c["parents"]], release=tag,
        ))
    return out


# ─── SNOMED CT (RF2 snapshot) ────────────────────────────────────────────

def _rf2_file(root: Path, pattern: str) -> Path:
    hits = sorted(root.rglob(pattern))
    if not hits:
        raise OntologyReleaseMissing(f"SNOMED RF2 file {pattern} not found under {root}")
    return hits[0]


def _snomed_active(root: Path) -> dict[str, bool]:
    status: dict[str, bool] = {}
    with _rf2_file(root, "Snapshot/Terminology/sct2_Concept_Snapshot_*.txt").open(encoding="utf-8") as f:
        next(f)
        for line in f:
            cols = line.split("\t", 3)
            status[cols[0]] = cols[2] == "1"
    return status


def _snomed_descriptions(root: Path, concept_ids: set[str]) -> dict[str, dict]:
    """US English FSN, preferred term and acceptable synonyms for ``concept_ids``."""
    desc: dict[str, tuple[str, str, str]] = {}      # description id → (concept, type, term)
    with _rf2_file(root, "Snapshot/Terminology/sct2_Description_Snapshot-en_*.txt").open(encoding="utf-8") as f:
        next(f)
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if cols[2] == "1" and cols[4] in concept_ids:
                desc[cols[0]] = (cols[4], cols[6], cols[7])

    out: dict[str, dict] = {cid: {"fsn": None, "pt": None, "acceptable": []} for cid in concept_ids}
    lang = _rf2_file(root, "Snapshot/Refset/Language/der2_cRefset_LanguageSnapshot-en_*.txt")
    with lang.open(encoding="utf-8") as f:
        next(f)
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if cols[2] != "1" or cols[4] != _SCT_US_ENGLISH or cols[5] not in desc:
                continue
            cid, dtype, term = desc[cols[5]]
            rec = out[cid]
            if dtype == _SCT_FSN:
                if cols[6] == _SCT_PREFERRED:
                    rec["fsn"] = term
            elif cols[6] == _SCT_PREFERRED:
                rec["pt"] = term
            elif cols[6] == _SCT_ACCEPTABLE:
                rec["acceptable"].append(term)
    return out


def semantic_tag(fsn: Optional[str]) -> Optional[str]:
    m = _SCT_SEMANTIC_TAG.search(fsn or "")
    return m.group(1) if m else None


def snomed_lookup(concept_ids: Iterable[str]) -> dict[str, dict]:
    """Release status of arbitrary SCTIDs, for validating curated codes.

    Returns ``{sctid: {"exists", "active", "fsn", "pt", "replaced_by"}}``.
    ``replaced_by`` comes from the REPLACED BY / SAME AS association refsets.
    """
    ids = {str(c) for c in concept_ids if c}
    if "snomed" not in available() or not ids:
        return {}
    h = hashlib.sha256(MANIFEST.read_bytes())
    h.update(repr((INDEX_FORMAT, sorted(ids))).encode())
    path = INDEX_DIR / f"sctlookup-{h.hexdigest()[:16]}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = _snomed_lookup_uncached(ids)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    for old in INDEX_DIR.glob("sctlookup-*.json"):
        old.unlink()
    path.write_text(json.dumps(result), encoding="utf-8")
    return result


def _snomed_lookup_uncached(ids: set[str]) -> dict[str, dict]:
    root = release_path("snomed")
    status = _snomed_active(root)
    names = _snomed_descriptions(root, ids)
    replaced: dict[str, str] = {}
    assoc = sorted(root.rglob("Snapshot/Refset/Content/der2_cRefset_AssociationSnapshot*.txt"))
    if assoc:
        with assoc[0].open(encoding="utf-8") as f:
            next(f)
            for line in f:
                cols = line.rstrip("\n").split("\t")
                if cols[2] == "1" and cols[4] in (_SCT_REPLACED_BY, _SCT_SAME_AS) and cols[5] in ids:
                    replaced.setdefault(cols[5], cols[6])
    return {
        cid: {
            "exists": cid in status,
            "active": status.get(cid, False),
            "fsn": names[cid]["fsn"],
            "pt": names[cid]["pt"],
            "replaced_by": replaced.get(cid),
        }
        for cid in ids
    }


def _load_snomed() -> list[OntologyTerm]:
    if "snomed" not in available():
        logger.warning("ontology release snomed not fetched; skipping")
        return []
    root = release_path("snomed")
    tag = release_tag("snomed")

    active = {cid for cid, ok in _snomed_active(root).items() if ok}

    parents: dict[str, list[str]] = defaultdict(list)
    with _rf2_file(root, "Snapshot/Terminology/sct2_Relationship_Snapshot_*.txt").open(encoding="utf-8") as f:
        next(f)
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if cols[2] == "1" and cols[7] == _SCT_ACTIVE_ISA and cols[4] in active:
                parents[cols[4]].append(cols[5])

    keep_scope: dict[str, str] = {}
    for root_id, scope in SNOMED_SUBSETS:
        for cid in _descendants([root_id], parents):
            keep_scope.setdefault(cid, scope)

    names = _snomed_descriptions(root, set(keep_scope))
    out = []
    dropped: dict[str, int] = defaultdict(int)
    for cid, scope in sorted(keep_scope.items()):
        rec = names[cid]
        sem = semantic_tag(rec["fsn"])
        if not rec["pt"] or sem not in SNOMED_KEEP_TAGS:
            dropped[sem or "no US preferred term"] += 1
            continue
        out.append(OntologyTerm(
            system="SNOMED", id=cid, label=rec["pt"], scope=scope,
            synonyms=sorted(set(rec["acceptable"]) - {rec["pt"]}),
            parents=parents.get(cid, []), release=tag,
        ))
    if dropped:
        logger.info("SNOMED subset: dropped %s", dict(dropped))
    return out


# ─── RxNorm (RRF) ────────────────────────────────────────────────────────

def _load_rxnorm() -> list[OntologyTerm]:
    """ASM ingredients from rules/asm_lexicon.py (scripts/build_asm_lexicon.py),
    plus the curated misspellings and abbreviations in MEDICATION_ONTOLOGY."""
    if "rxnorm" not in available():
        logger.warning("ontology release rxnorm not fetched; skipping")
        return []
    from rules.asm_lexicon import ASM_LEXICON, RXNORM_RELEASE
    from rules.epilepsy_ontology import MEDICATION_ONTOLOGY

    tag = release_tag("rxnorm")
    if RXNORM_RELEASE != tag:
        logger.warning("rules/asm_lexicon.py was built from %s but %s is pinned; "
                       "rerun scripts/build_asm_lexicon.py", RXNORM_RELEASE, tag)
    out = []
    for key, d in ASM_LEXICON.items():
        curated = MEDICATION_ONTOLOGY.get(key)
        names = {*d["salts"], *d["brands"], *d["other_names"],
                 *((curated.label, *curated.synonyms) if curated else ())}
        out.append(OntologyTerm(
            system="RxNorm", id=d["rxcui"], label=d["label"], scope="medication",
            synonyms=sorted({s for s in names if s.lower() != d["label"].lower()}),
            release=RXNORM_RELEASE,
        ))
    return out


# ─── Cache + entry point ─────────────────────────────────────────────────

def _cache_key() -> str:
    h = hashlib.sha256(MANIFEST.read_bytes())
    h.update(repr((INDEX_FORMAT, OBO_SUBSETS, SNOMED_SUBSETS, sorted(SNOMED_KEEP_TAGS))).encode())
    try:
        from rules.asm_lexicon import ASM_LEXICON
        from rules.epilepsy_ontology import MEDICATION_ONTOLOGY
        h.update(json.dumps(ASM_LEXICON, sort_keys=True).encode())
        h.update(json.dumps({k: [e.label, *e.synonyms] for k, e in MEDICATION_ONTOLOGY.items()},
                            sort_keys=True).encode())
    except Exception:
        pass
    return h.hexdigest()[:16]


def build_terms() -> list[OntologyTerm]:
    terms: list[OntologyTerm] = []
    for name, fn in (("obo", _load_obo_subsets), ("epio", _load_epio),
                     ("snomed", _load_snomed), ("rxnorm", _load_rxnorm)):
        try:
            part = fn()
        except OntologyReleaseMissing as e:
            logger.warning("skipping %s: %s", name, e)
            continue
        logger.info("loaded %d %s terms", len(part), name)
        terms.extend(part)
    return terms


def load_terms(force: bool = False) -> list[OntologyTerm]:
    """Return all subset terms, from cache when the manifest hasn't changed."""
    if not MANIFEST.exists():
        return []
    path = INDEX_DIR / f"terms-{_cache_key()}.json.gz"
    if path.exists() and not force:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return [OntologyTerm(**d) for d in json.load(f)]
    terms = build_terms()
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    for old in INDEX_DIR.glob("terms-*.json.gz"):
        old.unlink()
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump([asdict(t) for t in terms], f)
    tmp.replace(path)
    return terms


__all__ = ["OntologyTerm", "build_terms", "load_terms", "semantic_tag", "snomed_lookup"]
