"""Ontology candidate retrieval service — the O in the LEO chain (Chain-of-Three spec P1.1).

Implements the compendium's *generation-to-selection* principle: instead of
letting the LLM invent identifiers, this service deterministically retrieves
a small candidate list per mention.  The LLM's job is then bounded — pick a
candidate or abstain.

Coverage strategy
-----------------
The compendium (page 10) names HPO + EPIO + RxNorm as target vocabularies
with SNOMED bridges under license.  Candidates come from two sources:

  * Pinned ontology releases (``services.ontology_loaders``): epilepsy-
    relevant subsets of HPO, MONDO, EPIO, SNOMED CT US and RxNorm, each
    candidate tagged with its own release (e.g. ``hpo:2026-09-01``).
    Routed by ``field_type`` via ``_FIELD_SCOPE_ROUTE``.
  * Curated artifacts: ``rules.epilepsy_ontology`` (24 v0.2.1 enum-value
    ConceptEntry maps with UMLS CUIs, SNOMED SCTIDs and synonyms — these
    carry the ``schema_enum_value`` bridge) and
    ``references/exect_v2_ilae_map.csv`` (ILAE 2017 → UMLS/SNOMED).

Every candidate carries ``system``, ``id``, ``label``, ``synonyms``,
``definition``, ``parents``, ``is_obsolete``, and ``release``.

API
---
    svc = OntologyCandidateService()
    cands = svc.get_candidates(
        mention="focal impaired awareness seizures",
        field_type="clinical_seizure.predominant_seizure_type",
        k=10,
    )
    for c in cands:
        print(c.system, c.id, c.label, c.rank_score)

The ``field_type`` is a dotted schema path — the service routes to the
right ontology subset (seizure types → SEIZURE_TYPE_ONTOLOGY etc.).  If
the caller supplies ``field_type=None``, we search all ontologies.

Ranking
-------
Deterministic lexical scoring (compendium page 6):
    1.0  — exact match on preferred label
    0.9  — exact match on any synonym
    0.7  — substring match on label
    0.5  — substring match on synonym
    0.3  — token-Jaccard >= 0.5

Vector scoring is deliberately out of scope for v0.  When we add HPO we
can slot in a sentence-BERT reranker without changing the API.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

REPO = Path(__file__).resolve().parent.parent


# ─── Candidate data class ────────────────────────────────────────────────

@dataclass
class Candidate:
    """One retrieved ontology concept, per the Chain-of-Three claim contract.

    A candidate is what the LLM sees when it selects.  It has enough
    context to disambiguate (label + definition + synonyms + parents) and
    enough provenance to validate (system + id + release).
    """
    system: str                    # "HPO" | "SNOMED" | "UMLS" | "ILAE" | "RxNorm" | "MEDAI-ENUM"
    id: str                        # e.g. "HP:0002121", "C0270833", "focal_impaired_awareness"
    label: str
    synonyms: list[str] = field(default_factory=list)
    definition: Optional[str] = None
    parents: list[str] = field(default_factory=list)
    is_obsolete: bool = False
    release: str = ""              # ontology release identifier or version tag
    # Ranking / debug
    match_type: str = ""           # "exact_label" | "exact_synonym" | "substring" | "jaccard"
    rank_score: float = 0.0
    # v0.2.1 bridge — the internal enum value this candidate corresponds to.
    schema_field: Optional[str] = None
    schema_enum_value: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Field-type → ontology dict routing ──────────────────────────────────
#
# Maps a dotted v0.2.1 schema path to the epilepsy_ontology dict name
# that should be searched first.  A None value means "no specialized
# routing — fall through to the full search".

_FIELD_ONTOLOGY_ROUTE: dict[str, str] = {
    "clinical_seizure.epilepsy_type":            "EpilepsyType",
    "clinical_seizure.predominant_seizure_type": "SeizureType",
    "clinical_seizure.other_seizure_types":      "SeizureType",
    "clinical_seizure.awareness":                "Awareness",
    "clinical_seizure.etiology_category":        "EtiologyCategory",
    "clinical_seizure.focal_motor_onset":        "FocalMotorOnset",
    "clinical_seizure.focal_nonmotor_onset":     "FocalNonmotorOnset",
    "clinical_seizure.status_epilepticus_history": "SeizureType",
    "medication.drug_resistance_status":         "DrugResistanceStatus",
    "medication.surgery_history":                "SurgeryType",
    "medication.non_drug_therapies":             "NonDrugTherapyType",
    "mri.findings":                              "MriFinding",
    "eeg.background":                            "EegBackground",
    "eeg.ied_present":                           "IedType",
}

# Maps a dotted schema path to the release-backed term scopes it may draw
# from (see services.ontology_loaders).  Fields not listed get no release
# candidates; field_type=None searches every scope.
_SEIZURE = ["seizure", "epio"]
_FIELD_SCOPE_ROUTE: dict[str, list[str]] = {
    "clinical_seizure.epilepsy_type":             ["epilepsy", "epio"],
    "clinical_seizure.predominant_seizure_type":  _SEIZURE,
    "clinical_seizure.other_seizure_types":       _SEIZURE,
    "clinical_seizure.awareness":                 _SEIZURE,
    "clinical_seizure.focal_motor_onset":         _SEIZURE,
    "clinical_seizure.focal_nonmotor_onset":      _SEIZURE,
    "clinical_seizure.status_epilepticus_history": _SEIZURE,
    "clinical_seizure.etiology_category":         ["epilepsy", "epio"],
    "clinical_seizure.etiology_specifics":        ["epilepsy", "epio", "mri"],
    "medication.current_asms":                    ["medication"],
    "medication.prior_asms":                      ["medication"],
    "medication.failed_asms":                     ["medication"],
    "eeg.background":                             ["eeg", "epio"],
    "eeg.ied_present":                            ["eeg", "epio"],
    "eeg.ied_findings":                           ["eeg", "epio"],
    "mri.findings":                               ["mri", "epio"],
    "mri.hippocampal_sclerosis":                  ["mri", "epio"],
    "mri.focal_cortical_dysplasia":               ["mri", "epio"],
}

# Tie-break among equally scored candidates: standard ontologies before
# cross-walk IDs before our internal enum.
_SYSTEM_PRIORITY = {"HPO": 0, "MONDO": 1, "EPIO": 2, "SNOMED": 3, "RxNorm": 4, "UMLS": 5, "MEDAI-ENUM": 9}
_MEDICATION_PRIORITY = {**_SYSTEM_PRIORITY, "RxNorm": -1}

# Obsolete terms stay retrievable (so the verifier can flag them) but rank
# below their live replacements.
_OBSOLETE_PENALTY = 0.8

_MIN_SUBSTRING_LEN = 4

_ILAE_SCTID = re.compile(r"/SNOMEDCT_US/\w+/(\d+)\]")


# ─── Text normalization ──────────────────────────────────────────────────

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _tokens(s: str) -> set[str]:
    return {t.lower() for t in _WORD_RE.findall(s or "")}


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ─── Service ─────────────────────────────────────────────────────────────

class OntologyCandidateService:
    """Retrieves candidates for a mention across all bundled ontologies.

    Load-once, query-many.  Thread-safe for reads.
    """

    def __init__(self, release: str = "medai-enum-v0.2.1+ilae2017", *, use_releases: bool = True):
        self._release = release
        self._enum_ontologies = self._load_enum_ontologies()
        self._ilae_map = self._load_ilae_map()
        self._cui_seed = self._load_cui_seed()
        self._terms_by_scope = self._load_release_terms() if use_releases else {}
        self._sct_status, self._curated_issues = self._load_curated_audit() if use_releases else ({}, {})
        self._term_index = {(t.system, t.id): t for ts in self._terms_by_scope.values() for t in ts}

    @staticmethod
    def _load_curated_audit() -> tuple[dict[str, dict], dict[tuple[str, str], set[str]]]:
        """SNOMED release status of curated SCTIDs, and the issue kinds that
        services.curated_code_audit found per (group, key) entry."""
        try:
            from services.curated_code_audit import audit, curated_sctids
            from services.ontology_loaders import snomed_lookup
            status = snomed_lookup(curated_sctids())
            failed: dict[tuple[str, str], set[str]] = {}
            for i in audit():
                failed.setdefault((i.group, i.key), set()).add(i.kind)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"curated code audit unavailable: {e}")
            return {}, {}
        return status, failed

    @staticmethod
    def _load_release_terms() -> dict[str, list]:
        """Group pinned-release terms by scope. Empty if no releases are fetched."""
        try:
            from services.ontology_loaders import load_terms
            terms = load_terms()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"ontology releases unavailable: {e}")
            return {}
        by_scope: dict[str, list] = {}
        for t in terms:
            by_scope.setdefault(t.scope, []).append(t)
        return by_scope

    @property
    def releases_loaded(self) -> bool:
        return bool(self._terms_by_scope)

    # ---- construction --------------------------------------------------

    @staticmethod
    def _load_enum_ontologies() -> dict[str, dict]:
        """Load the 24 ConceptEntry dicts from rules.epilepsy_ontology."""
        from rules.epilepsy_ontology import all_enum_ontologies
        return all_enum_ontologies()

    @staticmethod
    def _load_ilae_map() -> list[dict]:
        """Load ILAE 2017 → UMLS / SNOMED cross-reference rows."""
        p = REPO / "references" / "exect_v2_ilae_map.csv"
        if not p.exists():
            return []
        rows = []
        with p.open() as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                # The CSV uses generic Column1..Column7 headers.  Extract
                # what we can defensively.
                label = (r.get("Column1", "") or "").strip()
                cui = (r.get("Column3", "") or "").strip()
                # Column4 holds a UMLS atom string, "Name [A123/SNOMEDCT_US/PT/54200006]".
                m = _ILAE_SCTID.search(r.get("Column4", "") or "")
                snomed = m.group(1) if m else ""
                synonyms_str = (r.get("Column6", "") or "").strip()
                if not label:
                    continue
                syns = [s.strip() for s in re.split(r"[;,|]", synonyms_str) if s.strip()]
                rows.append({"label": label, "cui": cui, "sctid": snomed, "synonyms": syns})
        return rows

    @staticmethod
    def _load_cui_seed() -> list[dict]:
        p = REPO / "references" / "exect_v2_cui_seed.csv"
        if not p.exists():
            return []
        rows = []
        with p.open() as fh:
            # Skip the leading "# ExECT-V2 CUI seed ..." comment
            first_line = fh.readline()
            if not first_line.startswith("#"):
                fh.seek(0)
            reader = csv.DictReader(fh)
            for r in reader:
                rows.append({
                    "cui": (r.get("cui", "") or "").strip(),
                    "sctid": (r.get("snomed_ct_id", "") or "").strip(),
                    "label": (r.get("preferred_term", "") or "").strip(),
                    "category": (r.get("category", "") or "").strip(),
                    "schema_hints": (r.get("schema_field_hints", "") or "").strip(),
                })
        return rows

    # ---- retrieval -----------------------------------------------------

    def get_candidates(
        self,
        mention: str,
        field_type: Optional[str] = None,
        k: int = 10,
    ) -> list[Candidate]:
        """Return up to k candidates ranked by lexical match strength.

        ``field_type`` is a dotted schema path.  When present, we search the
        matching ontology dict first and only fall through to the full
        search if too few candidates are found.
        """
        mention_norm = _normalize(mention)
        mention_toks = _tokens(mention)
        if not mention_norm:
            return []

        # Which ontology dicts to search, in priority order.
        search_dicts = self._route_dicts(field_type)

        seen_ids: set[tuple[str, str]] = set()
        seen_curated: set[tuple[str, str, str]] = set()
        out: list[Candidate] = []
        for onto_name, onto in search_dicts:
            for enum_val, entry in onto.items():
                # entry: rules.epilepsy_ontology.ConceptEntry
                label = getattr(entry, "label", None) or enum_val
                syns = list(getattr(entry, "synonyms", []) or [])
                cui = getattr(entry, "cui", None)
                sctid = getattr(entry, "sctid", None)

                # Codes the curated-code audit rejected are not emitted.
                issues = self._curated_issues.get((onto_name, enum_val), set())
                if any(k.startswith("sctid_") for k in issues):
                    sctid = None
                if issues & {"cui_name_mismatch", "umls_synonyms_unrelated"}:
                    cui = None

                # One code may back entries in different groups (a resection is
                # both a SurgeryType and a DocumentType); dedupe within a group.
                system, cid = self._pick_system_id(cui, sctid, enum_val)
                key = (system, cid)
                if (onto_name, *key) in seen_curated:
                    continue

                score, mtype = self._score(
                    mention_norm=mention_norm,
                    mention_toks=mention_toks,
                    label=label,
                    synonyms=syns,
                )

                # A curated SNOMED code found in the pinned release takes the
                # release's US preferred term, status and tag; curated wording
                # stays as synonyms.
                release, definition, parents, obsolete = self._release, None, [], False
                sct = self._sct_status.get(cid) if system == "SNOMED" else None
                if sct and sct.get("exists"):
                    term = self._term_index.get(key)
                    pt = sct.get("pt") or label
                    syns = list(dict.fromkeys(
                        [s for s in (label, *syns, *(term.synonyms if term else ())) if s != pt]))
                    rel_score, rel_type = self._score(
                        mention_norm=mention_norm, mention_toks=mention_toks, label=pt, synonyms=syns)
                    if rel_score > score:
                        score, mtype = rel_score, rel_type
                    label = pt
                    release = self._snomed_release()
                    obsolete = not sct.get("active")
                    if term:
                        definition, parents = term.definition, term.parents
                    if obsolete:
                        score *= _OBSOLETE_PENALTY
                if score <= 0.0:
                    continue

                seen_ids.add(key)
                seen_curated.add((onto_name, *key))
                schema_field = field_type if _FIELD_ONTOLOGY_ROUTE.get(field_type or "") == onto_name \
                    else _ONTONAME_TO_SCHEMA_FIELD.get(onto_name)
                out.append(Candidate(
                    system=system,
                    id=cid,
                    label=label,
                    synonyms=syns,
                    definition=definition,
                    parents=parents,
                    is_obsolete=obsolete,
                    release=release,
                    match_type=mtype,
                    rank_score=score,
                    schema_field=schema_field,
                    schema_enum_value=enum_val,
                ))

        # Add ILAE map + CUI seed rows that our enum ontology didn't cover
        for row in self._ilae_map:
            label = row["label"]
            score, mtype = self._score(
                mention_norm=mention_norm,
                mention_toks=mention_toks,
                label=label,
                synonyms=row["synonyms"],
            )
            if score <= 0.0:
                continue
            cui = row["cui"]
            sct = self._sct_status.get(row["sctid"])
            # Only SCTIDs confirmed active in the pinned release are emitted.
            sctid = row["sctid"] if sct and sct.get("active") else None
            system, cid = self._pick_system_id(cui, sctid, label.lower().replace(" ", "_"))
            if (system, cid) in seen_ids:
                continue
            seen_ids.add((system, cid))
            out.append(Candidate(
                system=system, id=cid, label=label, synonyms=row["synonyms"],
                release=self._snomed_release() if sctid else self._release,
                match_type=mtype, rank_score=score * 0.9,
            ))

        # Pinned-release terms for the scopes this field may draw from
        for term in self._route_terms(field_type):
            key = (term.system, term.id)
            if key in seen_ids:
                continue
            score, mtype = self._score(
                mention_norm=mention_norm,
                mention_toks=mention_toks,
                label=term.label,
                synonyms=term.synonyms,
            )
            if score <= 0.0:
                continue
            if term.is_obsolete:
                score *= _OBSOLETE_PENALTY
            seen_ids.add(key)
            out.append(Candidate(
                system=term.system, id=term.id, label=term.label,
                synonyms=term.synonyms, definition=term.definition,
                parents=term.parents, is_obsolete=term.is_obsolete,
                release=term.release, match_type=mtype, rank_score=score,
                schema_field=field_type,
            ))

        priority = _MEDICATION_PRIORITY if (field_type or "").startswith("medication.") else _SYSTEM_PRIORITY
        out.sort(key=lambda c: (-c.rank_score, priority.get(c.system, 8)))
        return out[:k]

    # ---- helpers -------------------------------------------------------

    def _route_dicts(self, field_type: Optional[str]) -> list[tuple[str, dict]]:
        """Return the (name, dict) list to search in priority order."""
        preferred = _FIELD_ONTOLOGY_ROUTE.get(field_type or "")
        pairs = []
        if preferred and preferred in self._enum_ontologies:
            pairs.append((preferred, self._enum_ontologies[preferred]))
        # Then everything else — order doesn't matter, we score independently
        for name, d in self._enum_ontologies.items():
            if name != preferred:
                pairs.append((name, d))
        return pairs

    @staticmethod
    @lru_cache(maxsize=1)
    def _snomed_release() -> str:
        from services.ontology_releases import release_tag
        return release_tag("snomed")

    def _route_terms(self, field_type: Optional[str]) -> list:
        if not self._terms_by_scope:
            return []
        if field_type is None:
            scopes = list(self._terms_by_scope)
        else:
            scopes = _FIELD_SCOPE_ROUTE.get(field_type, [])
        return [t for s in scopes for t in self._terms_by_scope.get(s, ())]

    @staticmethod
    def _pick_system_id(cui: Optional[str], sctid: Optional[str], fallback: str) -> tuple[str, str]:
        """For curated entries: SNOMED, then UMLS, else MEDAI-ENUM."""
        if sctid:
            return ("SNOMED", str(sctid))
        if cui:
            return ("UMLS", str(cui))
        return ("MEDAI-ENUM", fallback)

    @staticmethod
    def _score(
        mention_norm: str,
        mention_toks: set[str],
        label: str,
        synonyms: list[str],
    ) -> tuple[float, str]:
        """Deterministic lexical scoring (compendium page 6)."""
        label_norm = _normalize(label)
        if mention_norm == label_norm:
            return (1.0, "exact_label")
        syn_norms = [_normalize(s) for s in synonyms]
        if mention_norm in syn_norms:
            return (0.9, "exact_synonym")
        # Short strings ("L", "R", "LEV") match inside almost anything, so they
        # only count as exact matches.
        min_sub = _MIN_SUBSTRING_LEN
        if len(mention_norm) >= min_sub and label_norm and mention_norm in label_norm:
            return (0.7, "substring_label")
        if len(label_norm) >= min_sub and label_norm in mention_norm:
            return (0.7, "substring_label_rev")
        for s in syn_norms:
            if len(s) >= min_sub and len(mention_norm) >= min_sub and (mention_norm in s or s in mention_norm):
                return (0.5, "substring_synonym")
        # Token-set overlap
        best_j = 0.0
        for s in [label_norm] + syn_norms:
            j = _jaccard(mention_toks, _tokens(s))
            if j > best_j:
                best_j = j
        if best_j >= 0.5:
            return (0.3 + 0.2 * (best_j - 0.5), "jaccard")
        return (0.0, "")


# Reverse map: ontology dict name → schema dotted path (best-effort).
_ONTONAME_TO_SCHEMA_FIELD: dict[str, str] = {}
for _field, _onto in _FIELD_ONTOLOGY_ROUTE.items():
    _ONTONAME_TO_SCHEMA_FIELD.setdefault(_onto, _field)


__all__ = ["Candidate", "OntologyCandidateService"]
