"""MedAI-EPI phenotype ontology v0.2.1 (§5, Table 3 + stress-test additions + coding cross-refs).

Modules:
  1. ClinicalSeizureModule       — semiology, seizure/epilepsy type, frequency, onset, etiology, focal subtypes
  2. MedicationModule            — current/prior ASMs, failures, drug-resistance, non-drug therapies
  3. ClinicalLocalizationModule  — clinician localization hypothesis
  4. EegModule                   — EEG report findings
  5. MriModule                   — MRI report findings, field strength
  6. IntegratedPhenotypeModule   — cross-modality synthesis (EMU/presurgical only)
  7. Provenance (via DocumentMetadata + per-field Evidence[T].source_*)

v0.2 changelog vs v0.1 (see docs/SCHEMA_V0_2.md):
  * SurgeryType.UNKNOWN
  * MriFinding.MOGHE, FCD_PALMINI_I/IIA/IIB
  * MriModule.field_strength_tesla (Evidence[float])
  * MriModule.model_validator enforces convenience-boolean ↔ findings consistency
  * IedFinding.dominant_frequency_hz
  * SeizureFrequency.duration_text, applies_to_type
  * ClinicalSeizureModule.other_seizure_frequencies
  * SurgeryHistoryItem.engel_class, ilae_outcome, device_model_text,
    stimulation_parameters_text, pathology_notes_text
  * MedicationModule.non_drug_therapies + NonDrugTherapy value object
  * ClinicalSeizureModule.etiology_category, etiology_details_text (provisional *)
  * ClinicalSeizureModule.focal_motor_onset, focal_nonmotor_onset (provisional *)

v0.2.1 changelog vs v0.2:
  * DocumentMetadata.icd10cm_codes / snomed_ct_codes (from EHR encounter header)
  * Medication.rxnorm_cui (optional cross-reference)
  * New CausativeAntibody enum + EtiologySpecifics value object
  * ClinicalSeizureModule.etiology_specifics (Evidence[EtiologySpecifics])
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import (
    Awareness,
    CausativeAntibody,
    ConcordanceStatus,
    DrugResistanceStatus,
    EegBackground,
    EegStudyType,
    EngelClass,
    EpilepsyType,
    EtiologyCategory,
    FocalMotorOnset,
    FocalNonmotorOnset,
    IedType,
    IlaeOutcome,
    Laterality,
    LobarLocalization,
    LocalizationSource,
    MedicationStatus,
    MriFinding,
    NonDrugTherapyType,
    SeizureType,
    SurgeryType,
)
from .evidence import DocumentMetadata, Evidence

SCHEMA_VERSION = "v0.2.1"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


class Medication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generic_name: str
    status: MedicationStatus
    dose_text: str | None = None
    reason_discontinued: str | None = None
    rxnorm_cui: str | None = None            # v0.2.1: optional normalization to RxNorm CUI


class EtiologySpecifics(BaseModel):
    """v0.2.1: structured slots for the etiology categories that commonly need them.

    All fields optional — annotators fill only those relevant to
    `ClinicalSeizureModule.etiology_category`. `causative_gene` uses HGNC gene
    symbols (e.g. "SCN1A", "DEPDC5"); `causative_variant` uses HGVS notation
    when available; the free-text `*_text` fields are for anything the enum
    doesn't cover (rare antibodies, uncommon pathogens, metabolic conditions).
    """
    model_config = ConfigDict(extra="forbid")

    causative_gene: str | None = None                # HGNC symbol
    causative_variant: str | None = None             # HGVS
    causative_antibody: CausativeAntibody | None = None
    associated_tumor_text: str | None = None         # paraneoplastic context, e.g. "SCLC"
    causative_pathogen_text: str | None = None       # e.g. "neurocysticercosis", "HSV-1"
    causative_metabolic_text: str | None = None      # e.g. "pyridoxine-dependent epilepsy"


class NonDrugTherapy(BaseModel):
    """v0.2: dietary, immunotherapy, and other non-pharmaceutical treatments."""
    model_config = ConfigDict(extra="forbid")

    therapy_type: NonDrugTherapyType
    status: MedicationStatus                 # reuse the status enum (current/prior/failed/…)
    response_text: str | None = None


class SeizureFrequency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str
    period: Literal["day", "week", "month", "year", "unspecified"] = "unspecified"
    count_min: float | None = None
    count_max: float | None = None
    seizure_free: bool = False
    duration_text: str | None = None         # v0.2: raw per-event duration quote
    applies_to_type: SeizureType | None = None  # v0.2: tie a frequency to a specific seizure type


class LobarClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lobe: LobarLocalization
    laterality: Laterality
    source: LocalizationSource


class IedFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ied_type: IedType
    localization: LobarLocalization | None = None
    laterality: Laterality | None = None
    dominant_frequency_hz: float | None = Field(default=None, gt=0, lt=100)  # v0.2


class SurgeryHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surgery_type: SurgeryType
    target: str | None = None
    laterality: Laterality | None = None
    year: int | None = None
    outcome_text: str | None = None
    # v0.2 additions
    engel_class: EngelClass | None = None
    ilae_outcome: IlaeOutcome | None = None
    device_model_text: str | None = None            # for neurostim: e.g. "AspireSR 106"
    stimulation_parameters_text: str | None = None  # raw quote, structured parsing deferred
    pathology_notes_text: str | None = None         # resected specimen histopath quote


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------


class ClinicalSeizureModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    epilepsy_type: Evidence[EpilepsyType]
    predominant_seizure_type: Evidence[SeizureType]
    other_seizure_types: list[Evidence[SeizureType]] = Field(default_factory=list)
    awareness: Evidence[Awareness]
    semiology_text: Evidence[str]
    age_at_onset_years: Evidence[float]
    seizure_frequency: Evidence[SeizureFrequency]
    other_seizure_frequencies: list[Evidence[SeizureFrequency]] = Field(default_factory=list)  # v0.2
    status_epilepticus_history: Evidence[bool]
    # v0.2 — etiology (provisional; needs reviewer confirmation)
    etiology_category: Evidence[EtiologyCategory]
    etiology_details_text: Evidence[str]
    etiology_specifics: Evidence[EtiologySpecifics]  # v0.2.1
    # v0.2 — focal onset subtypes (provisional; applicable when predominant type is focal)
    focal_motor_onset: Evidence[FocalMotorOnset]
    focal_nonmotor_onset: Evidence[FocalNonmotorOnset]


class MedicationModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_asms: list[Evidence[Medication]] = Field(default_factory=list)
    prior_asms: list[Evidence[Medication]] = Field(default_factory=list)
    failed_asms: list[Evidence[Medication]] = Field(default_factory=list)
    adverse_effects_text: Evidence[str]
    drug_resistance_status: Evidence[DrugResistanceStatus]
    surgery_history: list[Evidence[SurgeryHistoryItem]] = Field(default_factory=list)
    non_drug_therapies: list[Evidence[NonDrugTherapy]] = Field(default_factory=list)  # v0.2


class ClinicalLocalizationModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_claim: Evidence[LobarClaim]
    alternative_claims: list[Evidence[LobarClaim]] = Field(default_factory=list)


class EegModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_type: Evidence[EegStudyType]
    background: Evidence[EegBackground]
    ied_present: Evidence[bool]
    ied_findings: list[Evidence[IedFinding]] = Field(default_factory=list)
    seizures_captured: Evidence[bool]
    seizures_captured_count: Evidence[int]
    ictal_onset_lobe: Evidence[LobarLocalization]
    ictal_onset_laterality: Evidence[Laterality]


class MriModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_normal: Evidence[bool]
    findings: list[Evidence[MriFinding]] = Field(default_factory=list)
    lesion_lobe: Evidence[LobarLocalization]
    lesion_laterality: Evidence[Laterality]
    hippocampal_sclerosis: Evidence[bool]
    focal_cortical_dysplasia: Evidence[bool]
    mri_negative_for_epilepsy: Evidence[bool]
    field_strength_tesla: Evidence[float]           # v0.2: 1.5 / 3.0 / 7.0 / other

    @model_validator(mode="after")
    def _finding_consistency(self) -> "MriModule":
        """v0.2 consistency guard: convenience booleans must agree with findings list.

        If `hippocampal_sclerosis.value=True`, the findings list must contain at least one
        HS entry (or an FCD-consistent equivalent). Same for `focal_cortical_dysplasia`.
        Only enforced when both fields have concrete boolean values (not None/UNKNOWN).
        """
        hs_finding = any(
            f.value in (MriFinding.HIPPOCAMPAL_SCLEROSIS,)
            for f in self.findings
        )
        fcd_finding = any(
            f.value in (
                MriFinding.FOCAL_CORTICAL_DYSPLASIA,
                MriFinding.FCD_PALMINI_I,
                MriFinding.FCD_PALMINI_IIA,
                MriFinding.FCD_PALMINI_IIB,
                MriFinding.MOGHE,
            )
            for f in self.findings
        )

        if self.hippocampal_sclerosis.value is True and not hs_finding:
            raise ValueError(
                "hippocampal_sclerosis=True but no HIPPOCAMPAL_SCLEROSIS entry in findings"
            )
        if self.focal_cortical_dysplasia.value is True and not fcd_finding:
            raise ValueError(
                "focal_cortical_dysplasia=True but no FCD/MOGHE entry in findings"
            )
        return self


class IntegratedPhenotypeModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinical_localization: Evidence[LobarClaim]
    eeg_localization: Evidence[LobarClaim]
    mri_localization: Evidence[LobarClaim]
    concordance: Evidence[ConcordanceStatus]
    concordance_notes_text: Evidence[str]


# ---------------------------------------------------------------------------
# Top-level phenotype record
# ---------------------------------------------------------------------------


class EpilepsyPhenotype(BaseModel):
    """One document → one phenotype record. Patient-level aggregation is separate (§14)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v0.2.1"] = "v0.2.1"
    document: DocumentMetadata

    clinical_seizure: ClinicalSeizureModule | None = None
    medication: MedicationModule | None = None
    clinical_localization: ClinicalLocalizationModule | None = None
    eeg: EegModule | None = None
    mri: MriModule | None = None
    integrated: IntegratedPhenotypeModule | None = None
