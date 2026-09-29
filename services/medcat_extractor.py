"""MedCAT-backed concept extractor for the MedAI-EPI pipeline (arm B1').

Phase 1c deliverable. Takes free text; returns a list of
:class:`LinkedEntity` records with:

- ``text``: the surface form actually matched in the document
- ``cui``: the CUI (or synthetic ``X-<Enum>-<value>`` placeholder for
  rules-only concepts)
- ``sctid``: SNOMED-CT id if the ontology entry has one
- ``label``: canonical label (from the ontology)
- ``enum_class``: name of the schema enum the concept belongs to
  (e.g. ``"SeizureType"``, ``"Medication"``)
- ``enum_value``: the enum's string value key (e.g. ``"focal_aware"``,
  ``"lamotrigine"``) or ``None`` when the CUI is not in our ontology
  and only the fallback linker produced it
- ``char_start`` / ``char_end``: byte offsets in the source text
- ``confidence``: float in [0, 1] — MedCAT's ``acc``/context similarity
- ``linker_tier``: ``"custom"`` (our CDB) or ``"umls_small"`` (fallback)

Design
------
- **Two-tier linking.** ``MedCATExtractor`` first runs our custom CDB
  (built by ``scripts/build_medcat_cdb_epilepsy.py``). Any character
  span it fails to cover can be filled by an optional fallback model
  pack (UMLS-Small MedCAT pack), if a path is supplied. Phase 1c ships
  without the fallback wired (see the deliverable's "PENDING" note);
  the code path is present so Phase 1d can drop the pack in without
  edits here.
- **Determinism.** MedCAT's ``get_entities`` is deterministic for a
  loaded CDB (no sampling in dict-mode). No hidden state between calls.
- **No Vocab required.** For an untrained CDB we pass an empty
  :class:`medcat.vocab.Vocab`; MedCAT 2.9's linker calls into the
  Vocab even when the disambiguation branch is not needed, and an
  uninitialised Vocab throws :class:`TypeError`. An empty Vocab makes
  the disambiguation code path a no-op while still allowing dict-based
  name matching (which is what we want for a fresh CDB).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rules.epilepsy_ontology import (  # noqa: E402
    ConceptEntry,
    all_enum_ontologies,
    supplementary_ontologies,
)


@dataclass
class LinkedEntity:
    """One MedCAT-linked concept mention.

    Char offsets are half-open (``text[char_start:char_end] == text``).

    Phase 2 additions (populated by :meth:`MedCATExtractor.attach_context`):

    - ``is_negated``: NEGATED_EXISTENCE from medspaCy ConText.
    - ``is_historical``: HISTORICAL from medspaCy ConText.
    - ``is_hypothetical``: HYPOTHETICAL from medspaCy ConText.
    - ``is_family``: FAMILY (non-patient experiencer) from medspaCy ConText.
    - ``sentence_text``: text of the enclosing sentence (populated when the
      char-offset → spaCy token mapping succeeded).
    - ``sentence_start``: char offset of the enclosing sentence (``-1`` if
      the mapping failed).
    """
    text: str
    cui: str
    sctid: Optional[str]
    label: str
    enum_class: Optional[str]
    enum_value: Optional[str]
    char_start: int
    char_end: int
    confidence: float
    linker_tier: str  # "custom" | "umls_small"
    type_ids: list[str] = field(default_factory=list)
    detected_name: Optional[str] = None
    # Phase 2: medspaCy ConText attributes.
    is_negated: bool = False
    is_historical: bool = False
    is_hypothetical: bool = False
    is_family: bool = False
    sentence_text: str = ""
    sentence_start: int = -1
    # Phase 4: canonical section name (from rules.us_note_structure) or None
    # when the mention falls outside any detected section (or the doc had
    # no recognisable structure).
    section_type: Optional[str] = None
    # Free-form ConText detail (categories → modifier surface forms), retained
    # for debugging / audit trails. Not part of the schema.
    context: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Ontology index: cui -> (enum_class, enum_value, ConceptEntry)
# ---------------------------------------------------------------------------

def _synthetic_cui(group_name: str, value_key: str) -> str:
    """Build the synthetic placeholder CUI used when an ontology entry has
    neither ``cui`` nor ``sctid`` (rules-only enums, catch-alls, etc.).

    Uppercased to match MedCAT's CDBMaker behaviour, which upper-cases all
    ingested CUIs.
    """
    safe = value_key.replace(" ", "_").replace("/", "_")
    return f"X-{group_name}-{safe}".upper()


def _build_ontology_index() -> dict[str, tuple[str, str, ConceptEntry]]:
    """Build a reverse map ``CUI -> (enum_class, enum_value, entry)``.

    Includes synthetic placeholder CUIs (``X-<Enum>-<value>``) since the
    CDB stores those verbatim. All keys are upper-cased to match MedCAT's
    CDBMaker behaviour.
    """
    index: dict[str, tuple[str, str, ConceptEntry]] = {}
    for group_name, oto in all_enum_ontologies().items():
        for value_key, entry in oto.items():
            cui = entry.cui.strip().upper() if entry.cui else _synthetic_cui(group_name, value_key)
            # First writer wins — enum ontologies take precedence over
            # supplementary ontologies on collision (unlikely).
            index.setdefault(cui, (group_name, value_key, entry))
    for group_name, oto in supplementary_ontologies().items():
        for value_key, entry in oto.items():
            cui = entry.cui.strip().upper() if entry.cui else _synthetic_cui(group_name, value_key)
            index.setdefault(cui, (group_name, value_key, entry))
    return index


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

class MedCATExtractor:
    """Load a custom CDB (+ optional fallback pack) and extract entities."""

    def __init__(
        self,
        custom_cdb_path: str | os.PathLike,
        umls_small_pack_path: Optional[str] = None,
        *,
        verbose: bool = False,
    ) -> None:
        self.custom_cdb_path = str(custom_cdb_path)
        self.umls_small_pack_path = umls_small_pack_path
        self.verbose = verbose

        self._ontology_index = _build_ontology_index()
        self._custom_cat = self._load_custom_cat(self.custom_cdb_path)
        self._fallback_cat = self._load_fallback_cat(umls_small_pack_path)

    # ---- Loaders --------------------------------------------------------

    def _load_custom_cat(self, cdb_path: str):
        from medcat.cdb.cdb import CDB
        from medcat.cat import CAT
        from medcat.vocab import Vocab

        cdb = CDB.load(cdb_path)
        # Empty Vocab keeps disambiguation code path safe on an untrained CDB.
        # We *do not* enable training here — this is pure dict-mode linking.
        vocab = Vocab()
        cat = CAT(cdb=cdb, vocab=vocab, config=cdb.config)
        if self.verbose:
            info = cdb.get_basic_info()
            print(f"[MedCATExtractor] custom CDB loaded: {info}")
        return cat

    def _load_fallback_cat(self, pack_path: Optional[str]):
        if not pack_path:
            return None
        if not os.path.exists(pack_path):
            if self.verbose:
                print(
                    f"[MedCATExtractor] Fallback pack path {pack_path!r} does "
                    f"not exist; skipping UMLS-Small tier."
                )
            return None
        from medcat.cat import CAT
        cat = CAT.load_model_pack(pack_path)
        if self.verbose:
            print(f"[MedCATExtractor] Fallback UMLS-Small pack loaded from {pack_path}")
        return cat

    # ---- Public API -----------------------------------------------------

    def extract(self, text: str) -> list[LinkedEntity]:
        """Extract linked entities from ``text``.

        Runs the custom CDB first; the optional UMLS-Small fallback runs
        on the same text and its entities are kept only if they don't
        overlap a span already found by the custom tier.
        """
        primary = self._run_cat(self._custom_cat, text, tier="custom")

        if self._fallback_cat is None:
            return primary

        covered = _span_intervals(primary)
        fallback_all = self._run_cat(self._fallback_cat, text, tier="umls_small")
        fallback = [
            e for e in fallback_all if not _overlaps_any(e, covered)
        ]
        return primary + fallback

    # ---- Phase 4: SOAP section attachment ------------------------------

    @staticmethod
    def attach_section_context(entities: list[LinkedEntity], sections) -> int:
        """Populate each entity's ``section_type`` field from ``sections``.

        Thin wrapper around
        :func:`rules.context_config_us.apply_section_context` — kept as a
        classmethod here so callers can chain
        ``extractor.attach_section_context(entities, sections)`` in the same
        style as :meth:`extract_with_context`.

        Returns the number of entities that received a section tag.
        """
        # Local import: keeps the module importable without spaCy when the
        # section detector isn't needed (e.g. unit tests of the linker).
        from rules.context_config_us import apply_section_context
        return apply_section_context(entities, list(sections or []))

    # ---- Phase 2: medspaCy ConText attachment --------------------------

    def extract_with_context(
        self,
        text: str,
        nlp,
    ) -> tuple[list[LinkedEntity], "any"]:
        """Extract entities and attach medspaCy ConText attributes.

        Convenience one-shot: runs MedCAT, builds a spaCy ``Doc`` on the
        same text via ``nlp``, injects our MedCAT entities as ``doc.ents``
        BEFORE the ConText component runs, so ConText decorates them.

        Returns ``(entities, doc)``. ``entities`` is the ``LinkedEntity``
        list with ``is_negated`` / ``is_historical`` / ``is_hypothetical``
        / ``is_family`` / ``sentence_text`` / ``sentence_start`` populated.
        """
        entities = self.extract(text)
        doc = attach_medspacy_context(entities, text, nlp)
        return entities, doc

    # ---- Internals ------------------------------------------------------

    def _run_cat(self, cat, text: str, *, tier: str) -> list[LinkedEntity]:
        """Run one MedCAT instance and map its entities to :class:`LinkedEntity`."""
        if cat is None or not text:
            return []
        result = cat.get_entities(text)
        # MedCAT returns either an Entities pydantic-like object or a
        # dict with an "entities" key mapping int-id -> entity dict.
        entities_map = result.get("entities", {}) if isinstance(result, dict) else getattr(result, "entities", {})
        out: list[LinkedEntity] = []
        for _, raw in entities_map.items():
            le = self._to_linked_entity(raw, tier=tier)
            if le is not None:
                out.append(le)
        # Deterministic order: by char_start, then by span length descending
        # (so longer, more specific matches on the same start come first).
        out.sort(key=lambda e: (e.char_start, -(e.char_end - e.char_start), e.cui))
        return out

    def _to_linked_entity(self, raw: dict, *, tier: str) -> Optional[LinkedEntity]:
        try:
            cui = str(raw.get("cui") or "").strip().upper()
            start = int(raw.get("start"))
            end = int(raw.get("end"))
            surface = str(raw.get("source_value") or "")
            pretty = str(raw.get("pretty_name") or "") or cui
        except (TypeError, ValueError):
            return None
        if not cui or end <= start:
            return None

        acc = raw.get("acc")
        try:
            confidence = float(acc) if acc is not None else 1.0
        except (TypeError, ValueError):
            confidence = 1.0

        # Resolve ontology metadata if this CUI is in our custom CDB.
        enum_class: Optional[str] = None
        enum_value: Optional[str] = None
        sctid: Optional[str] = None
        label = pretty
        onto = self._ontology_index.get(cui)
        if onto is not None:
            enum_class, enum_value, entry = onto
            sctid = entry.sctid
            label = entry.label or pretty

        type_ids = raw.get("type_ids") or []
        if not isinstance(type_ids, list):
            type_ids = list(type_ids)

        return LinkedEntity(
            text=surface,
            cui=cui,
            sctid=sctid,
            label=label,
            enum_class=enum_class,
            enum_value=enum_value,
            char_start=start,
            char_end=end,
            confidence=confidence,
            linker_tier=tier,
            type_ids=list(type_ids),
            detected_name=raw.get("detected_name"),
            context=None,
        )


# ---------------------------------------------------------------------------
# Span-overlap helpers (kept private to this module)
# ---------------------------------------------------------------------------

def _span_intervals(entities: list[LinkedEntity]) -> list[tuple[int, int]]:
    return [(e.char_start, e.char_end) for e in entities]


def _overlaps_any(e: LinkedEntity, intervals: list[tuple[int, int]]) -> bool:
    for s, t in intervals:
        if e.char_start < t and s < e.char_end:
            return True
    return False


def _select_non_overlapping(spans: list):
    """Return a maximal non-overlapping subset of ``spans`` favouring
    longer spans on ties. Uses greedy interval selection over token
    offsets (``span.start``, ``span.end``).
    """
    if not spans:
        return []
    # Sort by (start, -length) so longer spans win on same start.
    ordered = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
    out = []
    last_end = -1
    for s in ordered:
        if s.start >= last_end:
            out.append(s)
            last_end = s.end
    return out


def attach_medspacy_context(entities: list[LinkedEntity], text: str, nlp) -> "any":
    """Run the medspaCy pipeline on ``text`` with MedCAT's entities pre-set
    as ``doc.ents``, then copy ConText attributes back onto each
    :class:`LinkedEntity`.

    Order of operations (deliberate)
    --------------------------------
    1. Build a bare ``Doc`` via ``nlp.make_doc(text)``.
    2. Resolve each entity's char-span → spaCy ``Span``; drop spans whose
       char offsets don't align with any spaCy token boundary (even under
       ``alignment_mode='expand'``).
    3. Attach a maximal non-overlapping subset of those spans as
       ``doc.ents``.
    4. Run each pipeline component (sentencizer, ConText) manually via
       ``nlp.pipeline`` — this way ConText decorates *our* ents.
    5. Copy ``span._.is_negated`` / etc onto each ``LinkedEntity``.

    Entities whose char-span could not be resolved keep their dataclass
    defaults (all context flags ``False``, ``sentence_start = -1``,
    ``sentence_text = ""``); a warning is emitted for the first few.

    Returns the populated :class:`spacy.tokens.Doc`.
    """
    doc = nlp.make_doc(text)

    spacy_spans = []
    idx_to_span: list[Optional[int]] = []
    for e in entities:
        span = doc.char_span(e.char_start, e.char_end, label="MEDAI_EPI")
        if span is None:
            span = doc.char_span(
                e.char_start, e.char_end,
                label="MEDAI_EPI", alignment_mode="expand",
            )
        if span is None:
            idx_to_span.append(None)
        else:
            idx_to_span.append(len(spacy_spans))
            spacy_spans.append(span)

    selected = _select_non_overlapping(spacy_spans)
    selected_set = {(s.start, s.end) for s in selected}
    if selected:
        try:
            doc.set_ents(selected)
        except (ValueError, TypeError):  # pragma: no cover - spaCy internal
            doc.set_ents(selected, default="unmodified")

    # Run the pipeline manually so ConText sees our ents.
    for _name, component in nlp.pipeline:
        doc = component(doc)

    # Copy attributes back.
    for e, spacy_idx in zip(entities, idx_to_span):
        if spacy_idx is None:
            continue
        span = spacy_spans[spacy_idx]
        # If ConText re-tokenised or moved the span, look it up by char.
        # (Rare — spaCy is deterministic on same text.)
        sent = span.sent
        e.sentence_text = sent.text
        e.sentence_start = sent.start_char

        if (span.start, span.end) in selected_set:
            e.is_negated = bool(getattr(span._, "is_negated", False))
            e.is_historical = bool(getattr(span._, "is_historical", False))
            e.is_hypothetical = bool(getattr(span._, "is_hypothetical", False))
            e.is_family = bool(getattr(span._, "is_family", False))
            mods = list(getattr(span._, "modifiers", []) or [])
            if mods:
                mod_records = []
                for m in mods:
                    tok_span = getattr(m, "modifier_span", None)
                    try:
                        mtext = doc[tok_span[0]:tok_span[1]].text if tok_span else ""
                    except Exception:  # pragma: no cover
                        mtext = ""
                    mod_records.append({"category": m.category, "text": mtext})
                e.context = {"modifiers": mod_records}
    return doc


__all__ = ["LinkedEntity", "MedCATExtractor", "attach_medspacy_context"]
