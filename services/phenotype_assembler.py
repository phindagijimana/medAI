"""Phase 2 orchestrator — MedCAT + medspaCy → ``EpilepsyPhenotype``.

Runs the two-tier extractor (:class:`services.medcat_extractor.MedCATExtractor`),
attaches medspaCy ConText attributes to each :class:`LinkedEntity`, dispatches
the entity list to a registry of :class:`rules.base_rule.BaseFieldRule`
instances, and assembles the final :class:`schema.ontology.EpilepsyPhenotype`.

The rule registry is intentionally empty in Phase 2 — Phase 3 populates it.
An empty registry still produces a valid ``EpilepsyPhenotype`` with all
optional module slots set to ``None`` and only the mandatory
``document`` metadata populated.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

# Ensure repo root on path when imported from outside a package.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from rules.base_rule import BaseFieldRule, make_meta
from rules.context_config import build_medspacy_pipeline, pipeline_stats
from rules.context_config_us import apply_section_context
from rules.uk_to_us_lexicon import normalize_uk_to_us
from rules.us_note_structure import Section, detect_sections
from schema.enums import DocumentType
from schema.evidence import DocumentMetadata, Evidence
from schema.ontology import (
    ClinicalLocalizationModule,
    ClinicalSeizureModule,
    EegModule,
    EpilepsyPhenotype,
    IntegratedPhenotypeModule,
    MedicationModule,
    MriModule,
)
from services.medcat_extractor import LinkedEntity, MedCATExtractor


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

RULE_REGISTRY: dict[str, BaseFieldRule] = {}


def register_rule(rule: BaseFieldRule) -> BaseFieldRule:
    """Register a rule under its ``rule.field_name``. Second registration
    for the same field replaces the first (Phase 3 tests may swap rules)."""
    if not rule.field_name:
        raise ValueError("Rule must define a non-empty field_name")
    RULE_REGISTRY[rule.field_name] = rule
    return rule


def clear_registry() -> None:
    """Wipe the registry — used by tests and by callers that want a fresh
    dispatcher (e.g. running Phase 2 baseline vs Phase 3 rules)."""
    RULE_REGISTRY.clear()


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------


class PhenotypeAssembler:
    """End-to-end pipeline: text → :class:`EpilepsyPhenotype`.

    Parameters
    ----------
    extractor
        A pre-loaded :class:`MedCATExtractor`.
    nlp
        Optional pre-built medspaCy Language. If ``None`` we build one
        via :func:`rules.context_config.build_medspacy_pipeline`.
    rules
        Iterable of :class:`BaseFieldRule` to run. Defaults to the module
        :data:`RULE_REGISTRY`.
    """

    def __init__(
        self,
        extractor: MedCATExtractor,
        *,
        nlp=None,
        rules: Optional[list[BaseFieldRule]] = None,
        load_default_rules: bool = True,
        apply_uk_to_us: bool = True,
        detect_us_sections: bool = True,
        context_engine: str = "medspacy",
    ) -> None:
        self.extractor = extractor
        self.nlp = nlp if nlp is not None else build_medspacy_pipeline()
        from services.context_engine import parse_context_engine
        self.context_engine = parse_context_engine(context_engine)
        # Phase 4: US adaptation switches.
        # ``apply_uk_to_us`` — pre-tokenisation spelling + drug-name rewrite.
        # ``detect_us_sections`` — SOAP/section detector; attaches
        #   ``section_type`` and section-scope context to each entity.
        self.apply_uk_to_us = apply_uk_to_us
        self.detect_us_sections = detect_us_sections

        # Phase 3a: populate the module registry by importing the field
        # rule modules (each module's top-level `register_rule(...)` calls
        # write into RULE_REGISTRY). Caller can suppress by passing
        # ``load_default_rules=False`` when they want a bare pipeline.
        if load_default_rules and rules is None:
            try:  # pragma: no cover - import side effects only
                import rules as _rules_pkg  # noqa: F401
                from rules import fields as _fields_pkg  # noqa: F401
            except Exception as _e:  # pragma: no cover
                print(f"[phenotype_assembler] Could not load default rules: {_e}")

        # Snapshot rules at construction time so a caller can subclass /
        # mutate the module-level registry without surprising a live
        # assembler.
        self._rules: list[BaseFieldRule] = list(
            rules if rules is not None else RULE_REGISTRY.values()
        )

    # ------------------------------------------------------------------

    def pipeline_stats(self) -> dict[str, Any]:
        """Report which medspaCy rules are loaded (defaults + our additions)."""
        return pipeline_stats(self.nlp)

    # ------------------------------------------------------------------

    def process(
        self,
        text: str,
        *,
        doc_id: str = "unknown",
        doc_type: DocumentType = DocumentType.PROGRESS_NOTE,
        doc_date: Optional[date] = None,
        patient_id: str = "unknown",
        icd10cm_codes: Optional[list[str]] = None,
        snomed_ct_codes: Optional[list[str]] = None,
    ) -> EpilepsyPhenotype:
        """Run the full pipeline on ``text`` and return a validated
        :class:`EpilepsyPhenotype`.

        Empty documents (whitespace / no text) yield a phenotype with only
        ``document`` populated and every module set to ``None``.
        """
        if doc_date is None:
            doc_date = date.today()

        document = DocumentMetadata(
            doc_id=doc_id,
            doc_type=doc_type,
            doc_date=doc_date,
            patient_id=patient_id,
            icd10cm_codes=list(icd10cm_codes or []),
            snomed_ct_codes=list(snomed_ct_codes or []),
        )

        pheno = EpilepsyPhenotype(document=document)

        # Empty / whitespace-only doc → short-circuit.
        if not text or not text.strip():
            return pheno

        # Phase 4: US adaptation — spelling + drug alias normalisation.
        # Char offsets shift only where the substitution length differs (a
        # handful of chars per replacement).  We keep the *normalised* text
        # as the canonical `text` used for entity spans below so all
        # offsets refer to the same string.
        original_text = text
        if self.apply_uk_to_us:
            text = normalize_uk_to_us(text)

        # Phase 4: SOAP / US section detection.
        sections: list[Section] = []
        if self.detect_us_sections:
            try:
                sections = detect_sections(text)
            except Exception as e:  # pragma: no cover - defensive
                print(f"[phenotype_assembler] detect_sections raised {e!r}; "
                      "continuing without section tags.")
                sections = []

        entities, doc = self.extractor.extract_with_context(
            text, self.nlp, engine=self.context_engine)
        # Attach section_type onto each LinkedEntity + section-scope context
        # overrides.  Order matters: this must run AFTER medspaCy so it can
        # promote (never demote) sentence-scope flags.
        if self.detect_us_sections:
            try:
                apply_section_context(entities, sections)
            except Exception as e:  # pragma: no cover - defensive
                print(f"[phenotype_assembler] apply_section_context raised "
                      f"{e!r}; entities keep default section_type=None.")

        meta = make_meta(doc_id=doc_id, doc_type=doc_type, doc_date=doc_date)

        # Phase 3a module bootstrap — rules write into these skeleton modules.
        # Every Evidence-valued field starts as NOT_DOCUMENTED so validated
        # `Evidence.not_documented()` passes even when a rule doesn't fire.
        self._bootstrap_modules(pheno, meta)

        # Phase 3b: two-wave rule dispatch. Wave 1 = primary rules (phase=1);
        # wave 2 = compound rules that depend on wave-1 outputs (phase=2)
        # e.g. drug_resistance_status (reads current/prior/failed asms) and
        # concordance (reads EEG/MRI/clinical localization). Wave-2 rules
        # receive the mutated ``pheno`` via a class-level attribute so they
        # can inspect already-populated fields.
        wave1 = [r for r in self._rules if getattr(r, "phase", 1) == 1]
        wave2 = [r for r in self._rules if getattr(r, "phase", 1) == 2]

        rule_outputs: dict[str, Any] = self._dispatch(wave1, entities, doc, meta)
        for field_name, value in rule_outputs.items():
            self._assign(pheno, field_name, value)

        # Expose the partial phenotype to wave-2 rules.
        for r in wave2:
            try:
                r.pheno = pheno  # attribute injection; wave-2 rules read this
            except Exception:  # pragma: no cover — read-only classes
                pass
        wave2_outputs: dict[str, Any] = self._dispatch(wave2, entities, doc, meta)
        for field_name, value in wave2_outputs.items():
            self._assign(pheno, field_name, value)

        # Store the raw entities on the phenotype for downstream consumers /
        # test harnesses. We intentionally do NOT add this to the schema —
        # it lives as a private-ish `_entities` attr via object.__setattr__
        # (Pydantic ConfigDict extra='forbid' bars model attrs).
        object.__setattr__(pheno, "_entities", entities)
        object.__setattr__(pheno, "_doc", doc)
        # Phase 4: expose the section list and (potentially normalised)
        # text so smoke tests / downstream reporters can inspect what the
        # pipeline actually processed.
        object.__setattr__(pheno, "_sections", sections)
        object.__setattr__(pheno, "_text", text)
        object.__setattr__(pheno, "_text_original", original_text)

        # Phase 5: apply compound / relational rules AFTER wave-2 field
        # rules complete. Compound rules read from + optionally overwrite
        # the partial phenotype (e.g. drug_resistance_status, concordance)
        # and store non-slotted derivations on ``pheno._derived``.
        # Imported inside the method to keep import cycles at bay (rules.compound
        # imports from schema, which is fine, but historically we've avoided
        # a top-level dep in the assembler on the rules package itself).
        try:  # pragma: no cover - defensive
            from rules.compound import apply_compound_rules
            compound_outcomes = apply_compound_rules(pheno, meta)
            object.__setattr__(pheno, "_compound_outcomes", compound_outcomes)
        except Exception as e:  # pragma: no cover - defensive
            print(f"[phenotype_assembler] compound-rule dispatch raised {e!r}; "
                  "leaving wave-2 outputs in place.")
        return pheno

    # ------------------------------------------------------------------

    def _dispatch(
        self,
        rules: list[BaseFieldRule],
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        for rule in rules:
            try:
                out = rule.apply(entities, doc, meta)
            except Exception as e:  # pragma: no cover - defensive
                # A single mis-behaving rule must not crash the pipeline.
                # In Phase 2 there are no rules; Phase 3 tests will exercise
                # this path.
                print(
                    f"[phenotype_assembler] Rule {rule.field_name!r} raised "
                    f"{type(e).__name__}: {e}; skipping."
                )
                continue
            if out is None:
                continue
            outputs[rule.field_name] = out
        return outputs

    # ------------------------------------------------------------------

    @staticmethod
    def _assign(pheno: EpilepsyPhenotype, field_name: str, value: Any) -> None:
        """Set a dotted path on ``pheno`` (e.g.
        ``clinical_seizure.epilepsy_type``). Called by the dispatcher for
        every rule that returned a non-``None`` output.
        """
        parts = field_name.split(".")
        target: Any = pheno
        for p in parts[:-1]:
            nxt = getattr(target, p, None)
            if nxt is None:
                # Module skeleton was not bootstrapped for this path; skip
                # rather than crash.
                return
            target = nxt
        setattr(target, parts[-1], value)

    # ------------------------------------------------------------------

    @staticmethod
    def _bootstrap_modules(pheno: EpilepsyPhenotype, meta: dict[str, Any]) -> None:
        """Instantiate ``clinical_seizure``, ``medication``, ``mri``, ``eeg``
        module skeletons on ``pheno``. Every Evidence-valued field is
        pre-filled with ``NOT_DOCUMENTED`` so rules can either overwrite or
        leave-as-is.

        The four modules populated here are the ones Phase 3a's P1 rules
        target. ``clinical_localization`` / ``integrated`` (Phase 3b) stay
        ``None`` until a P2 rule needs them.
        """
        nd = lambda: Evidence.not_documented(
            source_doc_id=meta["doc_id"],
            source_doc_type=meta["doc_type"],
            source_date=meta["doc_date"],
        )

        pheno.clinical_seizure = ClinicalSeizureModule(
            epilepsy_type=nd(),
            predominant_seizure_type=nd(),
            other_seizure_types=[],
            awareness=nd(),
            semiology_text=nd(),
            age_at_onset_years=nd(),
            seizure_frequency=nd(),
            other_seizure_frequencies=[],
            status_epilepticus_history=nd(),
            etiology_category=nd(),
            etiology_details_text=nd(),
            etiology_specifics=nd(),
            focal_motor_onset=nd(),
            focal_nonmotor_onset=nd(),
        )
        pheno.medication = MedicationModule(
            current_asms=[],
            prior_asms=[],
            failed_asms=[],
            adverse_effects_text=nd(),
            drug_resistance_status=nd(),
            surgery_history=[],
            non_drug_therapies=[],
        )
        pheno.mri = MriModule(
            overall_normal=nd(),
            findings=[],
            lesion_lobe=nd(),
            lesion_laterality=nd(),
            hippocampal_sclerosis=nd(),
            focal_cortical_dysplasia=nd(),
            mri_negative_for_epilepsy=nd(),
            field_strength_tesla=nd(),
        )
        pheno.eeg = EegModule(
            study_type=nd(),
            background=nd(),
            ied_present=nd(),
            ied_findings=[],
            seizures_captured=nd(),
            seizures_captured_count=nd(),
            ictal_onset_lobe=nd(),
            ictal_onset_laterality=nd(),
        )
        # Phase 3b — bootstrap clinical_localization + integrated modules
        # so rules targeting primary_claim / concordance can slot into a
        # ready skeleton and Pydantic validation still passes when nothing
        # fires.
        pheno.clinical_localization = ClinicalLocalizationModule(
            primary_claim=nd(),
            alternative_claims=[],
        )
        pheno.integrated = IntegratedPhenotypeModule(
            clinical_localization=nd(),
            eeg_localization=nd(),
            mri_localization=nd(),
            concordance=nd(),
            concordance_notes_text=nd(),
        )


__all__ = [
    "PhenotypeAssembler",
    "RULE_REGISTRY",
    "register_rule",
    "clear_registry",
]
