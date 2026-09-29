"""Abstract base class for per-schema-field extraction rules.

Phase 2 deliverable §2. Each concrete rule subclasses :class:`BaseFieldRule`
and implements :meth:`BaseFieldRule.apply`, returning either an
:class:`schema.evidence.Evidence` or ``None``.

The rule dispatcher (``services/phenotype_assembler.py``) iterates the
registered rules in field-name order and slots their output into the
corresponding attribute of :class:`schema.ontology.EpilepsyPhenotype`.

Design principles
-----------------
- Rules receive **already-linked** entities (``LinkedEntity`` from
  :mod:`services.medcat_extractor`) — they never call MedCAT themselves.
- Rules also receive the spaCy ``Doc`` populated by
  :func:`rules.context_config.build_medspacy_pipeline` so they can inspect
  raw text, sentences, or run local ``spacy.Matcher`` patterns for the
  JAPE-only bits.
- Every ``Evidence[T]`` produced by :meth:`_make_evidence` inherits its
  ``source_*`` fields from a doc-level ``meta`` dict — rules never invent
  provenance.
- Certainty / temporal_status default to ``DEFINITE`` / ``CURRENT`` and
  are downgraded automatically from ConText flags on the source entity.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Iterable, Optional, TypeVar, Union

# Runtime imports guarded to keep base_rule importable without a spaCy install
# in dependency-limited environments (e.g. tests that only need the ontology).
try:  # pragma: no cover - optional import
    from spacy.tokens import Doc  # noqa: F401
except Exception:  # pragma: no cover
    Doc = Any  # type: ignore

from schema.enums import Certainty, DocumentType, TemporalStatus
from schema.evidence import Evidence
from services.medcat_extractor import LinkedEntity

T = TypeVar("T")


class BaseFieldRule(ABC):
    """Abstract base class for one schema-field extraction rule.

    Attributes
    ----------
    field_name
        Dotted path into ``EpilepsyPhenotype`` (e.g.
        ``"clinical_seizure.predominant_seizure_type"``). Used by the
        assembler to know where to write the returned ``Evidence[T]``.
    enum_class
        The Python ``Enum`` subclass whose ``.value`` identifies which
        ``LinkedEntity.enum_value`` rows are candidates. ``None`` for
        free-text / compound-value fields (rule sub-selects manually).
    enum_class_name
        Optional override for the string used to match
        ``LinkedEntity.enum_class`` (defaults to ``enum_class.__name__``).
        Useful when a rule reads entities of a different enum than the
        one it emits.
    """

    field_name: str = ""
    enum_class: Optional[type] = None
    enum_class_name: Optional[str] = None

    # ------------------------------------------------------------------
    # Candidate filtering
    # ------------------------------------------------------------------

    def relevant_entities(
        self,
        entities: Iterable[LinkedEntity],
        *,
        enum_class_name: Optional[str] = None,
        include_negated: bool = False,
        include_family: bool = False,
        include_hypothetical: bool = False,
    ) -> list[LinkedEntity]:
        """Return entities whose ``enum_class`` matches this rule.

        By default excludes entities marked by ConText as negated / family /
        hypothetical (a rule can override by flipping the include flags).
        """
        target_name = enum_class_name or self.enum_class_name
        if target_name is None and self.enum_class is not None:
            target_name = self.enum_class.__name__

        out: list[LinkedEntity] = []
        for e in entities:
            if target_name is not None and e.enum_class != target_name:
                continue
            if not include_negated and e.is_negated:
                continue
            if not include_family and e.is_family:
                continue
            if not include_hypothetical and e.is_hypothetical:
                continue
            out.append(e)
        return out

    # ------------------------------------------------------------------
    # Sentence-scope helpers
    # ------------------------------------------------------------------

    @staticmethod
    def sentence_span(entity: LinkedEntity, doc) -> tuple[int, int]:
        """Return (start_char, end_char) of the sentence enclosing ``entity``.

        Falls back to the entity span itself when ConText attachment failed
        (``entity.sentence_start`` is ``-1``).
        """
        if entity.sentence_start is not None and entity.sentence_start >= 0:
            end = entity.sentence_start + len(entity.sentence_text)
            return entity.sentence_start, end
        return entity.char_start, entity.char_end

    # ------------------------------------------------------------------
    # Evidence construction
    # ------------------------------------------------------------------

    def _make_evidence(
        self,
        value: T,
        entity: LinkedEntity,
        meta: dict[str, Any],
        *,
        certainty: Optional[Certainty] = None,
        temporal_status: Optional[TemporalStatus] = None,
        evidence_text: Optional[str] = None,
    ) -> Evidence[T]:
        """Wrap ``value`` in an :class:`Evidence` with provenance from
        ``entity`` + ``meta``.

        Rules
        -----
        - Certainty defaults to ``DEFINITE`` and is downgraded to
          ``POSSIBLE`` when the source entity carries a ConText
          ``is_hypothetical`` or the caller passes ``certainty=None`` with
          an entity flagged uncertain.
        - Temporal status defaults to ``CURRENT`` and is upgraded to
          ``HISTORICAL`` when ``entity.is_historical``.
        - ``evidence_text`` defaults to ``entity.text`` (the surface span).
        - Char offsets are always populated from the entity.
        """
        if certainty is None:
            if entity.is_hypothetical:
                certainty = Certainty.POSSIBLE
            else:
                certainty = Certainty.DEFINITE
        if temporal_status is None:
            temporal_status = (
                TemporalStatus.HISTORICAL if entity.is_historical else TemporalStatus.CURRENT
            )
        text = evidence_text if evidence_text is not None else entity.text

        return Evidence[T](
            value=value,
            certainty=certainty,
            temporal_status=temporal_status,
            evidence_text=text,
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
            char_start=entity.char_start,
            char_end=entity.char_end,
        )

    def _negated_evidence(
        self,
        entity: LinkedEntity,
        meta: dict[str, Any],
    ) -> Evidence:
        """Convenience: emit a NEGATED Evidence with ``value=None`` when a
        rule wants to record 'this concept was explicitly ruled out'.

        Per :class:`schema.evidence.Evidence` validator: ``value=None`` +
        ``Certainty.NEGATED`` forbids ``evidence_text``, so we drop the
        span text but keep the char offsets on the doc-level meta.
        """
        return Evidence(
            value=None,
            certainty=Certainty.NEGATED,
            temporal_status=TemporalStatus.UNSPECIFIED,
            evidence_text=None,
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
        )

    def _not_documented(self, meta: dict[str, Any]) -> Evidence:
        """Convenience: NOT_DOCUMENTED Evidence for a required field the
        rule couldn't fire on."""
        return Evidence.not_documented(
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
        )

    # ------------------------------------------------------------------
    # Contract
    # ------------------------------------------------------------------

    @abstractmethod
    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Union[Evidence, list[Evidence]]]:
        """Produce an ``Evidence[T]`` (or ``None``) for this rule's field.

        Rules that populate list-valued fields (e.g. ``other_seizure_types``)
        may return ``list[Evidence[T]]`` instead.
        """
        raise NotImplementedError


def make_meta(
    doc_id: str,
    doc_type: DocumentType,
    doc_date: date,
) -> dict[str, Any]:
    """Small factory for the ``meta`` dict rules read from.

    Kept separate from ``BaseFieldRule`` so callers can inline it without
    instantiating a rule.
    """
    return {"doc_id": doc_id, "doc_type": doc_type, "doc_date": doc_date}


__all__ = ["BaseFieldRule", "make_meta"]
