"""Per-document-type field applicability masks (§11).

A field is "applicable" for a doc type iff a reasonable annotator could
plausibly find evidence for it in that doc family. Non-applicable fields
are excluded from both extraction prompts and scoring (§11: avoid
penalizing systems for irrelevant fields).

The mask is deliberately conservative — a field marked NOT applicable
here should never be evaluated on that doc type. When in doubt, mark
applicable and let the annotator record NOT_DOCUMENTED.
"""

from __future__ import annotations

from .enums import DocumentType

# Module names must match attribute names on EpilepsyPhenotype.
Module = str

_ALL_MODULES = (
    "clinical_seizure",
    "medication",
    "clinical_localization",
    "eeg",
    "mri",
    "integrated",
)


# Which modules any given DocumentType may populate.
MODULE_APPLICABILITY: dict[DocumentType, set[Module]] = {
    DocumentType.MRI_REPORT: {"mri"},
    DocumentType.EEG_REPORT: {"eeg"},
    DocumentType.PROGRESS_NOTE: {"clinical_seizure", "medication", "clinical_localization"},
    DocumentType.INITIAL_CONSULT: {
        "clinical_seizure",
        "medication",
        "clinical_localization",
    },
    DocumentType.PRESURGICAL_EVALUATION: set(_ALL_MODULES),
    DocumentType.EMU_ADMISSION: {"clinical_seizure", "medication", "clinical_localization"},
    DocumentType.EMU_DISCHARGE: set(_ALL_MODULES),
    DocumentType.SURGERY_CONFERENCE: set(_ALL_MODULES),
    DocumentType.PROCEDURE_SEEG: {"eeg", "clinical_localization"},
    DocumentType.PROCEDURE_RESECTION: {"clinical_localization", "medication"},
    DocumentType.PROCEDURE_NEUROSTIM: {"medication", "clinical_localization"},
    DocumentType.OTHER: set(_ALL_MODULES),  # permissive; annotator uses NOT_DOCUMENTED
}


# Optional per-field carve-outs when the whole module is applicable but
# specific fields are not. Kept minimal for v0.1 to avoid over-scoping
# before pilot annotation reveals what's actually recoverable.
FIELD_CARVEOUTS: dict[DocumentType, dict[Module, set[str]]] = {
    # Progress notes may reference imaging/EEG results but we score those
    # against the source imaging/EEG doc, not against the progress note.
    DocumentType.PROGRESS_NOTE: {},
    DocumentType.INITIAL_CONSULT: {},
    # EMU admission usually predates the EEG/MRI interpretation, so no
    # imaging module even though the document is rich.
    DocumentType.EMU_ADMISSION: {},
}


def modules_for(doc_type: DocumentType) -> set[Module]:
    """Return the set of module names applicable to this document type."""
    return set(MODULE_APPLICABILITY.get(doc_type, set()))


def is_module_applicable(doc_type: DocumentType, module: Module) -> bool:
    return module in modules_for(doc_type)


def is_field_applicable(doc_type: DocumentType, module: Module, field: str) -> bool:
    if not is_module_applicable(doc_type, module):
        return False
    carveout = FIELD_CARVEOUTS.get(doc_type, {}).get(module, set())
    return field not in carveout


def enforce(phenotype, strict: bool = True) -> list[str]:
    """Check a populated EpilepsyPhenotype against the applicability mask.

    Returns a list of violation messages (populated non-applicable modules).
    If strict=True, raises ValueError on the first violation.
    """
    doc_type = phenotype.document.doc_type
    allowed = modules_for(doc_type)
    violations: list[str] = []
    for module in _ALL_MODULES:
        if getattr(phenotype, module, None) is not None and module not in allowed:
            msg = f"module {module!r} is not applicable to {doc_type.value}"
            if strict:
                raise ValueError(msg)
            violations.append(msg)
    return violations
