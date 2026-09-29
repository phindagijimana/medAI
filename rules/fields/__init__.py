"""Per-schema-field extraction rules (Phase 3a + Phase 3b).

Each submodule ports rule *logic* from ExECT-V2's JAPE + Groovy pipeline
into Python for one or more schema fields. Import-side effect: every
submodule registers its concrete :class:`BaseFieldRule` instance(s) with
:data:`services.phenotype_assembler.RULE_REGISTRY`.

Phase 3a modules (P1 fields, 8 fields / 19 rules)
-------------------------------------------------
- ``seizure_type``      — ``clinical_seizure.predominant_seizure_type``
                          + ``other_seizure_types``
- ``seizure_frequency`` — ``clinical_seizure.seizure_frequency``
                          + ``other_seizure_frequencies``
- ``onset_age``         — ``clinical_seizure.age_at_onset_years``
- ``epilepsy_type``     — ``clinical_seizure.epilepsy_type``
- ``etiology``          — ``clinical_seizure.etiology_category``
                          + ``etiology_details_text``
- ``medication``        — ``medication.current_asms`` / ``prior_asms``
                          / ``failed_asms``
- ``mri``               — ``mri.findings`` + convenience booleans + lesion
                          localization + field-strength Tesla
- ``eeg``               — ``eeg.background`` + ``ied_findings``
                          + ``ied_present``

Phase 3b modules (P2 fields, 16 fields / ~25 rules — extends 3a)
----------------------------------------------------------------
- ``awareness``              — ``clinical_seizure.awareness``
- ``focal_onset``            — ``clinical_seizure.focal_motor_onset``
                               + ``focal_nonmotor_onset``
                               + ``semiology_text``
- ``status_epilepticus``     — ``clinical_seizure.status_epilepticus_history``
- ``clinical_localization``  — ``clinical_localization.primary_claim``
                               + ``alternative_claims``
                               + ``integrated.{clinical,eeg,mri}_localization``
                               + ``integrated.concordance`` [wave-2]
- ``medication_extra``       — ``medication.adverse_effects_text``
                               + ``non_drug_therapies``
                               + ``drug_resistance_status`` [wave-2]
- ``mri_extra``              — ``mri.lesion_lobe``
                               + ``mri.lesion_laterality``
                               + ``mri.field_strength_tesla``
- ``eeg_extra``              — ``eeg.study_type`` + ``seizures_captured``
                               + ``seizures_captured_count``
                               + ``ictal_onset_lobe`` + ``ictal_onset_laterality``
- ``surgery``                — ``medication.surgery_history``
- ``autoimmune``             — ``clinical_seizure.etiology_specifics``

Provenance policy
-----------------
Every submodule cites the exact ExECT-V2 files it studied (JAPE + Groovy)
in its module docstring. No verbatim JAPE syntax is retained; semantics
are reimplemented in Python using :class:`spacy.tokens.Doc` +
:class:`~services.medcat_extractor.LinkedEntity` + medspaCy ConText flags.
Phase 3b modules that have no ExECT source (surgery, autoimmune)
explicitly cite their non-ExECT provenance (Engel 1993, Wieser 2001,
Graus 2016, Kwan 2010, etc.).

Wave-2 rules
------------
Two rules run in a second dispatch wave after wave-1 completes because
they read the partial phenotype produced by wave-1:
- ``clinical_localization.ConcordanceStatusRule`` reads the three
  modality-specific localizations.
- ``medication_extra.DrugResistanceStatusRule`` reads the failed-ASM count.
The assembler exposes ``self.pheno`` on wave-2 rule instances before
calling ``.apply()``.
"""
from __future__ import annotations

# Phase 3a — P1 rules (import order matters for dispatch sequence).
from . import seizure_type  # noqa: F401  — registers 2 rules
from . import seizure_frequency  # noqa: F401  — registers 2 rules
from . import onset_age  # noqa: F401  — registers 1 rule
from . import epilepsy_type  # noqa: F401  — registers 1 rule
from . import etiology  # noqa: F401  — registers 2 rules
from . import medication  # noqa: F401  — registers 3 rules
from . import mri  # noqa: F401  — registers 5 rules
from . import eeg  # noqa: F401  — registers 3 rules

# Phase 3b — P2 rules.
from . import awareness  # noqa: F401  — registers 1 rule
from . import focal_onset  # noqa: F401  — registers 3 rules
from . import status_epilepticus  # noqa: F401  — registers 1 rule
from . import clinical_localization  # noqa: F401  — registers 6 rules (5+1)
from . import medication_extra  # noqa: F401  — registers 3 rules (2+1)
from . import mri_extra  # noqa: F401  — registers 3 rules
from . import eeg_extra  # noqa: F401  — registers 5 rules
from . import surgery  # noqa: F401  — registers 1 rule
from . import autoimmune  # noqa: F401  — registers 1 rule
