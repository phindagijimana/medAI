# Supplementary Rule Provenance Table — arm B1' MedCAT+Rules

*Companion to v0.5 §Attribution and licensing.*

Every rule in `rules/fields/*.py` and `rules/compound.py` is annotated
with a module docstring that enumerates the ExECT-V2 files it was
studied against (for rules with ExECT counterparts) and the primary
clinical literature it was derived from (for rules with no ExECT
counterpart). This table extracts and consolidates those citations.

**Rule counts:**

- **43 field-rule classes** across 17 files in `rules/fields/`
- **10 compound functions** in `rules/compound.py`
- **Total: 53 rules**

**ExECT-V2 files studied (unique):** ~45 JAPE files + ~15 Groovy
serializers + ~4 gazetteer / lookup files + `Other/ILAE proposed map
to UMLS and SNOMEDCT.xlsx`.

**Reimplementation stance:** every rule reimplements ExECT-V2 logic
independently in Python on the MedCAT + medspaCy stack. No verbatim
JAPE grammar or Groovy code is retained in our source tree. Studied
files are cited as reference material only.

---

## Section 1 — Field rules (`rules/fields/*.py`)

| # | Our file | Our class | ExECT-V2 files studied | Role studied | Non-ExECT primary sources |
|---:|---|---|---|---|---|
| 1 | `autoimmune.py` | `EtiologySpecificsRule` | — (no ExECT source; ExECT has generic "autoimmune" mentions but no CausativeAntibody enumeration) | — | Graus F et al. 2016 (Lancet Neurol 15:391); Steriade C et al. 2020 (Epilepsia 61:1341); Dubey D et al. 2020 (Ann Neurol 87:313) |
| 2 | `awareness.py` | `AwarenessRule` | `jape/seizurechange.jape`; `Groovy/Diagnosis.groovy`; `jape/PartialSeizure.jape`; `resources/gazetteers/seizure_targets.lst` | ILAE 2017 renaming of "simple/complex partial" → focal-with/without impaired awareness; awareness attribute serializer; simple/complex-partial fold-in; awareness surface forms | Fisher RS et al. 2017 (Epilepsia 58:522) |
| 3 | `clinical_localization.py` | `PrimaryLocalizationClaimRule` | `jape/Lateralisation.jape`; `jape/LocationAndFinding.jape`; `jape/InvestigationsMRI.jape`; `jape/InvestigationsEEG.jape`; `Groovy/Investigations.groovy`; `Groovy/Diagnosis.groovy` | Left/right/bilateral tokens; Lobe + Laterality + Finding combo; MRI-lesion + localization; EEG-focus + localization; investigation-scoped serializer; clinical-hypothesis serializer | Rosenow F & Lüders H 2001 (Brain 124:1683); ILAE presurgical evaluation standards |
| 4 | `clinical_localization.py` | `AlternativeLocalizationClaimsRule` | (same files as row 3) | (same roles) | (same non-ExECT sources) |
| 5 | `clinical_localization.py` | `IntegratedClinicalLocalizationRule` | (same files as row 3) | (same roles) | (same non-ExECT sources) |
| 6 | `clinical_localization.py` | `IntegratedEegLocalizationRule` | (same files as row 3) | (same roles) | (same non-ExECT sources) |
| 7 | `clinical_localization.py` | `IntegratedMriLocalizationRule` | (same files as row 3) | (same roles) | (same non-ExECT sources) |
| 8 | `clinical_localization.py` | `ConcordanceStatusRule` (wave-2) | (same files as row 3) | Multi-source concordance; superseded at compound stage by `derive_localization_concordance` (row 51) | (same non-ExECT sources) |
| 9 | `eeg.py` | `EegBackgroundRule` | `jape/investigations.jape`; `jape/InvestigationsEEG.jape`; `jape/NegatedFindingEEG.jape`; `jape/InvestigationBlock.jape`; `jape/InvestigationWithin.jape`; `jape/InvestigationsLookup.jape`; `jape/LocationAndFinding.jape`; `jape/Lateralisation.jape`; `resources/gazetteers/EEG_results.lst`; `Groovy/Investigations.groovy`; `Groovy/MarkupInvestigations.groovy` | Top-level investigations composition; EEG-specific patterns; "no epileptiform activity" negation; sentence-block scope; nested-clause finding; gazetteer lookup; laterality; background+IED vocabulary; serializers | Hirsch LJ et al. 2013 (J Clin Neurophysiol 30:1; ACNS EEG terminology) |
| 10 | `eeg.py` | `IedPresentRule` | (same files as row 9) | (same roles) | (same non-ExECT sources) |
| 11 | `eeg.py` | `IedFindingsRule` | (same files as row 9) | (same roles) | (same non-ExECT sources) |
| 12 | `eeg_extra.py` | `EegStudyTypeRule` | `jape/InvestigationsEEG.jape`; `jape/LocationAndFinding.jape`; `jape/Lateralisation.jape`; `Groovy/Investigations.groovy` | EEG-specific patterns; lobe + laterality composition; laterality tokens; output serializer | Hirsch LJ et al. 2013 (ACNS terminology) |
| 13 | `eeg_extra.py` | `EegSeizuresCapturedRule` | (same files as row 12) | (same roles) | (same non-ExECT sources) |
| 14 | `eeg_extra.py` | `EegSeizuresCapturedCountRule` | (same files as row 12) | (same roles) | (same non-ExECT sources) |
| 15 | `eeg_extra.py` | `EegIctalOnsetLobeRule` | (same files as row 12) | (same roles) | (same non-ExECT sources) |
| 16 | `eeg_extra.py` | `EegIctalOnsetLateralityRule` | (same files as row 12) | (same roles) | (same non-ExECT sources) |
| 17 | `epilepsy_type.py` | `EpilepsyTypeRule` | `Groovy/Diagnosis.groovy`; `Groovy/MarkupDiagnosis.groovy`; `jape/EpilepsyDiagnosis.jape`; `jape/EpilepsyMentions.jape`; `jape/DiagfromSeizure.jape`; `jape/DiagnosisB.jape`; `jape/DiagnosisB2.jape`; `jape/EpiCause.jape`; `Other/ILAE proposed map to UMLS and SNOMEDCT.xlsx` | Top-level diagnosis serializer; clause-level span builder; diagnosis-noun composition; surface-form gazetteer; inference of epilepsy diagnosis from seizure type; secondary diagnosis phase; etiology link (exclusion only); CUI → ILAE 2017 label mapping | Fisher RS et al. 2017 (ILAE 2017 operational classification) |
| 18 | `etiology.py` | `EtiologyCategoryRule` | `Groovy/EpilepsyCause.groovy`; `Groovy/MarkupEpilepsyCause.groovy`; `jape/EpilepsyCause.jape`; `jape/EpiCause.jape`–`EpiCause4.jape` (4 files); `jape/DiseaseCause.jape`; `jape/Symptomatic.jape`; `jape/Symptomatic2.jape`; `jape/FebrileSeizures.jape`; `jape/FebrileSeizuresB.jape`; `config/epilepsy.txt` (custom UMLS lexicon); `Other/ILAE proposed map to UMLS and SNOMEDCT.xlsx` | Top-level cause serializer; clause-scoped cause span; canonical cause patterns; cause variants; disease→cause link; symptomatic classification; infectious/febrile disambiguation; cause-CUI list; category mapping | Scheffer IE et al. 2017 (ILAE 2017 classification of the epilepsies) |
| 19 | `etiology.py` | `EtiologyDetailsRule` | (same files as row 18) | (same roles) | (same non-ExECT sources) |
| 20 | `focal_onset.py` | `FocalMotorOnsetRule` | `Groovy/Diagnosis.groovy`; `jape/seizurechange.jape`; `jape/PartialSeizure.jape`; `jape/SeizureMentions.jape`; `resources/gazetteers/seizure_targets.lst`; `Groovy/MarkupSeizureFrequency.groovy` | Semiology block serializer; semiology + seizure-type composition; simple/complex-partial semiology attribute; surface-form collection; semiology vocabulary; clause-scoped tagging | Fisher RS et al. 2017 (Epilepsia 58:522, 58:531 seizure classification hierarchy) |
| 21 | `focal_onset.py` | `FocalNonmotorOnsetRule` | (same files as row 20) | (same roles) | (same non-ExECT sources) |
| 22 | `focal_onset.py` | `SemiologyTextRule` | (same files as row 20) | (same roles) | (same non-ExECT sources) |
| 23 | `medication.py` | `CurrentAsmsRule` | `jape/prescription.jape`; `jape/prescription2.jape`; `jape/prescriptionSentence.jape`; `jape/PrescriptionEpilepsy.jape`; `jape/prescriptionFilter*.jape` (5 files); `jape/prescription-implicit.jape`; `jape/prescription-coref.jape`; `jape/prescription-indicator.jape`; `jape/PrescriptionML.jape`; `jape/PrescriptionMLCreated.jape`; `jape/KeepPrescription.jape`; `jape/KeepPrescriptionInText.jape`; `jape/dose-change.jape`; `jape/doses.jape`; `jape/measurement.jape`; `jape/routes.jape`; `jape/DrugPointInTime.jape`; `jape/LazyPrescription.jape`; `jape/noMeds.jape`; `Groovy/Prescription.groovy`; `Groovy/PrescriptionJson.groovy` | Canonical DRUG DOSE FREQ; sentence-scope guard; ASM-only filter; pseudo-negation exclusions (5 files); implicit "still on X" / "continue X"; pronoun-anaphoric "he takes it"; dose-change indicators; ML-derived spans (skipped in our port); coref keep; dose modification; numeric dose parse; route (PO/IV/IM); past/current classifier; relaxed fallback; "on no medications"; serializers | RxNorm (free NLM); BNF (UK drug names) |
| 24 | `medication.py` | `PriorAsmsRule` | (same files as row 23) | (same roles) | (same non-ExECT sources) |
| 25 | `medication.py` | `FailedAsmsRule` | (same files as row 23) | (same roles) | (same non-ExECT sources) |
| 26 | `medication_extra.py` | `AdverseEffectsTextRule` | `jape/DrugPointInTime.jape`; `jape/prescriptionFilter*.jape`; `Groovy/Prescription.groovy` | Current-vs-past classifier; adverse-effect exclusion filters; serializer | — |
| 27 | `medication_extra.py` | `NonDrugTherapiesRule` | (same files as row 26) | (same roles) | Kossoff EH et al. 2018 (Epilepsia Open 3:175; ketogenic diet); Fisher RS et al. 2010 (Neurology 75:e21; VNS) |
| 28 | `medication_extra.py` | `DrugResistanceStatusRule` (wave-2; superseded at compound stage) | (same files as row 26) | (same roles) | Kwan P et al. 2010 (Epilepsia 51:1069; ILAE drug-resistance definition) |
| 29 | `mri.py` | `MriFindingsRule` | `jape/investigations.jape`; `jape/InvestigationsMRI.jape`; `jape/InvestigationsCT.jape`; `jape/NegatedFindingMRI.jape`; `jape/InvestigationBlock.jape`; `jape/InvestigationWithin.jape`; `jape/InvestigationsLookup.jape`; `jape/LocationAndFinding.jape`; `jape/Lateralisation.jape`; `jape/GenericInvestigations.jape`; `jape/InvestigationsMP.jape`; `jape/InvestConj.jape`; `resources/gazetteers/ct_mri_results.lst`; `Groovy/Investigations.groovy`; `Groovy/MarkupInvestigations.groovy` | Top-level composition; MRI-specific patterns; CT-neg impact on MRI negativity; "no lesion" / "normal MRI"; sentence-block scoping; nested-clause finding; gazetteer lookup; finding + laterality; laterality tokens; fallback for uncommon phrasings; MP-tagger combo; conjunction ("and", "with") multi-finding; finding vocabulary; serializers | — |
| 30 | `mri.py` | `MriHippocampalSclerosisRule` | (same files as row 29) | (same roles) | — |
| 31 | `mri.py` | `MriFcdRule` | (same files as row 29) | (same roles) | Palmini A et al. 2004 (Neurology 62 Suppl 3:S2; FCD classification); Blümcke I et al. 2011 (Epilepsia 52:158; ILAE FCD consensus) |
| 32 | `mri.py` | `MriNegativeForEpilepsyRule` | (same files as row 29) | (same roles) | — |
| 33 | `mri.py` | `MriOverallNormalRule` | (same files as row 29) | (same roles) | — |
| 34 | `mri_extra.py` | `MriLesionLobeRule` | `jape/InvestigationsMRI.jape`; `jape/LocationAndFinding.jape`; `jape/Lateralisation.jape`; `Groovy/Investigations.groovy` | MRI finding + localization; lobe+laterality composition; laterality tokens; serializer | Rüber T et al. 2018 (Epilepsy Res 142:167; 7T MRI in epilepsy) |
| 35 | `mri_extra.py` | `MriLesionLateralityRule` | (same files as row 34) | (same roles) | (same non-ExECT sources) |
| 36 | `mri_extra.py` | `MriFieldStrengthRule` | (same files as row 34) | (same roles) | ACR MRI practice guidelines |
| 37 | `onset_age.py` | `OnsetAgeRule` | `jape/OnsetAge.jape`; `jape/OnsetAgeA.jape`; `jape/OnsetAgeB.jape`; `jape/OnsetAgeC.jape`; `jape/OnsetAgeRange.jape`; `jape/onset.jape`; `jape/times.jape`; `jape/Age.jape`; `jape/age3.jape`; `jape/AgeDiagnosed.jape`; `jape/TimeSinceOnset.jape`; `jape/TimeSinceOnsetB.jape`; `Groovy/Onset.groovy`; `Groovy/WhenDiagnosed.groovy` | Canonical "Person + Disease + onset + Age"; word-order variants; probability+onset; small residuals; age-range ("in his teens", "aged 6-8"); Onset trigger annotations; TimePeriod gazetteer; Age token composition; age-at-diagnosis fallback; "seizures since age X"; "X years since first seizure"; serializers | — |
| 38 | `seizure_frequency.py` | `SeizureFrequencyRule` | `jape/seizure-frequency.jape`; `jape/seizure-frequency1.jape`; `jape/seizure-frequency2.jape`; `jape/seizure-frequency3.jape`; `jape/frequency.jape`; `jape/mainSeizFreq.jape`; `jape/SFBlockClean.jape`; `jape/SeizFreqSentence.jape`; `jape/SeizFreqFilter*.jape`; `jape/SeizureFree.jape`; `jape/SeizFreeSentence.jape`; `jape/SeizFreeFilter*.jape`; `jape/SeizureFrequencyExtendSinceDuring.jape`; `jape/TwoSeizureFreqOneTimePeriod.jape`; `jape/times.jape`; `jape/numberRange.jape`; `jape/AToNumberRange.jape`; `Groovy/SeizureFrequency.groovy`; `Groovy/SeizureFrequencyFirstLetter.groovy` | Canonical NUMBER+per+UNIT; range+qualifier variants; since/during time-window; final filters; Frequency annotation constructors; top-level composition; cleanup phase; sentence-scoping; SeizureFree boolean; since-clause extension; range disambiguation; TimePeriods gazetteer; number-range parse; serializers; first-letter dedup | — |
| 39 | `seizure_frequency.py` | `OtherSeizureFrequenciesRule` | (same files as row 38) | (same roles) | — |
| 40 | `seizure_type.py` | `PredominantSeizureTypeRule` | `jape/seizurechange.jape`; `jape/PartialSeizure.jape`; `jape/SingleSeizure.jape`; `jape/SeizureMentions.jape`; `jape/PluralSeizuresJAVA.jape`; `jape/addSeziureType.jape`; `jape/MultipleSeizures.jape`; `jape/implicitSeizure.jape`; `jape/SeizureFree.jape` (as EXCLUDE); `Groovy/Diagnosis.groovy`; `Groovy/MarkupSeizureFrequency.groovy`; `Other/ILAE proposed map to UMLS and SNOMEDCT.xlsx` | Seizure-vs-frequency-change disambiguation; simple/complex-partial → ILAE 2017 mapping; single-seizure marker; surface-form collection; plural-form normalization; type+qualifier merge; multiple-types coordinated in one clause; "usual/typical" pronoun resolution; "no seizures" exclusion; serializers; CUI↔ILAE 2017 label mapping | Fisher RS et al. 2017 (Epilepsia 58:522) |
| 41 | `seizure_type.py` | `OtherSeizureTypesRule` | (same files as row 40) | (same roles) | (same non-ExECT sources) |
| 42 | `status_epilepticus.py` | `StatusEpilepticusHistoryRule` | `jape/seizurechange.jape`; `jape/FebrileSeizures.jape`; `jape/SeizureMentions.jape`; `Groovy/Diagnosis.groovy` | Status epilepticus as distinct seizure event category; status vs febrile-status disambiguation; SE surface-form collection; SE emitted alongside seizure type | Trinka E et al. 2015 (Epilepsia 56:1515; ILAE SE definition); Brophy GM et al. 2012 (Neurocritical Care Society SE guidelines) |
| 43 | `surgery.py` | `SurgeryHistoryRule` | — (no ExECT source; ExECT-V2 does not have a surgery-history JAPE pipeline) | — | Engel J Jr et al. 1993 (Surgical Treatment of the Epilepsies 2nd ed., Raven Press); Wieser HG et al. 2001 (Epilepsia 42:282; ILAE outcome scale); ILAE 2019 surgical epilepsy classification (Lüders et al.); Fisher RS et al. 2010 (Neurology 75:e21; VNS); Morrell MJ 2011 (Neurology 77:1295; RNS trial); Fisher RS et al. 2010 (Epilepsia 51:899; SANTE DBS trial) |

