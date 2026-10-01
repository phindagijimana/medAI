"""Chain-of-Three orchestrator: Prepare → Reason → Verify → Publish.

Compendium pages 6-7 define four stages with explicit contracts at each
boundary.  This module wires the components together:

    Prepare       → services.us_note_preprocessing  (canonicalises
                    headers, segments, hashes)
    Reason A      → services.phenotype_assembler    (B1' MedCAT+Rules,
                    the ExECT-US specialist channel)
    Reason B      → LLM backend (optional in v0; the specialist alone
                    already drives most output)
    Reason C      → services.ontology_candidates    (candidate retrieval
                    + LLM selection; in v0 we auto-pick the top candidate
                    emitted by B1')
    Verify        → schema + hard + policy checks → ValidatorVerdict
    Publish       → services.ledger.EvidenceLedger

v0 goal (user directive: *"usable model in an app"*): the pipeline must
be callable end-to-end from one function:

    pipeline = ChainPipeline()
    stats = pipeline.extract(
        note_text=..., document_id=..., ledger=ledger)

Each extracted Evidence[T] from the specialist is converted to a Claim,
validated, assigned a ValidatorVerdict, and routed via ledger.publish().

The LLM reasoner is a late addition — in v0 the specialist does the
heavy lifting and the LLM path is reserved for review items where the
reviewer sees candidate alternatives.  This is deliberate: the compendium
treats the LLM as *interpreter*, not *authority*.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from schema.claim import (
    Assertion, Claim, Experiencer, ReasonCode, TemporalStatus,
    ValidatorVerdict, Versions, claim_from_evidence,
)


logger = logging.getLogger(__name__)


# ─── Config ──────────────────────────────────────────────────────────────

@dataclass
class ChainPipelineConfig:
    """Knobs for the pipeline. Freeze these in run manifests."""
    rules_version: str = "medai-epi-rules-v0.2.1"
    pipeline_version: str = "chain-of-three-v0.1"
    ontology_release: str = "medai-enum-v0.2.1+ilae2017"
    min_confidence_for_accept: float = 0.0   # unused in v0 (no calibrated conf)
    auto_accept_detectors: tuple[str, ...] = ("exect_us",)  # specialist alone can accept
    require_llm_for_accept: bool = False
    section_whitelist_for_auto_accept: tuple[str, ...] = (
        "assessment", "medications", "diagnostic_studies", "history_of_present_illness",
    )
    enable_preprocessing: bool = True


@dataclass
class ExtractionStats:
    n_claims_emitted: int = 0
    n_accepted: int = 0
    n_review: int = 0
    n_rejected: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    def tally(self, verdict: ValidatorVerdict, reasons: list[ReasonCode]) -> None:
        self.n_claims_emitted += 1
        if verdict == ValidatorVerdict.ACCEPT:
            self.n_accepted += 1
        elif verdict == ValidatorVerdict.REVIEW:
            self.n_review += 1
        elif verdict == ValidatorVerdict.REJECT:
            self.n_rejected += 1
        for r in reasons:
            self.reasons[r.value] = self.reasons.get(r.value, 0) + 1


# ─── Orchestrator ────────────────────────────────────────────────────────

class ChainPipeline:
    """The Prepare → Reason → Verify → Publish wiring.

    v0 scope: deterministic path (specialist + candidate service +
    validator) end-to-end.  LLM reasoning hooks are declared but default
    to no-op; wiring in Med42 / DeepSeek is additive and does not change
    the public API.
    """

    def __init__(
        self,
        config: Optional[ChainPipelineConfig] = None,
        *,
        extractor: Any = None,   # services.medcat_extractor.MedCATExtractor
        assembler: Any = None,   # services.phenotype_assembler.PhenotypeAssembler
        candidate_service: Any = None,  # services.ontology_candidates.OntologyCandidateService
        llm_backend: Any = None,         # optional
    ):
        self.cfg = config or ChainPipelineConfig()
        self._extractor = extractor
        self._assembler = assembler
        self._candidate_service = candidate_service
        self._llm = llm_backend
        self._lazy_init_done = False

    def _lazy_init(self) -> None:
        """Load the heavy components once, on first extract call."""
        if self._lazy_init_done:
            return
        if self._assembler is None:
            from services.medcat_extractor import MedCATExtractor
            from services.phenotype_assembler import PhenotypeAssembler
            from pathlib import Path
            cdb = Path(__file__).resolve().parent.parent / "data" / "medcat_cdb_epilepsy" / "cdb"
            if self._extractor is None:
                self._extractor = MedCATExtractor(str(cdb), verbose=False)
            self._assembler = PhenotypeAssembler(self._extractor)
        if self._candidate_service is None:
            from services.ontology_candidates import OntologyCandidateService
            self._candidate_service = OntologyCandidateService(release=self.cfg.ontology_release)
        self._lazy_init_done = True

    # ---- Public API ----------------------------------------------------

    def extract(
        self,
        note_text: str,
        *,
        document_id: str,
        ledger: Any = None,       # services.ledger.EvidenceLedger
        doc_date: str = "2026-01-01",
        return_claims: bool = False,
    ) -> ExtractionStats | tuple[ExtractionStats, list[Claim]]:
        """Run the full chain on one note.

        If a ``ledger`` is supplied, each resulting Claim is published to
        it (ACCEPT → claims, REVIEW → queue, REJECT → audit).
        Returns an ExtractionStats; pass ``return_claims=True`` for both.
        """
        self._lazy_init()
        stats = ExtractionStats()
        claims: list[Claim] = []

        # ── Prepare ──
        text = self._prepare(note_text)

        # ── Reason A: specialist (B1' MedCAT+Rules) ──
        pheno = self._reason_specialist(text, document_id=document_id, doc_date=doc_date)
        if pheno is None:
            return (stats, claims) if return_claims else stats

        # ── Reason C: for every Evidence output, retrieve candidates, pick top ──
        # (v0 skips Reason B / LLM detection — specialist already provides spans.)
        for ev, section, field_type in self._iter_evidence(pheno, text):
            claim = self._evidence_to_claim(
                ev=ev, source_text=text, document_id=document_id,
                section=section, field_type=field_type,
            )

            # ── Verify ──
            self._verify(claim, field_type=field_type)

            # ── Publish ──
            stats.tally(claim.validator_verdict, claim.reason_codes)
            if ledger is not None:
                ledger.publish(claim)
            claims.append(claim)

        if return_claims:
            return stats, claims
        return stats

    # ---- Stage implementations -----------------------------------------

    def _prepare(self, text: str) -> str:
        """Normalise + canonicalise section headers (reversible)."""
        if not self.cfg.enable_preprocessing:
            return text
        try:
            from services.us_note_preprocessing import preprocess_note
            processed, _ = preprocess_note(
                text,
                canonicalize_headers=True,
                annotate_ilae=False,  # keep offsets stable
                annotate_drugs=False,
            )
            return processed
        except Exception as e:
            logger.warning(f"preprocess failed, using raw text: {e}")
            return text

    def _reason_specialist(self, text: str, *, document_id: str, doc_date: str):
        """Run B1' MedCAT+Rules."""
        from datetime import date as _date
        from schema.enums import DocumentType
        try:
            dd = _date.fromisoformat(doc_date)
        except Exception:
            dd = _date(2026, 1, 1)
        try:
            pheno = self._assembler.process(
                text, doc_id=document_id, doc_type=DocumentType.PROGRESS_NOTE,
                doc_date=dd,
            )
            return pheno
        except Exception as e:
            logger.exception(f"specialist extraction failed: {e}")
            return None

    def _iter_evidence(self, pheno, text: str):
        """Walk all populated Evidence[T] fields in an EpilepsyPhenotype.

        Yields (evidence_dict, section_label, field_type_dotted_path).
        """
        pheno_dict = pheno.model_dump() if hasattr(pheno, "model_dump") else pheno
        for mod_name, module in (pheno_dict or {}).items():
            if not isinstance(module, dict) or mod_name in ("document", "schema_version"):
                continue
            for fld, val in module.items():
                field_path = f"{mod_name}.{fld}"
                section = _section_hint(mod_name)
                # Scalar Evidence[T] wrapper
                if isinstance(val, dict) and "value" in val and val.get("value") is not None:
                    yield val, section, field_path
                # List of Evidence[T] wrappers
                elif isinstance(val, list):
                    for ev in val:
                        if isinstance(ev, dict) and "value" in ev and ev.get("value") is not None:
                            yield ev, section, field_path

    def _evidence_to_claim(
        self, *, ev: dict, source_text: str, document_id: str,
        section: str, field_type: str,
    ) -> Claim:
        """Build a Claim from an Evidence[T], attaching a retrieved candidate."""
        # Attempt candidate retrieval if we have a quote
        mention_text = (ev.get("evidence_text") or "").strip()
        concept_system = "MEDAI-ENUM"
        concept_id = str(ev.get("value") or "unknown")
        concept_label = concept_id
        candidate_rank = 1

        if mention_text and self._candidate_service is not None:
            cands = self._candidate_service.get_candidates(
                mention=mention_text, field_type=field_type, k=5,
            )
            if cands:
                top = cands[0]
                concept_system = top.system
                concept_id = top.id
                concept_label = top.label
                candidate_rank = 1

        # Map Evidence certainty / temporal_status → claim labels
        certainty = (ev.get("certainty") or "").lower()
        temporal = (ev.get("temporal_status") or "").lower()

        assertion = _assertion_from_certainty(certainty)
        experiencer = Experiencer.PATIENT  # v0: specialist doesn't yet emit experiencer per-field
        temporal_status = _temporal_from_evidence(temporal)

        claim = claim_from_evidence(
            ev,
            document_id=document_id,
            source_text=source_text,
            section=section,
            concept_system=concept_system,
            concept_id=concept_id,
            concept_label=concept_label,
            ontology_release=self.cfg.ontology_release,
            assertion=assertion,
            experiencer=experiencer,
            temporal_status=temporal_status,
            detectors=["exect_us"],
            candidate_rank=candidate_rank,
            model_confidence=None,
            versions=Versions(
                model="",
                prompt="",
                rules=self.cfg.rules_version,
                retriever=self.cfg.ontology_release,
                pipeline=self.cfg.pipeline_version,
            ),
            initial_verdict=ValidatorVerdict.REVIEW,  # Verify will re-decide
        )
        return claim

    # ---- Verify --------------------------------------------------------

    def _verify(self, claim: Claim, *, field_type: str) -> None:
        """Apply hard + policy checks; mutate claim.validator_verdict in place.

        Hard failures → REJECT.  Policy flags → REVIEW.  Otherwise ACCEPT.
        """
        reasons: list[ReasonCode] = list(claim.reason_codes)

        # Hard: OFFSETS_UNRESOLVED already added by claim_from_evidence
        if ReasonCode.OFFSETS_UNRESOLVED in reasons:
            claim.validator_verdict = ValidatorVerdict.REJECT
            claim.reason_codes = reasons
            return

        # Hard: label vs concept id sanity (MEDAI-ENUM fallback is always valid)
        if not claim.concept.id or not claim.concept.label:
            reasons.append(ReasonCode.INVALID_CODE)
            claim.validator_verdict = ValidatorVerdict.REJECT
            claim.reason_codes = reasons
            return

        # Hard: quote hash must match the current mention
        import hashlib as _h
        expected = _h.sha256(claim.mention.text.encode("utf-8")).hexdigest()
        if expected != claim.mention.sha256:
            reasons.append(ReasonCode.QUOTE_MISMATCH)
            claim.validator_verdict = ValidatorVerdict.REJECT
            claim.reason_codes = reasons
            return

        # Policy: uncertain / hypothetical never auto-accept
        if claim.assertion == Assertion.UNCERTAIN:
            reasons.append(ReasonCode.UNCERTAIN_ASSERTION)
            claim.validator_verdict = ValidatorVerdict.REVIEW
            claim.reason_codes = reasons
            return
        if claim.assertion == Assertion.HYPOTHETICAL:
            reasons.append(ReasonCode.HYPOTHETICAL_ASSERTION)
            claim.validator_verdict = ValidatorVerdict.REVIEW
            claim.reason_codes = reasons
            return

        # Policy: family experiencer → review
        if claim.experiencer == Experiencer.FAMILY:
            reasons.append(ReasonCode.FAMILY_EXPERIENCER)
            claim.validator_verdict = ValidatorVerdict.REVIEW
            claim.reason_codes = reasons
            return

        # Policy: medication-derived phenotype inference is never auto
        if field_type.startswith("clinical_seizure") and claim.detectors == ["exect_us"] \
                and claim.concept.system == "MEDAI-ENUM":
            # Specialist linked only to our internal enum — a weak code source.
            reasons.append(ReasonCode.SPECIFICITY_UNSUPPORTED)
            claim.validator_verdict = ValidatorVerdict.REVIEW
            claim.reason_codes = reasons
            return

        # Otherwise accept
        reasons.append(ReasonCode.ACCEPT_SPECIALIST_LLM_AGREE if "llm" in claim.detectors
                       else ReasonCode.ACCEPT_UNANIMOUS)
        claim.validator_verdict = ValidatorVerdict.ACCEPT
        claim.reason_codes = reasons


