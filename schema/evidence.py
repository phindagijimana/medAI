"""Evidence-wrapped values for MedAI-EPI (§12 evidence grounding).

Every non-metadata field in the ontology is wrapped in Evidence[T]. A field
without documentation uses value=None with certainty=NOT_DOCUMENTED and no
evidence_text.
"""

from __future__ import annotations

from datetime import date
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import Certainty, DocumentType, TemporalStatus

T = TypeVar("T")


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    doc_type: DocumentType
    doc_date: date
    patient_id: str
    # v0.2.1 — optional structured coding metadata from the EHR encounter header
    icd10cm_codes: list[str] = Field(default_factory=list)
    snomed_ct_codes: list[str] = Field(default_factory=list)


class Evidence(BaseModel, Generic[T]):
    """Value + provenance for a single phenotype field.

    Rules:
    - value=None ⇒ certainty must be NOT_DOCUMENTED or UNKNOWN, evidence_text must be None.
    - value is a concrete assertion ⇒ evidence_text is required (minimal sufficient span).
    - char_start/char_end are optional; only populate when offsets are robust.
    """

    model_config = ConfigDict(extra="forbid")

    value: T | None = None
    certainty: Certainty = Certainty.NOT_DOCUMENTED
    temporal_status: TemporalStatus = TemporalStatus.UNSPECIFIED
    evidence_text: str | None = None
    source_doc_id: str
    source_doc_type: DocumentType
    source_date: date
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _consistency(self) -> "Evidence[T]":
        if self.value is None:
            if self.certainty not in (Certainty.NOT_DOCUMENTED, Certainty.UNKNOWN, Certainty.NEGATED):
                raise ValueError(
                    "value=None requires certainty in {NOT_DOCUMENTED, UNKNOWN, NEGATED}"
                )
            if self.certainty == Certainty.NOT_DOCUMENTED and self.evidence_text is not None:
                raise ValueError("NOT_DOCUMENTED must have evidence_text=None")
        else:
            if self.certainty == Certainty.NOT_DOCUMENTED:
                raise ValueError("value present but certainty=NOT_DOCUMENTED")
            if not self.evidence_text or not self.evidence_text.strip():
                raise ValueError("value present requires non-empty evidence_text")

        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must both be set or both None")
        if self.char_start is not None and self.char_end is not None:
            if self.char_end <= self.char_start:
                raise ValueError("char_end must be > char_start")
        return self

    @classmethod
    def not_documented(
        cls,
        source_doc_id: str,
        source_doc_type: DocumentType,
        source_date: date,
    ) -> "Evidence[T]":
        """Convenience constructor for the common absent-field case."""
        return cls(
            value=None,
            certainty=Certainty.NOT_DOCUMENTED,
            temporal_status=TemporalStatus.UNSPECIFIED,
            evidence_text=None,
            source_doc_id=source_doc_id,
            source_doc_type=source_doc_type,
            source_date=source_date,
        )