---

## Section 2 — Compound rules (`rules/compound.py`)

All compound rules are Phase 5 wave-2; they run after the wave-1
field-rule dispatch completes and mutate the partially-populated
`EpilepsyPhenotype` object. None of them call MedCAT or medspaCy
directly. Each reimplements published clinical criteria; no verbatim
clinical-text-mining code is copied from any external repository.

| # | Function | Field(s) mutated / derived | Primary reference |
|---:|---|---|---|
| 44 | `derive_drug_resistance` | `medication.drug_resistance_status` (ILAE 2010 Kwan five-way state machine mapped to 3-value enum) | Kwan P et al. 2010 (Epilepsia 51:1069) |
| 45 | `derive_epilepsy_duration_years` | `pheno._derived['epilepsy_duration_years']` (no schema slot) | Arithmetic on `doc_date.year` − onset_year; raw-text fallback |
| 46 | `derive_medication_currently_taking` | `medication.current_asms` / `prior_asms` (move on discontinuation cue) | medspaCy temporality convention^{Eyre2021}; ExECT `DrugPointInTime.jape` studied for cue vocabulary |
| 47 | `derive_ilae_classification_full` | `pheno._derived['ilae_classification']` (nested dict following ILAE 2017 tree levels 1-4) | Fisher RS et al. 2017 (Epilepsia 58:522); Scheffer IE et al. 2017 (Epilepsia 58:512) |
| 48 | `derive_seizure_free_since` | `pheno._derived['seizure_free_since']` (ISO date or duration quote) | Composed entities; F-S seizure_free ExECT rules studied for phrasing patterns |
| 49 | `derive_focal_to_bilateral_tc` | `clinical_seizure.predominant_seizure_type` (FBTC composition safety net) | Fisher RS et al. 2017; ExECT `jape/seizurechange.jape` studied |
| 50 | `derive_localization_concordance` | `integrated.concordance` (supersedes `ConcordanceStatusRule`, considers `clinical_localization.primary_claim`) | Rosenow F & Lüders H 2001 (Brain 124:1683); ILAE presurgical standards |
| 51 | `derive_surgery_outcome_class` | `surgery_history[i].engel_class` / `ilae_outcome`; `pheno._derived['post_surgical_outcome']` | Engel J Jr 1993; Wieser HG et al. 2001 (Epilepsia 42:282) |
| 52 | `derive_autoimmune_probable` | `pheno._derived['autoimmune_probable']` (bool) | Graus F et al. 2016 (Lancet Neurol 15:391) |
| 53 | `derive_polytherapy_flag` | `pheno._derived['polytherapy']` (bool if ≥ 2 concurrent-active ASMs) | Kanner AM & Bicchi MM 2022 (JAMA 327:1269) |

