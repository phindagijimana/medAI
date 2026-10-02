"""LEO chain orchestrator: Prepare → Reason → Verify → Publish.

LEO = LLM + EpExtra + Ontology, our implementation of the Chain-of-Three
spec.  EpExtra is our US adaptation of ExECT (Fonferko-Shadrach et al.):
ExECT-V2 rules ported onto MedCAT.  The three components corroborate one
another; none is the sole authority.

Compendium pages 6-7 define four stages with explicit contracts at each
boundary.  This module wires the components together:

    Prepare       → services.us_note_preprocessing  (canonicalises
                    headers, segments, hashes)
    Reason A      → services.phenotype_assembler    (B1' MedCAT+Rules,
                    the EpExtra specialist channel)
    Reason B      → services.chain_llm  (Med42-8B, optional; live or
                    replayed from run manifests).  Agreement with the
                    specialist is the accept signal; the LLM never
                    accepts a fact on its own
    Reason C      → services.ontology_candidates    (candidate retrieval;
                    the top candidate is adopted only on an exact
                    label/synonym hit, otherwise the claim keeps its
                    internal enum ID and goes to review)
    Verify        → schema + hard + policy checks → ValidatorVerdict
    Publish       → services.ledger.EvidenceLedger

v0 goal (user directive: *"usable model in an app"*): the pipeline must
be callable end-to-end from one function:

    pipeline = ChainPipeline()
    stats = pipeline.extract(
        note_text=..., document_id=..., ledger=ledger)

Each extracted Evidence[T] from the specialist is converted to a Claim,
validated, assigned a ValidatorVerdict, and routed via ledger.publish().

The LLM reasoner is optional (``llm_reasoner=``).  Without it the chain
is specialist-only (leo-v0.1 behaviour).  With it, specialist and LLM
values are fused per field by ``services.chain_llm.fuse``: agreement adds
the ``llm`` detector, disagreement routes to review with the LLM value
shown as ``Claim.alternative``, and LLM-only facts are never auto-accepted.
This is deliberate: the compendium treats the LLM as *interpreter*, not
*authority*.
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

SPECIALIST_DETECTOR = "epextra"


# ─── Config ──────────────────────────────────────────────────────────────

# Field path of a drug given once during the encounter; kept for the reviewer, outside current_asms.
ACUTE_FIELD_PATH = "medication.acute_administration"
RESCUE_FIELD_PATH = "medication.rescue_medication"
_PLACEHOLDER_VALUES = {"undefined", "not_assessed", "not assessed", "not_applicable"}


@dataclass
class ChainPipelineConfig:
    """Knobs for the pipeline. Freeze these in run manifests."""
    rules_version: str = "medai-epi-rules-v0.2.1"
    pipeline_version: str = "leo-v0.5"
    ontology_release: str = "medai-enum-v0.2.1+ilae2017"
    min_confidence_for_accept: float = 0.0   # unused in v0 (no calibrated conf)
    min_candidate_score: float = 0.9         # exact label (1.0) or exact synonym (0.9)
    auto_accept_detectors: tuple[str, ...] = (SPECIALIST_DETECTOR,)  # specialist alone can accept
    require_llm_for_accept: bool = False
    section_whitelist_for_auto_accept: tuple[str, ...] = (
        "assessment", "medications", "diagnostic_studies", "history_of_present_illness",
    )
    enable_preprocessing: bool = True
    # On a scalar specialist/LLM disagreement, which side's value becomes the claim.
    # {"clinical_seizure.epilepsy_type": "llm", ...}; absent = "specialist".  Chosen on
    # development letters only (docs/EVAL_PROTOCOL_LEO.md 10.3), never on the held-out set.
    disagree_primary: dict = field(default_factory=dict)
    # Locate a span for LLM-only values whose own quote is not in the note.
    ground_llm_values: bool = True
    # Seizure-frequency values with no counts and no period (specialist placeholder) are not claims.
    drop_empty_frequency: bool = True
    # A specialist-only drug is not auto-accepted when the LLM listed other drugs but not this one.
    specialist_only_drug_review: bool = True
    # One-off drug administrations (IV load, ED dose) are routed to review, outside current_asms.
    acute_administration_filter: bool = True
    # As-needed seizure-rescue drugs (PRN, buccal/intranasal/rectal, "rescue") are kept apart from
    # the maintenance regimen: field path medication.rescue_medication, not current_asms.
    rescue_role_split: bool = True
    # The specialist marks a frequency PROBABLE only when the note says "about/approximately N"
    # (rules/fields/seizure_frequency.py).  That is an approximate quantity, not an uncertain
    # assertion, so it is read as asserted; otherwise no approximate frequency can auto-accept.
    approx_frequency_is_asserted: bool = True
    llm_arm: str = ""   # provenance label of the LLM arm, e.g. "M3" (set by the caller)


@dataclass
class ExtractionStats:
    n_claims_emitted: int = 0
    n_accepted: int = 0
    n_review: int = 0
    n_rejected: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    # LLM channel (all zero when no reasoner is attached)
    llm_available: bool = False
    n_llm_agree: int = 0          # specialist claim corroborated by the LLM
    n_llm_disagree: int = 0       # scalar field, different values
    n_specialist_only: int = 0    # specialist claim the LLM did not produce
    n_llm_only: int = 0           # LLM claim with a verbatim quote, routed to review
    n_placeholders_dropped: int = 0   # specialist schema defaults not turned into claims
    n_empty_frequency_dropped: int = 0   # empty seizure-frequency values (no counts, no period)
    n_specialist_only_unconfirmed: int = 0  # specialist-only drugs sent to review: LLM listed others
    n_acute_rerouted: int = 0     # one-off drug administrations kept out of current_asms
    n_rescue_routed: int = 0      # as-needed rescue drugs kept out of current_asms
    n_llm_grounded: int = 0       # subset of n_llm_only whose span was found by value grounding, not by the model's quote
    n_llm_unsupported: int = 0    # LLM claim whose quote is not in the note

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
        llm_backend: Any = None,         # optional Med42Backend -> wrapped in LiveLLMReasoner
        llm_reasoner: Any = None,        # optional callable(text, doc_id, doc_date) -> phenotype dict
    ):
        self.cfg = config or ChainPipelineConfig()
        self._extractor = extractor
        self._assembler = assembler
        self._candidate_service = candidate_service
        self._llm = llm_backend
        if llm_reasoner is None and llm_backend is not None:
            from services.chain_llm import LiveLLMReasoner
            llm_reasoner = LiveLLMReasoner(llm_backend, arm=self.cfg.llm_arm or "M3")
        self._llm_reasoner = llm_reasoner
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

        # ── Reason B: LLM phenotype (optional) ──
        from services.chain_llm import fuse, flatten
        llm_pheno = self._reason_llm(text, document_id=document_id, doc_date=doc_date)
        stats.llm_available = llm_pheno is not None

        spec_items = flatten(
            pheno.model_dump(mode="json") if hasattr(pheno, "model_dump") else pheno)
        # Schema defaults ("undefined", "not_assessed") are not findings; emitting them as claims
        # only produces rejects (audit finding F1: valid is not populated).
        n0 = len(spec_items)
        spec_items = [it for it in spec_items
                      if not (isinstance(it.ev.get("value"), str)
                              and it.ev["value"].strip().lower() in _PLACEHOLDER_VALUES)]
        stats.n_placeholders_dropped = n0 - len(spec_items)
        llm_items = flatten(llm_pheno) if llm_pheno is not None else []
        if self.cfg.drop_empty_frequency:
            from services.chain_llm import is_empty_frequency
            n1 = len(spec_items) + len(llm_items)
            keep = lambda it: not (it.field_path.endswith("seizure_frequency")
                                   and is_empty_frequency(it.ev.get("value")))
            spec_items = [it for it in spec_items if keep(it)]
            llm_items = [it for it in llm_items if keep(it)]
            stats.n_empty_frequency_dropped = n1 - len(spec_items) - len(llm_items)
        llm_has_meds = any(it.field_path == "medication.current_asms" for it in llm_items)
        if llm_pheno is not None:
            fusion = fuse(spec_items, llm_items)
            fused_spec = fusion.specialist
            llm_only = fusion.llm_only
        else:
            from services.chain_llm import FusedSpecialist
            fused_spec = [FusedSpecialist(it, "specialist_only") for it in spec_items]
            llm_only = []

        # ── Reason C + Verify + Publish, specialist claims ──
        for fs in fused_spec:
            it = fs.item
            detectors = [SPECIALIST_DETECTOR]
            initial: list[ReasonCode] = []
            alternative = None
            swapped = False
            if (llm_pheno is not None and fs.status == "disagree" and fs.llm_item is not None
                    and self.cfg.disagree_primary.get(it.field_path) == "llm"):
                swapped_ev = self._llm_evidence(fs.llm_item, text)
                if swapped_ev is not None:
                    from services.chain_llm import display_value
                    spec_display = display_value(it.ev.get("value"))
                    it = fs.llm_item
                    it = type(it)(field_path=it.field_path, module=it.module, ev=swapped_ev, multi=it.multi)
                    detectors = ["llm"]
                    swapped = True
            if llm_pheno is not None:
                if fs.status == "agree":
                    detectors.append("llm")
                    stats.n_llm_agree += 1
                elif fs.status == "disagree":
                    initial.append(ReasonCode.SOURCE_DISAGREEMENT)
                    alternative = spec_display if swapped else fs.alternative
                    stats.n_llm_disagree += 1
                else:
                    stats.n_specialist_only += 1
            role, _rule = self._drug_role(it.field_path, it.ev, text)
            acute = role == "acute"
            rescue = role == "rescue"
            if acute:
                initial.append(ReasonCode.ACUTE_ADMINISTRATION)
                stats.n_acute_rerouted += 1
            elif rescue:
                initial.append(ReasonCode.RESCUE_ROLE)
                stats.n_rescue_routed += 1
            if (not acute and self.cfg.specialist_only_drug_review and fs.status == "specialist_only"
                    and it.field_path == "medication.current_asms" and llm_has_meds):
                initial.append(ReasonCode.SPECIALIST_ONLY_UNCONFIRMED)
                stats.n_specialist_only_unconfirmed += 1
            claim = self._evidence_to_claim(
                ev=it.ev, source_text=text, document_id=document_id,
                section=_section_hint(it.module), field_type=it.field_path,
                detectors=detectors, initial_reasons=initial,
            )
            claim.alternative = alternative
            if acute:
                claim.field_path = ACUTE_FIELD_PATH
            elif rescue:
                claim.field_path = RESCUE_FIELD_PATH
            self._finish(claim, field_type=it.field_path, stats=stats, ledger=ledger)
            claims.append(claim)

        # ── LLM-only claims: verbatim quote required, never auto-accepted ──
        from services.chain_llm import locate_quote
        for it in llm_only:
            ev = dict(it.ev)
            span = locate_quote(ev.get("evidence_text") or "", text)
            grounded = False
            if span is None and getattr(self.cfg, "ground_llm_values", True):
                from services.chain_llm import ground_value
                span = ground_value(it.field_path, ev.get("value"), text)
                grounded = span is not None
            if span is not None:
                ev["char_start"], ev["char_end"] = span
                ev["evidence_text"] = text[span[0]:span[1]]
            else:
                ev["char_start"] = ev["char_end"] = None
            role, _rule = self._drug_role(it.field_path, ev, text)
            acute = role == "acute"
            rescue = role == "rescue"
            if acute:
                stats.n_acute_rerouted += 1
            elif rescue:
                stats.n_rescue_routed += 1
            claim = self._evidence_to_claim(
                ev=ev, source_text=text, document_id=document_id,
                section=_section_hint(it.module), field_type=it.field_path,
                detectors=["llm"],
                initial_reasons=([ReasonCode.ACUTE_ADMINISTRATION] if acute else
                                 [ReasonCode.RESCUE_ROLE] if rescue else []),
            )
            if acute:
                claim.field_path = ACUTE_FIELD_PATH
            elif rescue:
                claim.field_path = RESCUE_FIELD_PATH
            if span is None:
                stats.n_llm_unsupported += 1
            else:
                stats.n_llm_only += 1
                stats.n_llm_grounded += int(grounded)
            self._finish(claim, field_type=it.field_path, stats=stats, ledger=ledger)
            claims.append(claim)

        if return_claims:
            return stats, claims
        return stats

    # ---- Stage implementations -----------------------------------------

    def _drug_role(self, field_path: str, ev: dict, text: str) -> tuple[str, Optional[str]]:
        """("acute" | "rescue" | "maintenance", rule) for a current-ASM mention.

        Each role has its own switch; a disabled role is reported as maintenance."""
        if field_path != "medication.current_asms" or not (
                self.cfg.acute_administration_filter or self.cfg.rescue_role_split):
            return "maintenance", None
        from services.chain_llm import locate_quote
        from services.med_context import drug_role
        start, end = ev.get("char_start"), ev.get("char_end")
        if start is None or end is None:
            span = locate_quote(ev.get("evidence_text") or "", text)
            if span is None:
                return "maintenance", None
            start, end = span
        role, rule = drug_role(text, int(start), int(end))
        if role == "acute" and not self.cfg.acute_administration_filter:
            from services.med_context import rescue_role
            r = rescue_role(text, int(start), int(end))
            role, rule = ("rescue", r) if r else ("maintenance", None)
        if role == "rescue" and not self.cfg.rescue_role_split:
            return "maintenance", None
        return role, rule

    def _acute_rule(self, field_path: str, ev: dict, text: str) -> Optional[str]:
        """Rule name when a current-ASM mention is a one-off administration, else None."""
        role, rule = self._drug_role(field_path, ev, text)
        return rule if role == "acute" else None

    def _llm_evidence(self, item, text: str):
        """Evidence dict of an LLM item with a span found in the note (its quote, else value grounding)."""
        from services.chain_llm import ground_value, locate_quote
        ev = dict(item.ev)
        span = locate_quote(ev.get("evidence_text") or "", text)
        if span is None and getattr(self.cfg, "ground_llm_values", True):
            span = ground_value(item.field_path, ev.get("value"), text)
        if span is None:
            return None
        ev["char_start"], ev["char_end"] = span
        ev["evidence_text"] = text[span[0]:span[1]]
        return ev

    def _finish(self, claim: Claim, *, field_type: str, stats: ExtractionStats, ledger: Any) -> None:
        """Verify, tally and publish one claim."""
        self._verify(claim, field_type=field_type)
        stats.tally(claim.validator_verdict, claim.reason_codes)
        if ledger is not None:
            ledger.publish(claim)

    def _reason_llm(self, text: str, *, document_id: str, doc_date: str):
        """Reason B: obtain an LLM phenotype dict, or None (specialist-only)."""
        if self._llm_reasoner is None:
            return None
        try:
            return self._llm_reasoner(text, document_id, doc_date)
        except Exception:
            logger.exception("LLM reasoner failed; continuing specialist-only")
            return None

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
        detectors: Optional[list[str]] = None,
        initial_reasons: Optional[list[ReasonCode]] = None,
    ) -> Claim:
        """Build a Claim from an Evidence[T], attaching a retrieved candidate."""
        # Attempt candidate retrieval if we have a quote
        mention_text = (ev.get("evidence_text") or "").strip()
        concept_system = "MEDAI-ENUM"
        concept_id = str(ev.get("value") or "unknown")
        concept_label = concept_id
        concept_release = self.cfg.ontology_release
        candidate_rank = 1

        if mention_text and self._candidate_service is not None:
            cands = self._candidate_service.get_candidates(
                mention=mention_text, field_type=field_type, k=5,
            )
            # Without the LLM selection step, only an exact label/synonym hit is
            # trusted; anything fuzzier keeps the enum ID and is left to review.
            if cands and cands[0].rank_score >= self.cfg.min_candidate_score and not cands[0].is_obsolete:
                top = cands[0]
                concept_system = top.system
                concept_id = top.id
                concept_label = top.label
                concept_release = top.release or concept_release
                candidate_rank = 1

        # Map Evidence certainty / temporal_status → claim labels
        certainty = (ev.get("certainty") or "").lower()
        temporal = (ev.get("temporal_status") or "").lower()
        if (self.cfg.approx_frequency_is_asserted and field_type.endswith("seizure_frequency")
                and certainty == "probable"):
            certainty = "definite"

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
            ontology_release=concept_release,
            assertion=assertion,
            experiencer=experiencer,
            temporal_status=temporal_status,
            detectors=detectors or [SPECIALIST_DETECTOR],
            candidate_rank=candidate_rank,
            model_confidence=None,
            versions=Versions(
                model=getattr(getattr(self._llm_reasoner, "info", None), "model", "")
                if "llm" in (detectors or []) else "",
                prompt=getattr(getattr(self._llm_reasoner, "info", None), "prompt", "")
                if "llm" in (detectors or []) else "",
                rules=self.cfg.rules_version,
                retriever=self.cfg.ontology_release,
                pipeline=self.cfg.pipeline_version,
            ),
            initial_verdict=ValidatorVerdict.REVIEW,  # Verify will re-decide
            initial_reasons=initial_reasons,
        )
        claim.field_path = field_type
        claim.value = ev.get("value")
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

        # Policy: a one-off drug administration is not the regimen; a person decides
        if ReasonCode.ACUTE_ADMINISTRATION in reasons:
            claim.validator_verdict = ValidatorVerdict.REVIEW
            claim.reason_codes = reasons
            return

        # Policy: the LLM listed drugs and did not list this one
        if ReasonCode.SPECIALIST_ONLY_UNCONFIRMED in reasons:
            claim.validator_verdict = ValidatorVerdict.REVIEW
            claim.reason_codes = reasons
            return

        # Policy: specialist and LLM committed to different values for a scalar field
        if ReasonCode.SOURCE_DISAGREEMENT in reasons:
            claim.validator_verdict = ValidatorVerdict.REVIEW
            claim.reason_codes = reasons
            return

        # Policy: a fact only the LLM proposed is never auto-accepted
        if claim.detectors == ["llm"]:
            reasons.append(ReasonCode.LLM_ONLY)
            claim.validator_verdict = ValidatorVerdict.REVIEW
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
        if field_type.startswith("clinical_seizure") and claim.detectors == [SPECIALIST_DETECTOR] \
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


__all__ = ["ChainPipeline", "ChainPipelineConfig", "ExtractionStats", "SPECIALIST_DETECTOR"]
