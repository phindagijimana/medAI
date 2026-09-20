"""Applicability-driven multi-module extraction router (paper §14).

Given a document + doc_type + arm + model backend, runs each applicable
module's extraction, collects the per-module manifests, and assembles a
top-level `EpilepsyPhenotype`.

Design notes:
- One document → one phenotype record. Patient-level aggregation is a
  separate deterministic step upstream/downstream, not this router's job.
- Each module extraction runs independently: a failure in one module does
  not tank the others. The final phenotype has None for any failed module.
- Per-module manifests are all persisted; the router returns them for
  aggregate reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from pydantic import BaseModel

from schema import (
    ClinicalLocalizationModule,
    ClinicalSeizureModule,
    DocumentMetadata,
    EegModule,
    EpilepsyPhenotype,
    IntegratedPhenotypeModule,
    MedicationModule,
    MriModule,
    modules_for,
)

from .extract import DecodingConfig, ExtractionResult, ModelBackend, extract_module
from .prompt_registry import resolve
from .run_manifest import RunManifest


# Mapping: module name in the schema ↔ Pydantic module class
MODULE_CLASSES: dict[str, Type[BaseModel]] = {
    "clinical_seizure": ClinicalSeizureModule,
    "medication": MedicationModule,
    "clinical_localization": ClinicalLocalizationModule,
    "eeg": EegModule,
    "mri": MriModule,
    "integrated": IntegratedPhenotypeModule,
}


@dataclass
class PhenotypeExtractionResult:
    """Top-level extraction result across all applicable modules."""
    phenotype: EpilepsyPhenotype
    per_module: dict[str, ExtractionResult]  # module_name -> ExtractionResult
    doc: DocumentMetadata
    arm: str

    @property
    def manifests(self) -> list[RunManifest]:
        return [r.manifest for r in self.per_module.values()]

    def summary(self) -> dict:
        """One-line-per-module summary of validity and repair. For logging."""
        return {
            module: {
                "raw_valid": r.manifest.raw_valid,
                "final_valid": r.manifest.final_valid,
                "repair_method": r.manifest.repair_method,
                "duration_s": r.manifest.duration_s,
                "tokens": r.manifest.raw_response_tokens,
            }
            for module, r in self.per_module.items()
        }


def extract_phenotype(
    *,
    doc: DocumentMetadata,
    source_text: str,
    model_backend: ModelBackend,
    arm: str,
    schema_version: str,
    decoding: DecodingConfig | None = None,
    version: str = "v1",
    write_manifests: bool = True,
) -> PhenotypeExtractionResult:
    """Extract every applicable module for `doc.doc_type` and assemble the
    top-level `EpilepsyPhenotype`. Failed modules end up as None on the
    phenotype (never partially-populated) so downstream code can rely on
    module-level presence checks."""
    applicable = sorted(modules_for(doc.doc_type))
    per_module: dict[str, ExtractionResult] = {}

    phenotype_kwargs: dict = {"document": doc}

    for module_name in applicable:
        module_cls = MODULE_CLASSES.get(module_name)
        if module_cls is None:
            # Should not happen unless the applicability mask references a
            # module without a Pydantic class — guard just in case.
            continue

        try:
            prompt = resolve(module_name, arm, version)
        except KeyError:
            # No prompt registered for this (module, arm) yet — skip cleanly.
            continue

        result = extract_module(
            module_cls=module_cls,
            prompt=prompt,
            source_text=source_text,
            source_doc_meta=doc,
            model_backend=model_backend,
            decoding=decoding,
            schema_version=schema_version,
        )
        if write_manifests:
            result.manifest.write()

        per_module[module_name] = result
        if result.module is not None:
            phenotype_kwargs[module_name] = result.module

    phenotype = EpilepsyPhenotype(**phenotype_kwargs)
    return PhenotypeExtractionResult(
        phenotype=phenotype,
        per_module=per_module,
        doc=doc,
        arm=arm,
    )