---

## Section 3 — Unique ExECT-V2 files studied (deduplicated)

The rules above collectively studied the following ExECT-V2 files
(deduplicated across the 43 field rules; alphabetical). This is the
"citation-inventory" summary that the manuscript's Attribution and
Licensing subsection references.

**JAPE files (~45 unique):**
`jape/addSeziureType.jape`, `jape/Age.jape`, `jape/age3.jape`,
`jape/AgeDiagnosed.jape`, `jape/AToNumberRange.jape`,
`jape/DiagfromSeizure.jape`, `jape/DiagnosisB.jape`,
`jape/DiagnosisB2.jape`, `jape/DiseaseCause.jape`,
`jape/dose-change.jape`, `jape/doses.jape`, `jape/DrugPointInTime.jape`,
`jape/EpiCause.jape`, `jape/EpiCause2.jape`, `jape/EpiCause3.jape`,
`jape/EpiCause4.jape`, `jape/EpilepsyCause.jape`,
`jape/EpilepsyDiagnosis.jape`, `jape/EpilepsyMentions.jape`,
`jape/FebrileSeizures.jape`, `jape/FebrileSeizuresB.jape`,
`jape/frequency.jape`, `jape/GenericInvestigations.jape`,
`jape/implicitSeizure.jape`, `jape/InvestConj.jape`,
`jape/InvestigationBlock.jape`, `jape/InvestigationsCT.jape`,
`jape/InvestigationsEEG.jape`, `jape/InvestigationsLookup.jape`,
`jape/InvestigationsMP.jape`, `jape/InvestigationsMRI.jape`,
`jape/InvestigationWithin.jape`, `jape/investigations.jape`,
`jape/KeepPrescription.jape`, `jape/KeepPrescriptionInText.jape`,
`jape/Lateralisation.jape`, `jape/LazyPrescription.jape`,
`jape/LocationAndFinding.jape`, `jape/mainSeizFreq.jape`,
`jape/measurement.jape`, `jape/MultipleSeizures.jape`,
`jape/NegatedFindingEEG.jape`, `jape/NegatedFindingMRI.jape`,
`jape/noMeds.jape`, `jape/numberRange.jape`, `jape/onset.jape`,
`jape/OnsetAge.jape`, `jape/OnsetAgeA.jape`, `jape/OnsetAgeB.jape`,
`jape/OnsetAgeC.jape`, `jape/OnsetAgeRange.jape`,
`jape/PartialSeizure.jape`, `jape/PluralSeizuresJAVA.jape`,
`jape/prescription-coref.jape`, `jape/prescription-implicit.jape`,
`jape/prescription-indicator.jape`, `jape/prescription.jape`,
`jape/prescription2.jape`, `jape/PrescriptionEpilepsy.jape`,
`jape/prescriptionFilter*.jape` (5 files),
`jape/PrescriptionML.jape`, `jape/PrescriptionMLCreated.jape`,
`jape/prescriptionSentence.jape`, `jape/routes.jape`,
`jape/SeizFreeFilter*.jape`, `jape/SeizFreeSentence.jape`,
`jape/SeizFreqFilter*.jape`, `jape/SeizFreqSentence.jape`,
`jape/SeizureFree.jape`, `jape/seizure-frequency.jape`,
`jape/seizure-frequency1.jape`, `jape/seizure-frequency2.jape`,
`jape/seizure-frequency3.jape`,
`jape/SeizureFrequencyExtendSinceDuring.jape`,
`jape/seizurechange.jape`, `jape/SeizureMentions.jape`,
`jape/SFBlockClean.jape`, `jape/SingleSeizure.jape`,
`jape/Symptomatic.jape`, `jape/Symptomatic2.jape`, `jape/times.jape`,
`jape/TimeSinceOnset.jape`, `jape/TimeSinceOnsetB.jape`,
`jape/TwoSeizureFreqOneTimePeriod.jape`.