# ─── Mapping helpers ────────────────────────────────────────────────────

def _section_hint(module_name: str) -> str:
    return {
        "clinical_seizure": "history",
        "medication":       "medications",
        "mri":              "diagnostic_studies",
        "eeg":              "diagnostic_studies",
        "clinical_history": "history",
        "comorbidities":    "history",
        "family_history":   "family_history",
    }.get(module_name, "unknown")


def _assertion_from_certainty(certainty: str) -> Assertion:
    c = certainty.lower()
    if c in ("negated",):
        return Assertion.ABSENT
    if c in ("possible", "probable"):
        return Assertion.UNCERTAIN
    if c in ("hypothetical",):
        return Assertion.HYPOTHETICAL
    return Assertion.PRESENT  # includes "definite" and empty


def _temporal_from_evidence(temporal: str) -> TemporalStatus:
    t = temporal.lower()
    if t in ("current", ""):
        return TemporalStatus.CURRENT
    if t in ("historical", "past"):
        return TemporalStatus.HISTORICAL
    if t == "resolved":
        return TemporalStatus.RESOLVED
    if t == "recurrent":
        return TemporalStatus.RECURRENT
    if t == "hypothetical":
        return TemporalStatus.UNKNOWN  # Hypothetical shows up in Assertion, not here
    return TemporalStatus.UNKNOWN


__all__ = ["ChainPipeline", "ChainPipelineConfig", "ExtractionStats"]
