"""Claim contract for the LEO chain (Chain-of-Three spec P1.2).

Verbatim JSON shape from the compendium page 8.  A Claim is the atomic
unit the pipeline produces: a structured phenotype assertion tied to an
exact source span, a specific ontology concept, and provenance that
makes every decision replayable.

Design rules (compendium page 8):
    * Offsets are authoritative.  The quote is display text; offsets +
      hash prove the evidence came from the source.
    * Null is valid.  Unknown time, code, or confidence must be
      explicit; fabricated completeness is worse than missingness.
    * Concept provenance is immutable.  Ontology updates create mapped
      derivatives, never in-place rewrites.
    * Model confidence is not a probability.  Calibrate against held-out
      labels before using it as a threshold.
    * Reason codes are enumerable.

This module ships:
    * ``Claim``                        — the Pydantic model
    * ``Mention``, ``Concept``, ``Temporality``  — nested components
    * ``ValidatorVerdict``, ``ReasonCode``, ``Assertion``, ``Experiencer``,
      ``TemporalStatus``                — closed enums
    * ``claim_from_evidence(ev, ...)``  — bridge from the existing v0.2.1
      Evidence[T] wrapper to a Claim

The Claim is intentionally JSON-serialisable with ``model_dump()`` so it
round-trips through the ledger and the review UI without custom
encoders.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── Closed enums ────────────────────────────────────────────────────────

class Assertion(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    UNCERTAIN = "uncertain"
    HYPOTHETICAL = "hypothetical"


class Experiencer(str, Enum):
    PATIENT = "patient"
    FAMILY = "family"
    OTHER = "other"


class TemporalStatus(str, Enum):
    CURRENT = "current"
    HISTORICAL = "historical"
    RESOLVED = "resolved"
    RECURRENT = "recurrent"
    UNKNOWN = "unknown"


class ValidatorVerdict(str, Enum):
    """Routing decision assigned by services.chain_pipeline during Verify."""
    ACCEPT = "accept"
    REVIEW = "review"
    REJECT = "reject"


class ReasonCode(str, Enum):
    """Enumerable reasons the validator flagged a claim.

    This is the authoritative list — rejecting or routing without a
    reason code is a bug.
    """
    # Hard failures (reject)
    SCHEMA_INVALID = "schema_invalid"
    OFFSETS_UNRESOLVED = "offsets_unresolved"
    QUOTE_MISMATCH = "quote_mismatch"
    INVALID_CODE = "invalid_code"
    LABEL_CODE_MISMATCH = "label_code_mismatch"
    OBSOLETE_CODE = "obsolete_code"
    # Policy flags (review)
    UNCERTAIN_ASSERTION = "uncertain_assertion"
    HYPOTHETICAL_ASSERTION = "hypothetical_assertion"
    SPECIFICITY_UNSUPPORTED = "specificity_unsupported"
    FAMILY_EXPERIENCER = "family_experiencer"
    SOURCE_DISAGREEMENT = "source_disagreement"
    MEDICATION_DERIVED = "medication_derived"
    LOW_CONFIDENCE = "low_confidence"
    MULTI_CANDIDATE_TIE = "multi_candidate_tie"
    LLM_ONLY = "llm_only"  # LLM proposed it, the specialist did not: never auto-accepted
    # Specialist proposed a drug, the LLM listed other drugs but not this one: not auto-accepted
    SPECIALIST_ONLY_UNCONFIRMED = "specialist_only_unconfirmed"
    # Drug given as a one-off dose during the encounter (IV load, ED bolus ...), not the regimen
    ACUTE_ADMINISTRATION = "acute_administration"
    # As-needed seizure-emergency drug (rescue); informational, the claim is judged like any other
    RESCUE_ROLE = "rescue_role"
    # The model ran, but no reader covers this field: a single-reader claim, never auto-accepted
    NO_SECOND_READER = "no_second_reader"
    # Ontology: the selector abstained or the retriever had no exact hit (code stays MEDAI-ENUM)
    ONTOLOGY_ABSTAIN = "ontology_abstain"
    # Ontology: the selector picked a retrieved candidate (informational)
    ONTOLOGY_SELECTED = "ontology_selected"
    # Accept
    # One detector made the claim and no second source contradicted or was asked to confirm it
    ACCEPT_UNANIMOUS = "accept_unanimous"
    ACCEPT_SPECIALIST_LLM_AGREE = "accept_specialist_llm_agree"


# ─── Nested components ───────────────────────────────────────────────────

class Mention(BaseModel):
    """The source text span that supports this claim."""
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="Exact source substring (display text)")
    start: int = Field(..., ge=0, description="Half-open char start offset")
    end: int = Field(..., ge=0, description="Half-open char end offset")
    sha256: str = Field(..., description="SHA-256 of the exact substring")

    @classmethod
    def from_span(cls, source_text: str, start: int, end: int) -> "Mention":
        """Build a mention from source text + offsets, hashing the slice."""
        if start < 0 or end > len(source_text) or start >= end:
            raise ValueError(f"invalid span [{start}:{end}] for text len={len(source_text)}")
        quoted = source_text[start:end]
        h = hashlib.sha256(quoted.encode("utf-8")).hexdigest()
        return cls(text=quoted, start=start, end=end, sha256=h)


class Concept(BaseModel):
    """The ontology concept this claim is bound to."""
    model_config = ConfigDict(extra="forbid")

    system: str = Field(..., description="e.g. HPO, SNOMED, UMLS, RxNorm, MEDAI-ENUM")
    id: str = Field(..., description="Stable identifier in the system")
    label: str = Field(..., description="Preferred label at the pinned release")
    ontology_release: str = Field(..., description="Frozen release identifier")


class Temporality(BaseModel):
    """Temporal scope of the claim."""
    model_config = ConfigDict(extra="forbid")

    status: TemporalStatus = TemporalStatus.UNKNOWN
    onset: Optional[str] = None       # free-form onset expression if present
    resolution: Optional[str] = None  # free-form resolution expression
    text: Optional[str] = None        # source-supported expression


class Versions(BaseModel):
    """Versioned artifacts that produced this claim — essential for replay."""
    model_config = ConfigDict(extra="allow")

    model: str = ""
    prompt: str = ""
    rules: str = ""
    retriever: str = ""
    pipeline: str = ""


# ─── Top-level Claim ─────────────────────────────────────────────────────

class Claim(BaseModel):
    """A structured phenotype assertion with full provenance.

    Mirrors the compendium page 8 JSON exactly. Every field is required
    at the schema level; the validator decides whether the claim is
    ACCEPT / REVIEW / REJECT.
    """
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(..., description="Run-scoped UUID")
    document_id: str = Field(..., description="Pseudonymous study ID")
    section: str = Field(..., description="family_history | history | assessment | ...")

    mention: Mention
    concept: Concept

    # Which schema field this claim populates and the value it asserts.  The
    # compendium JSON identifies a claim by concept alone; these two optional
    # fields make a claim self-describing (reviewer UI, field-level scoring).
    field_path: Optional[str] = Field(
        None, description="Schema field, e.g. 'clinical_seizure.epilepsy_type'")
    value: Optional[Any] = Field(
        None, description="Value asserted for field_path (enum string, number or object)")

    assertion: Assertion
    experiencer: Experiencer
    temporality: Temporality

    detectors: list[str] = Field(
        default_factory=list,
        description="Which detectors fired: e.g. ['llm', 'epextra']",
    )
    candidate_rank: int = Field(1, ge=1, description="Rank of the selected candidate in retrieval")
    model_confidence: Optional[float] = Field(
        None,
        description="Model's self-reported confidence; NOT a calibrated probability",
    )

    alternative: Optional[str] = Field(
        None,
        description=(
            "Value proposed by the dissenting detector when the specialist and the "
            "LLM disagree (reason code source_disagreement). Shown to the reviewer; "
            "null when the detectors agree or only one fired."
        ),
    )

    # Ontology arm (retriever + optional Arm E selector).  extra=forbid, so these are explicit.
    ontology_match: str = Field(
        "none",
        description="none | exact | selected | abstain — how the concept id was bound",
    )
    ontology_candidates: list[dict] = Field(
        default_factory=list,
        description="Top retrieved candidates shown to the selector (index, system, id, label, rank_score)",
    )
    code_accepted: bool = Field(
        False,
        description="True only when the value is accepted AND the code is an exact hit or a selector pick "
                    "(never MEDAI-ENUM)",
    )

    validator_verdict: ValidatorVerdict = ValidatorVerdict.REVIEW
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    versions: Versions = Field(default_factory=Versions)

    # Audit timestamp — not in the compendium schema but useful for the ledger.
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def new_id(cls) -> str:
        return str(uuid.uuid4())


# ─── Bridge from Evidence[T] → Claim ─────────────────────────────────────

def claim_from_evidence(
    evidence: dict,
    *,
    document_id: str,
    source_text: str,
    section: str = "unknown",
    concept_system: str = "MEDAI-ENUM",
    concept_id: Optional[str] = None,
    concept_label: Optional[str] = None,
    ontology_release: str = "medai-enum-v0.2.1",
    assertion: Assertion = Assertion.PRESENT,
    experiencer: Experiencer = Experiencer.PATIENT,
    temporal_status: TemporalStatus = TemporalStatus.CURRENT,
    detectors: Optional[list[str]] = None,
    candidate_rank: int = 1,
    model_confidence: Optional[float] = None,
    versions: Optional[Versions] = None,
    initial_verdict: ValidatorVerdict = ValidatorVerdict.REVIEW,
    initial_reasons: Optional[list[ReasonCode]] = None,
) -> Claim:
    """Convert one v0.2.1 Evidence[T] dict to a Claim.

    Expected ``evidence`` keys (compatible with services.phenotype_assembler
    output):
        - ``value``: the extracted value (used to fill concept_id if not given)
        - ``evidence_text``: the quoted substring
        - ``char_start`` / ``char_end``: offsets
        - ``certainty`` / ``temporal_status``: may inform routing
    """
    ev_text = (evidence.get("evidence_text") or "").strip()
    cs = evidence.get("char_start")
    ce = evidence.get("char_end")

    if cs is None or ce is None or not ev_text:
        # Try to find the quote in source text — a lenient fallback for
        # Evidence objects that lack offsets.
        if ev_text and source_text:
            idx = source_text.find(ev_text)
            if idx >= 0:
                cs, ce = idx, idx + len(ev_text)

    if cs is None or ce is None:
        # Degenerate case: emit the claim with zero-length span at 0.  The
        # validator will catch this and reject.
        mention = Mention(text=ev_text or "", start=0, end=0,
                          sha256=hashlib.sha256(b"").hexdigest())
        reasons = list(initial_reasons or []) + [ReasonCode.OFFSETS_UNRESOLVED]
        verdict = ValidatorVerdict.REJECT
    else:
        try:
            mention = Mention.from_span(source_text, cs, ce)
            reasons = list(initial_reasons or [])
            verdict = initial_verdict
        except ValueError:
            mention = Mention(text=ev_text, start=0, end=len(ev_text),
                              sha256=hashlib.sha256(ev_text.encode("utf-8")).hexdigest())
            reasons = list(initial_reasons or []) + [ReasonCode.OFFSETS_UNRESOLVED]
            verdict = ValidatorVerdict.REJECT

    # Default concept from Evidence.value if caller didn't give one.
    if concept_id is None:
        v = evidence.get("value")
        concept_id = str(v) if v is not None else "unknown"
    if concept_label is None:
        concept_label = str(evidence.get("value") or concept_id)

    temporality = Temporality(
        status=temporal_status,
        text=None,
    )

    return Claim(
        claim_id=Claim.new_id(),
        document_id=document_id,
        section=section,
        mention=mention,
        concept=Concept(
            system=concept_system,
            id=concept_id,
            label=concept_label,
            ontology_release=ontology_release,
        ),
        assertion=assertion,
        experiencer=experiencer,
        temporality=temporality,
        detectors=detectors or [],
        candidate_rank=candidate_rank,
        model_confidence=model_confidence,
        validator_verdict=verdict,
        reason_codes=reasons,
        versions=versions or Versions(),
    )


__all__ = [
    "Claim", "Mention", "Concept", "Temporality", "Versions",
    "Assertion", "Experiencer", "TemporalStatus",
    "ValidatorVerdict", "ReasonCode",
    "claim_from_evidence",
]