**Groovy serializers (~15 unique):**
`Groovy/Diagnosis.groovy`, `Groovy/EpilepsyCause.groovy`,
`Groovy/Investigations.groovy`, `Groovy/MarkupDiagnosis.groovy`,
`Groovy/MarkupEpilepsyCause.groovy`, `Groovy/MarkupInvestigations.groovy`,
`Groovy/MarkupSeizureFrequency.groovy`, `Groovy/Onset.groovy`,
`Groovy/Prescription.groovy`, `Groovy/PrescriptionJson.groovy`,
`Groovy/SeizureFrequency.groovy`,
`Groovy/SeizureFrequencyFirstLetter.groovy`,
`Groovy/WhenDiagnosed.groovy`.

**Gazetteers / lookup files:**
`resources/gazetteers/seizure_targets.lst`,
`resources/gazetteers/EEG_results.lst`,
`resources/gazetteers/ct_mri_results.lst`,
`config/epilepsy.txt` (custom UMLS lexicon).

**Reference maps:**
`Other/ILAE proposed map to UMLS and SNOMEDCT.xlsx` (concept-linker
seed for `epilepsy_type`, `seizure_type`, `etiology_category`).

---

## Section 4 — Non-ExECT primary sources (deduplicated)

Rules with no ExECT counterpart (surgery, autoimmune, drug-resistance
state machine, non-drug therapy) are derived from published clinical
criteria:

