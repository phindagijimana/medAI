"""Ontology candidate retrieval service (Chain-of-Three P1.1).

Implements the compendium's *generation-to-selection* principle: instead of
letting the LLM invent identifiers, this service deterministically retrieves
a small candidate list per mention.  The LLM's job is then bounded — pick a
candidate or abstain.

Coverage strategy
-----------------
The compendium (page 10) names HPO + EPIO + RxNorm as target vocabularies
with SNOMED bridges under license.  We don't yet ship an HPO release on
disk, so the initial implementation builds candidates from artifacts we
DO have:

  * ``rules.epilepsy_ontology`` — 24 v0.2.1 enum-value ConceptEntry maps
    with UMLS CUIs, SNOMED SCTIDs, canonical labels, and curated
    synonyms.
  * ``references/exect_v2_ilae_map.csv`` — ILAE 2017 → UMLS/SNOMED
    mapping table (150 rows).
  * ``references/exect_v2_cui_seed.csv`` — CUI seed with schema field
    hints.

Every candidate carries ``system``, ``id``, ``label``, ``synonyms``,
``definition``, ``parents``, ``is_obsolete``, and ``release`` — the same
shape a future HPO-backed candidate must have.  Swapping HPO in later is
a one-file change: add ``_load_hpo_release()`` and register it in
``_CANDIDATE_SOURCES``.

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
    "clinical_seizure.epilepsy_type":            "EPILEPSY_TYPE_ONTOLOGY",
    "clinical_seizure.predominant_seizure_type": "SEIZURE_TYPE_ONTOLOGY",
    "clinical_seizure.other_seizure_types":      "SEIZURE_TYPE_ONTOLOGY",
    "clinical_seizure.awareness":                "AWARENESS_ONTOLOGY",
    "clinical_seizure.etiology_category":        "ETIOLOGY_CATEGORY_ONTOLOGY",
    "clinical_seizure.focal_motor_onset":        "FOCAL_MOTOR_ONSET_ONTOLOGY",
    "clinical_seizure.focal_nonmotor_onset":     "FOCAL_NONMOTOR_ONSET_ONTOLOGY",
    "clinical_seizure.status_epilepticus_history": "SEIZURE_TYPE_ONTOLOGY",
    "medication.drug_resistance_status":         "DRUG_RESISTANCE_STATUS_ONTOLOGY",
    "medication.surgery_history":                "SURGERY_TYPE_ONTOLOGY",
    "medication.non_drug_therapies":             "NON_DRUG_THERAPY_TYPE_ONTOLOGY",
    "mri.findings":                              "MRI_FINDING_ONTOLOGY",
    "eeg.background":                            "EEG_BACKGROUND_ONTOLOGY",
    "eeg.ied_present":                           "IED_TYPE_ONTOLOGY",
}


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

    def __init__(self, release: str = "medai-enum-v0.2.1+ilae2017"):
        self._release = release
        self._enum_ontologies = self._load_enum_ontologies()
        self._ilae_map = self._load_ilae_map()
        self._cui_seed = self._load_cui_seed()

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
                snomed = (r.get("Column4", "") or "").strip()
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
        out: list[Candidate] = []
        for onto_name, onto in search_dicts:
            for enum_val, entry in onto.items():
                # entry: rules.epilepsy_ontology.ConceptEntry
                label = getattr(entry, "label", None) or enum_val
                syns = list(getattr(entry, "synonyms", []) or [])
                cui = getattr(entry, "cui", None)
                sctid = getattr(entry, "sctid", None)

                system, cid = self._pick_system_id(cui, sctid, enum_val)
                key = (system, cid)
                if key in seen_ids:
                    continue

                score, mtype = self._score(
                    mention_norm=mention_norm,
                    mention_toks=mention_toks,
                    label=label,
                    synonyms=syns,
                )
                if score <= 0.0:
                    continue

                seen_ids.add(key)
                schema_field = _ONTONAME_TO_SCHEMA_FIELD.get(onto_name)
                out.append(Candidate(
                    system=system,
                    id=cid,
                    label=label,
                    synonyms=syns,
                    definition=None,  # ConceptEntry doesn't carry definitions
                    parents=[],
                    is_obsolete=False,
                    release=self._release,
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
            sctid = row["sctid"]
            system, cid = self._pick_system_id(cui, sctid, label.lower().replace(" ", "_"))
            if (system, cid) in seen_ids:
                continue
            seen_ids.add((system, cid))
            out.append(Candidate(
                system=system, id=cid, label=label, synonyms=row["synonyms"],
                release=self._release, match_type=mtype, rank_score=score * 0.9,
            ))

        out.sort(key=lambda c: -c.rank_score)
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
    def _pick_system_id(cui: Optional[str], sctid: Optional[str], fallback: str) -> tuple[str, str]:
        """Prefer HPO if we ever attach it, then SNOMED, UMLS, else MEDAI-ENUM."""
        # (HPO support goes here when a release is loaded)
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
        if label_norm and mention_norm in label_norm:
            return (0.7, "substring_label")
        if label_norm and label_norm in mention_norm:
            return (0.7, "substring_label_rev")
        for s in syn_norms:
            if s and (mention_norm in s or s in mention_norm):
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
_ONTONAME_TO_SCHEMA_FIELD: dict[str, str] = {
    onto_name: field_type for field_type, onto_name in _FIELD_ONTOLOGY_ROUTE.items()
}


__all__ = ["Candidate", "OntologyCandidateService"]