- **Kwan P et al. 2010** (Epilepsia 51:1069) — ILAE 2010
  drug-resistance definition — cited by rows 28, 44.
- **Fisher RS et al. 2017** (Epilepsia 58:522) — ILAE 2017 seizure
  classification — cited by rows 2, 17, 20-22, 40-41, 47, 49.
- **Scheffer IE et al. 2017** (Epilepsia 58:512) — ILAE 2017
  classification of the epilepsies — cited by rows 18-19, 47.
- **Engel J Jr 1993** (Surgical Treatment of the Epilepsies 2nd ed.) —
  post-surgical outcome IA–IVC — cited by rows 43, 51.
- **Wieser HG et al. 2001** (Epilepsia 42:282) — ILAE post-surgical
  outcome scale — cited by rows 43, 51.
- **Graus F et al. 2016** (Lancet Neurol 15:391) — autoimmune
  encephalitis diagnostic criteria — cited by rows 1, 52.
- **Steriade C et al. 2020** (Epilepsia 61:1341) — autoimmune-
  associated epilepsy classification — cited by row 1.
- **Dubey D et al. 2020** (Ann Neurol 87:313) — autoantibody testing
  yield — cited by row 1.
- **Trinka E et al. 2015** (Epilepsia 56:1515) — ILAE SE definition —
  cited by row 42.
- **Brophy GM et al. 2012** — Neurocritical Care Society SE
  guidelines — cited by row 42.
- **Rosenow F & Lüders H 2001** (Brain 124:1683) — presurgical
  evaluation review — cited by rows 3-8, 50.
- **Palmini A et al. 2004** (Neurology 62 Suppl 3:S2) — FCD
  classification — cited by row 31.
- **Blümcke I et al. 2011** (Epilepsia 52:158) — ILAE FCD consensus —
  cited by row 31.
- **Rüber T et al. 2018** (Epilepsy Res 142:167) — 7T MRI in
  epilepsy — cited by rows 34-35.
- **Kossoff EH et al. 2018** (Epilepsia Open 3:175) — ketogenic
  diet — cited by rows 27.
- **Fisher RS et al. 2010** (Neurology 75:e21) — VNS overview —
  cited by rows 27, 43.
- **Morrell MJ 2011** (Neurology 77:1295) — RNS trial — cited by
  row 43.
- **Fisher RS et al. 2010** (Epilepsia 51:899) — SANTE DBS trial —
  cited by row 43.
- **Hirsch LJ et al. 2013** (J Clin Neurophysiol 30:1) — ACNS EEG
  terminology — cited by rows 9-16.
- **Kanner AM & Bicchi MM 2022** (JAMA 327:1269) — polytherapy
  usage — cited by row 53.
- **ILAE 2019 surgical epilepsy classification** (Lüders et al.) —
  cited by row 43.
- **ACR MRI practice guidelines** — cited by row 36.

---

## Section 5 — Auxiliary lexicon files (not counted as rules)

The following files are supporting infrastructure, not extraction
rules. They are cited for completeness because they carry ExECT-V2
or clinical-literature provenance in their docstrings:

- `rules/epilepsy_ontology.py` — 255 ontology entries mapping (enum,
  value) → {SCTID, CUI, label, synonyms}. Sources per entry:
  BioPortal SNOMED-CT browser; NINDS Common Data Elements;
  ILAE 2017 (Fisher et al.); RxNorm (NLM); F-S 160-letter
  training-corpus surface-form mining.
- `rules/context_config.py` — medspaCy ConText config with
  ExECT-V2 UK trigger set as fallback. medspaCy citation: Eyre H
  et al. 2021.
- `rules/context_config_us.py` — merged UK + US ConText triggers
  (`s/p`, `r/o`, `hx of`, `denies`, `w/o`, `-ve`, `no evidence of`,
  `no signs of`, `pt reports no`, `unremarkable`, `WNL`).
- `rules/uk_to_us_lexicon.py` — UK→US spelling normalization
  (~50 entries: paediatric→pediatric, oesophageal→esophageal,
  haemorrhage→hemorrhage, etc.) and UK→US drug-name crosswalks
  (~15 entries: phenobarbitone→phenobarbital,
  sodium valproate→valproic acid formulation, etc.).
- `rules/us_note_structure.py` — SOAP section detector for US
  clinical notes (SUBJECTIVE, OBJECTIVE, ASSESSMENT, PLAN, HPI,
  PMH, PSH, MEDICATIONS, REVIEW OF SYSTEMS, PHYSICAL EXAM,
  IMPRESSION, RECOMMENDATIONS).
- `rules/jape_to_python.md` — one-page cheatsheet mapping JAPE
  constructs to spaCy Matcher / Python (reference material only).

---

*End of Supplementary Rule Provenance Table.*
