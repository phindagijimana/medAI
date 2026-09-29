# ExECT-V2 File Inventory Mapped to MedAI-EPI v0.2.1 Schema Fields

**Purpose.** Phase 0.4 of the MedCAT+Rules build plan (`docs/MedCAT.md`).
Complete file-by-file inventory of the ExECT-V2 GATE pipeline
(github.com/swneurosci/ExECT-V2), with every JAPE / Groovy file mapped to the
MedAI-EPI v0.2.1 schema field it feeds (or marked `UNUSED`/`SKIP` if not
relevant).

**Source.** All content in this doc is *metadata* (filename, byte size,
one-line summary, schema-field mapping). No verbatim JAPE or Groovy code is
included. The source tree lives at `references/exect_v2/` (git-ignored,
study-only).

**Citation.** Fonferko-Shadrach B et al. *ExECT-V2 pipeline & annotation
guidelines,* BMC Med Res Methodol 2019 + J Biomed Semantics 2024.
Repository: <https://github.com/swneurosci/ExECT-V2> (commit `c6202de`).

---

## Coverage summary

| Priority | JAPE | Groovy | Total | Meaning |
|---|---:|---:|---:|---|
| **P1** — pilot-populated 8 fields | 133 | 9 | 142 | Port first (Phase 3 Days 4-6) |
| **P2** — remaining 16 fields | 51 | 3 | 54 | Port second (Phase 3 Days 7-8) |
| **SKIP** — orchestrator / helper / shared / `UNUSED` / redundant | 67 | 9 | 76 | Not directly ported; replaced by medspaCy/spaCy primitives or by the pipeline entry-point in `services/medcat_extractor.py` |
| **TOTAL** | **251** | **21** | **272** | |

Every file is classified. There are no `UNKNOWN` rows.

## Interpretation notes

1. **JAPE files are grammar-style rule files** compiled by GATE. Many small
   files exist because ExECT-V2 evolved iteratively, so nearly every schema
   field has a *family* of files (base + `B`/`C`/`D`/`Filter`/`Filter2`
   variants and cleanup passes). We only need to port the *union of the
   semantics,* not each file 1:1.
2. **Groovy files are output serializers** — they read GATE annotation sets
   (`Output` or `Original markups`) and write CSV / JSON. The `Markup*`
   Groovy files export the *hand-annotated gold standard* (not pipeline
   output), so they are `SKIP` in the pipeline-port sense but valuable as
   documentation of the gold-annotation schema.
3. **Time / date / negation / lookup helpers** (Ann Time gazetteers from
   GATE ANNIE, medspaCy ConText) are marked `SKIP` because medspaCy +
   spaCy provide equivalent primitives out-of-box — we do not port these.
4. **Machine-learning artefacts** (`PrescML`, `PrescriptionML`,
   `PrescriptionMLCreated`) refer to ExECT-V2's internal supervised-learning
   experiments and are not part of the rule set.
5. **Multiphase orchestrator files** (`epilepsy.jape`, `GenericDiagnosis.jape`,
   `GenericPrescription.jape`, `main.jape`, `stage1.jape`,
   `EpilepsySeizFreq.jape`) declare *phase chains*, not rules — the
   equivalent role in our pipeline is `services/medcat_extractor.py`'s
   pipeline configuration.
6. **CT investigation files** (`InvestigationsCT.jape`,
   `NegatedFindingCT.jape`) are marked `UNUSED`: our v0.2.1 schema has an
   `MriModule` but no CT module. If v0.3 adds CT, promote these to P2.
7. **`organisations.jape`** is a leftover from GATE ANNIE's named-entity
   pipeline and has no epilepsy relevance → `UNUSED`/`SKIP`.
8. **File families most relevant to Phase 3 P1:**
   - `seizure*` / `Seiz*` / `SF*` (~50 files) → `clinical_seizure.seizure_frequency` + `predominant_seizure_type`.
   - `Diag*` / `Diagnosis*` (~15 files) → `epilepsy.type` (EpilepsyType).
   - `EpiCause*` / `EpilepsyCause*` / `Symptomatic*` → `etiology_category`.
   - `Prescription*` / `Presc*` / `Drug*` / `frequency.jape` / `doses.jape` / `measurement.jape` → `medication.*`.
   - `Investigations*` / `NegatedFinding*` → `mri.*` and `eeg.*`.
   - `OnsetAge*` / `OnsetDate*` / `AgeDiagnosed*` / `TimeSince*` → `age_at_onset_years`.

## Interaction with Phase 1a (CUI seed extraction)

The following non-`.jape`/`.groovy` files are read by Phase 1a to build
`references/exect_v2_cui_seed.csv` (not listed here — they are dictionaries
and gazetteers, not rules):

- `Other/CustomUMLS/custom_umls.txt` (~500 CUIs).
- `Other/CustomUMLS/epilepsy.txt`, `seizure.txt`, `seizureSlang.txt`,
  `anticonvultants.txt`, `drugs.txt`, `comorbidities.txt`,
  `InvestResults.txt`, `BirthHistory.txt`.
- `epilepsy.lst`, `seizure.lst`, `drugs.lst`, `anticonvulscant.lst`,
  `comorbidities.lst` (~15 gazetteers).
- `Other/ILAE proposed map to UMLS and SNOMEDCT.xlsx` (exported by
  `scripts/export_exect_ilae_xlsx.py` to `references/exect_v2_ilae_map.csv`,
  149 rows).

---

## Full file inventory

### JAPE files (n=251)

| File | Bytes | Summary | Schema field(s) | Priority |
|---|---:|---|---|---|
| `AToNumberRange.jape` | 296 | Age token normalizer / range parser | clinical_seizure.age_at_onset_years — helper | P1 |
| `Age.jape` | 5308 | Age token normalizer / range parser | clinical_seizure.age_at_onset_years — helper | P1 |
| `AgeDiagnosed.jape` | 3728 | Diagnosis-date / time-since-diagnosis / time-since-onset extraction | clinical_seizure.age_at_onset_years (via computation) | P1 |
| `BirthHistory.jape` | 6995 | Birth-history detection (prematurity, birth injuries, normal birth) | birth_history (currently free-text; may map to comorbidities in v0.3) | P2 |
| `BirthHistoryB.jape` | 4284 | Birth-history detection (prematurity, birth injuries, normal birth) | birth_history (currently free-text; may map to comorbidities in v0.3) | P2 |
| `BirthHistoryC.jape` | 670 | Birth-history detection (prematurity, birth injuries, normal birth) | birth_history (currently free-text; may map to comorbidities in v0.3) | P2 |
| `BirthHistoryD.jape` | 1350 | Birth-history detection (prematurity, birth injuries, normal birth) | birth_history (currently free-text; may map to comorbidities in v0.3) | P2 |
| `Certainty.jape` | 82 | Certainty / probability-level assignment (Levels 1-5) | shared — Certainty enum across all fields | SKIP |
| `CompoundLookup.jape` | 58 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `ContextCorrection.jape` | 889 | Context / experiencer correction (patient vs family) | shared — feeds family_history subject disambiguation | SKIP |
| `ControlAsSplit.jape` | 171 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `DateBio.jape` | 2190 | Date / DOB / clinic-date extraction (patient metadata) | document metadata (encounter_date) — not a phenotype field | P2 |
| `DateDiagnosed.jape` | 4317 | Diagnosis-date / time-since-diagnosis / time-since-onset extraction | clinical_seizure.age_at_onset_years (via computation) | P1 |
| `DateDiagnosedB.jape` | 2437 | Diagnosis-date / time-since-diagnosis / time-since-onset extraction | clinical_seizure.age_at_onset_years (via computation) | P1 |
| `DateSince.jape` | 1276 | Diagnosis-date / time-since-diagnosis / time-since-onset extraction | clinical_seizure.age_at_onset_years (via computation) | P1 |
| `DelNumInMeasurment.jape` | 848 | Cleanup — deletes stray numeric tokens inside measurement spans | medication.current_asms[] — filter, no direct extraction | P1 |
| `DeleteLookupAfterTigDeleted.jape` | 2111 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `DeleteNonAsTrigger.jape` | 970 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `DiagBFilter.jape` | 646 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DiagBFilter2.jape` | 505 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DiagExclude.jape` | 871 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DiagExclude2.jape` | 387 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DiagInInvestDelete.jape` | 1671 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DiagTrigSFreq.jape` | 1727 | Seizure-frequency helper / cleanup / edge-case rules | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `DiagfromSeizure.jape` | 3089 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DiagfromSeizureLookup3.jape` | 1260 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DiagnosisB.jape` | 2947 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DiagnosisB2.jape` | 1301 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DiagnosisFilter.jape` | 755 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DiagnosisHypothetical.jape` | 703 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DiagnosisMP.jape` | 289 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DiseaseCause.jape` | 559 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `DoB.jape` | 587 | Date / DOB / clinic-date extraction (patient metadata) | document metadata (encounter_date) — not a phenotype field | P2 |
| `DrugPointInTime.jape` | 615 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `EpiCause.jape` | 5905 | Epilepsy-cause / etiology extraction (structural, symptomatic, etc.) | clinical_seizure.etiology_category (EtiologyCategory), etiology_details_text | P1 |
| `EpiCause2.jape` | 1039 | Epilepsy-cause / etiology extraction (structural, symptomatic, etc.) | clinical_seizure.etiology_category (EtiologyCategory), etiology_details_text | P1 |
| `EpiCause3.jape` | 1045 | Epilepsy-cause / etiology extraction (structural, symptomatic, etc.) | clinical_seizure.etiology_category (EtiologyCategory), etiology_details_text | P1 |
| `EpiCause4.jape` | 1578 | Epilepsy-cause / etiology extraction (structural, symptomatic, etc.) | clinical_seizure.etiology_category (EtiologyCategory), etiology_details_text | P1 |
| `EpilepsyCause.jape` | 426 | Epilepsy-cause / etiology extraction (structural, symptomatic, etc.) | clinical_seizure.etiology_category (EtiologyCategory), etiology_details_text | P1 |
| `EpilepsyDiagnosis.jape` | 112 | Epilepsy-diagnosis detection / gazetteer / filter | epilepsy.type (EpilepsyType) | P1 |
| `EpilepsyFilters.jape` | 703 | Epilepsy-diagnosis detection / gazetteer / filter | epilepsy.type (EpilepsyType) | P1 |
| `EpilepsyInvestigations.jape` | 238 | Investigation-generic detection / dispatch / helper | eeg.performed (bool), mri.overall_normal (bool) via imaging_eeg_performed.py | P2 |
| `EpilepsyJAVA.jape` | 2113 | Epilepsy-diagnosis detection / gazetteer / filter | epilepsy.type (EpilepsyType) | P1 |
| `EpilepsyMentions.jape` | 395 | Epilepsy-diagnosis detection / gazetteer / filter | epilepsy.type (EpilepsyType) | P1 |
| `EpilepsyPsuedoLookups.jape` | 89 | Epilepsy-diagnosis detection / gazetteer / filter | epilepsy.type (EpilepsyType) | P1 |
| `EpilepsySeizFreq.jape` | 296 | Multiphase orchestrator — chains SeizFrequency + SeizureFree phases | orchestration only — no direct schema mapping | SKIP |
| `ExperiencerReversal.jape` | 6261 | Context / experiencer correction (patient vs family) | shared — feeds family_history subject disambiguation | SKIP |
| `FebrileSeizures.jape` | 8189 | Febrile-seizure detection (both affirmed and negated statements) | comorbidities[] or family_history — subject-dependent | P2 |
| `FebrileSeizuresB.jape` | 641 | Febrile-seizure detection (both affirmed and negated statements) | comorbidities[] or family_history — subject-dependent | P2 |
| `FilterOutLearningDis.jape` | 376 | Filter for 'learning disability' mentions (avoid double-annotation) | comorbidities[] — filter | P2 |
| `FinalCleanUp.jape` | 51 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `GenericDiagnosis.jape` | 192 | Stage-1 multiphase orchestrator — chains tokenizer / list-splitter phases | orchestration only — no direct schema mapping | SKIP |
| `GenericInvestigations.jape` | 124 | Investigation-generic detection / dispatch / helper | eeg.performed (bool), mri.overall_normal (bool) via imaging_eeg_performed.py | P2 |
| `GenericPrescription.jape` | 143 | Stage-1 multiphase orchestrator — chains tokenizer / list-splitter phases | orchestration only — no direct schema mapping | SKIP |
| `GenericSeizureFrequency.jape` | 204 | Generic seizure-frequency fallback pattern | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `InvestConj.jape` | 2154 | Investigation-generic detection / dispatch / helper | eeg.performed (bool), mri.overall_normal (bool) via imaging_eeg_performed.py | P2 |
| `InvestigationBlock.jape` | 984 | Investigation-generic detection / dispatch / helper | eeg.performed (bool), mri.overall_normal (bool) via imaging_eeg_performed.py | P2 |
| `InvestigationWithin.jape` | 1666 | Investigation-generic detection / dispatch / helper | eeg.performed (bool), mri.overall_normal (bool) via imaging_eeg_performed.py | P2 |
| `Investigations.jape` | 2070 | Investigation-generic detection / dispatch / helper | eeg.performed (bool), mri.overall_normal (bool) via imaging_eeg_performed.py | P2 |
| `InvestigationsCT.jape` | 10026 | CT investigation / negated CT findings detection | UNUSED — v0.2.1 schema has no CT module (MRI-only) | SKIP |
| `InvestigationsEEG.jape` | 11107 | EEG investigation / negated EEG findings detection | eeg.background (EegBackground), eeg.ied_findings[] (IedFinding, IedType) | P1 |
| `InvestigationsLookup.jape` | 11317 | Investigation-generic detection / dispatch / helper | eeg.performed (bool), mri.overall_normal (bool) via imaging_eeg_performed.py | P2 |
| `InvestigationsMP.jape` | 339 | Investigation-generic detection / dispatch / helper | eeg.performed (bool), mri.overall_normal (bool) via imaging_eeg_performed.py | P2 |
| `InvestigationsMRI.jape` | 11155 | MRI investigation / negated MRI findings detection | mri.findings[] (MriFinding), mri.overall_normal | P1 |
| `KeepPrescription.jape` | 2957 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `KeepPrescriptionInText.jape` | 684 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `Lateralisation.jape` | 900 | Adds laterality feature to focal-epilepsy diagnosis | clinical_localization.primary_claim.laterality (Laterality) | P2 |
| `LazyPrescription.jape` | 1760 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `LocationAndFinding.jape` | 1108 | Investigation-generic detection / dispatch / helper | eeg.performed (bool), mri.overall_normal (bool) via imaging_eeg_performed.py | P2 |
| `Lookaround.jape` | 535 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `Lookaround2.jape` | 195 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `Lookup2Annotation.jape` | 191 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `Lookup3Appelt.jape` | 459 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `Lookup3AppeltComorbs.jape` | 478 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `LookupAppelt.jape` | 444 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `LookupDrift.jape` | 605 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `LookupPhrases.jape` | 118 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `LookupSplit.jape` | 207 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `LookupWithin.jape` | 836 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `MedicalHistory.jape` | 3645 | Patient-history / medical-history / comorbidity extraction | comorbidities[], family_history (subject disambiguation needed) | P2 |
| `MedicalHistoryB.jape` | 1008 | Patient-history / medical-history / comorbidity extraction | comorbidities[], family_history (subject disambiguation needed) | P2 |
| `Medmod.jape` | 2023 | Patient-history / medical-history / comorbidity extraction | comorbidities[], family_history (subject disambiguation needed) | P2 |
| `MultipleSeizures.jape` | 1514 | Seizure-instance detection (single / multiple / partial / previous) | clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `NP.jape` | 648 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `NegatedFindingCT.jape` | 1011 | CT investigation / negated CT findings detection | UNUSED — v0.2.1 schema has no CT module (MRI-only) | SKIP |
| `NegatedFindingEEG.jape` | 1020 | EEG investigation / negated EEG findings detection | eeg.background (EegBackground), eeg.ied_findings[] (IedFinding, IedType) | P1 |
| `NegatedFindingMRI.jape` | 1020 | MRI investigation / negated MRI findings detection | mri.findings[] (MriFinding), mri.overall_normal | P1 |
| `NegationBack.jape` | 4416 | Negation / negation-cleanup pass (medspaCy ConText equivalent) | shared — feeds Certainty.NEGATED across all fields | SKIP |
| `NegationCleanUp.jape` | 4632 | Negation / negation-cleanup pass (medspaCy ConText equivalent) | shared — feeds Certainty.NEGATED across all fields | SKIP |
| `NegationCleanup2.jape` | 2193 | Negation / negation-cleanup pass (medspaCy ConText equivalent) | shared — feeds Certainty.NEGATED across all fields | SKIP |
| `NegationCleanup3.jape` | 2081 | Negation / negation-cleanup pass (medspaCy ConText equivalent) | shared — feeds Certainty.NEGATED across all fields | SKIP |
| `NegationCleanup4.jape` | 1346 | Negation / negation-cleanup pass (medspaCy ConText equivalent) | shared — feeds Certainty.NEGATED across all fields | SKIP |
| `OnsetAge.jape` | 12069 | Age-at-onset / onset-date extraction | clinical_seizure.age_at_onset_years | P1 |
| `OnsetAgeA.jape` | 1560 | Age-at-onset / onset-date extraction | clinical_seizure.age_at_onset_years | P1 |
| `OnsetAgeB.jape` | 3246 | Age-at-onset / onset-date extraction | clinical_seizure.age_at_onset_years | P1 |
| `OnsetAgeC.jape` | 838 | Age-at-onset / onset-date extraction | clinical_seizure.age_at_onset_years | P1 |
| `OnsetAgeRange.jape` | 3369 | Age-at-onset / onset-date extraction | clinical_seizure.age_at_onset_years | P1 |
| `OnsetDate.jape` | 7430 | Age-at-onset / onset-date extraction | clinical_seizure.age_at_onset_years | P1 |
| `OnsetDateB.jape` | 3073 | Age-at-onset / onset-date extraction | clinical_seizure.age_at_onset_years | P1 |
| `OnsetDateC.jape` | 155 | Age-at-onset / onset-date extraction | clinical_seizure.age_at_onset_years | P1 |
| `OnsetDateD.jape` | 782 | Age-at-onset / onset-date extraction | clinical_seizure.age_at_onset_years | P1 |
| `OtherDiagCleaning.jape` | 590 | Other-diagnosis / comorbidity list-mining | comorbidities[] | P2 |
| `OtherDiagPhrase.jape` | 13771 | Other-diagnosis / comorbidity list-mining | comorbidities[] | P2 |
| `OtherDiagnosis.jape` | 5941 | Other-diagnosis / comorbidity list-mining | comorbidities[] | P2 |
| `OtherDiagnosisB.jape` | 4277 | Other-diagnosis / comorbidity list-mining | comorbidities[] | P2 |
| `OtherDiagnosisC.jape` | 5948 | Other-diagnosis / comorbidity list-mining | comorbidities[] | P2 |
| `OtherDiagnosisInvest.jape` | 1057 | Investigation-generic detection / dispatch / helper | eeg.performed (bool), mri.overall_normal (bool) via imaging_eeg_performed.py | P2 |
| `OtherDiagnosisListA.jape` | 6121 | Other-diagnosis / comorbidity list-mining | comorbidities[] | P2 |
| `OtherDiagnosisListB.jape` | 6828 | Other-diagnosis / comorbidity list-mining | comorbidities[] | P2 |
| `OtherDiagnosisListC.jape` | 4761 | Other-diagnosis / comorbidity list-mining | comorbidities[] | P2 |
| `OtherDiagnosisListD.jape` | 3381 | Other-diagnosis / comorbidity list-mining | comorbidities[] | P2 |
| `OtherDiagnosisListE.jape` | 1348 | Other-diagnosis / comorbidity list-mining | comorbidities[] | P2 |
| `OtherDiagnosisListF.jape` | 5216 | Other-diagnosis / comorbidity list-mining | comorbidities[] | P2 |
| `PartialDateYear.jape` | 352 | Date / DOB / clinic-date extraction (patient metadata) | document metadata (encounter_date) — not a phenotype field | P2 |
| `PartialSeizure.jape` | 2257 | Seizure-instance detection (single / multiple / partial / previous) | clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `PatientDates.jape` | 55 | Date / DOB / clinic-date extraction (patient metadata) | document metadata (encounter_date) — not a phenotype field | P2 |
| `PatientHistA.jape` | 30651 | Patient-history / medical-history / comorbidity extraction | comorbidities[], family_history (subject disambiguation needed) | P2 |
| `PatientHistB.jape` | 11162 | Patient-history / medical-history / comorbidity extraction | comorbidities[], family_history (subject disambiguation needed) | P2 |
| `PatientHistC.jape` | 4125 | Patient-history / medical-history / comorbidity extraction | comorbidities[], family_history (subject disambiguation needed) | P2 |
| `PatientHistD.jape` | 2821 | Patient-history / medical-history / comorbidity extraction | comorbidities[], family_history (subject disambiguation needed) | P2 |
| `PatientHistE.jape` | 1538 | Patient-history / medical-history / comorbidity extraction | comorbidities[], family_history (subject disambiguation needed) | P2 |
| `PatientHistory.jape` | 477 | Patient-history / medical-history / comorbidity extraction | comorbidities[], family_history (subject disambiguation needed) | P2 |
| `Phrase3.jape` | 165 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `PhraseLookup.jape` | 468 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `PhrasePruning.jape` | 374 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `PluralSeizuresJAVA.jape` | 1657 | Seizure-instance detection (single / multiple / partial / previous) | clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `PrescML.jape` | 1303 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `PrescriptionEpilepsy.jape` | 132 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `PrescriptionML.jape` | 201 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `PrescriptionMLCreated.jape` | 763 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `PrescriptionNotFilter.jape` | 325 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `PrescriptionNotFilter2.jape` | 375 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `PreviousSeizure.jape` | 4240 | Seizure-instance detection (single / multiple / partial / previous) | clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `RemoveLookup2FromTimeSince.jape` | 921 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `RemoveOldPrescML.jape` | 606 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `RemoveSeizFreeBlock.jape` | 269 | Seizure-frequency helper / cleanup / edge-case rules | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `RemoveSeizure.jape` | 393 | Exclusion filter — removes false-positive seizure lookups | clinical_seizure.predominant_seizure_type (SeizureType) — filter, no direct extraction | P1 |
| `RemoveSeizureLookups.jape` | 2890 | Exclusion filter — removes false-positive seizure lookups | clinical_seizure.predominant_seizure_type (SeizureType) — filter, no direct extraction | P1 |
| `RemoveSeziure.jape` | 402 | Exclusion filter — removes false-positive seizure lookups | clinical_seizure.predominant_seizure_type (SeizureType) — filter, no direct extraction | P1 |
| `RemoveTimePeriodFromAge.jape` | 500 | Age token normalizer / range parser | clinical_seizure.age_at_onset_years — helper | P1 |
| `RemoveTimeSinceFromAge.jape` | 275 | Age token normalizer / range parser | clinical_seizure.age_at_onset_years — helper | P1 |
| `SF.jape` | 7141 | Seizure-frequency helper / cleanup / edge-case rules | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `SFBlockClean.jape` | 268 | Seizure-frequency helper / cleanup / edge-case rules | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `SeizChangeFilter.jape` | 1215 | Seizure-change / seizure-type transition rules (e.g. focal→bilateral TC) | clinical_seizure.predominant_seizure_type (SeizureType), compound.focal_to_bilateral_tc | P1 |
| `SeizChangeFilter2.jape` | 1441 | Seizure-change / seizure-type transition rules (e.g. focal→bilateral TC) | clinical_seizure.predominant_seizure_type (SeizureType), compound.focal_to_bilateral_tc | P1 |
| `SeizChangeSentence.jape` | 1397 | Seizure-change / seizure-type transition rules (e.g. focal→bilateral TC) | clinical_seizure.predominant_seizure_type (SeizureType), compound.focal_to_bilateral_tc | P1 |
| `SeizFreeFilter.jape` | 1545 | Seizure-free interval detection | clinical_seizure.seizure_frequency (SeizureFrequency.seizure_free) | P1 |
| `SeizFreeFilter2.jape` | 1456 | Seizure-free interval detection | clinical_seizure.seizure_frequency (SeizureFrequency.seizure_free) | P1 |
| `SeizFreeSentence.jape` | 1431 | Seizure-free interval detection | clinical_seizure.seizure_frequency (SeizureFrequency.seizure_free) | P1 |
| `SeizFreqFilter.jape` | 1796 | Seizure-frequency detection rules (counts, periods, since/during) | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `SeizFreqFilter2.jape` | 1501 | Seizure-frequency detection rules (counts, periods, since/during) | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `SeizFreqFilter3.jape` | 1339 | Seizure-frequency detection rules (counts, periods, since/during) | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `SeizFreqSentence.jape` | 1502 | Seizure-frequency detection rules (counts, periods, since/during) | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `SeizFrequency.jape` | 2223 | Seizure-frequency detection rules (counts, periods, since/during) | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `SeizureControl.jape` | 10701 | Seizure-control status rules (controlled / uncontrolled / breakthrough) | epilepsy.drug_resistance (DrugResistanceStatus, compound) | P1 |
| `SeizureExclude.jape` | 121 | Exclusion filter — removes false-positive seizure lookups | clinical_seizure.predominant_seizure_type (SeizureType) — filter, no direct extraction | P1 |
| `SeizureExclude1.jape` | 1179 | Exclusion filter — removes false-positive seizure lookups | clinical_seizure.predominant_seizure_type (SeizureType) — filter, no direct extraction | P1 |
| `SeizureExclude3.jape` | 325 | Exclusion filter — removes false-positive seizure lookups | clinical_seizure.predominant_seizure_type (SeizureType) — filter, no direct extraction | P1 |
| `SeizureExclude4.jape` | 539 | Exclusion filter — removes false-positive seizure lookups | clinical_seizure.predominant_seizure_type (SeizureType) — filter, no direct extraction | P1 |
| `SeizureFree.jape` | 36738 | Seizure-free interval detection | clinical_seizure.seizure_frequency (SeizureFrequency.seizure_free) | P1 |
| `SeizureFrequencyExtendSinceDuring.jape` | 1461 | Seizure-frequency helper / cleanup / edge-case rules | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `SeizureFrequencyMP.jape` | 459 | Seizure-frequency helper / cleanup / edge-case rules | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `SeizureMentions.jape` | 6207 | Seizure-mention detection (surface anchoring for downstream rules) | clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `SeizureSince.jape` | 5694 | 'Since X seizure' rules — anchors seizure count to a temporal reference | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `SeziureExclude.jape` | 391 | Exclusion filter — removes false-positive seizure lookups | clinical_seizure.predominant_seizure_type (SeizureType) — filter, no direct extraction | P1 |
| `SinceDate.jape` | 0 | Diagnosis-date / time-since-diagnosis / time-since-onset extraction | clinical_seizure.age_at_onset_years (via computation) | P1 |
| `SingleSeizure.jape` | 570 | Seizure-instance detection (single / multiple / partial / previous) | clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `SingleSeizureJAVA.jape` | 1644 | Seizure-instance detection (single / multiple / partial / previous) | clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `SingleSeizureLookup.jape` | 535 | Seizure-instance detection (single / multiple / partial / previous) | clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `Symptomatic.jape` | 840 | Epilepsy-cause / etiology extraction (structural, symptomatic, etc.) | clinical_seizure.etiology_category (EtiologyCategory), etiology_details_text | P1 |
| `Symptomatic2.jape` | 1613 | Epilepsy-cause / etiology extraction (structural, symptomatic, etc.) | clinical_seizure.etiology_category (EtiologyCategory), etiology_details_text | P1 |
| `TheseLookups.jape` | 683 | Lookup-cleanup pass — resolves 'these X' anaphora spanning Lookup annotations | shared linguistic helper | SKIP |
| `ThirdDose.jape` | 1799 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `TimeSince.jape` | 1860 | Diagnosis-date / time-since-diagnosis / time-since-onset extraction | clinical_seizure.age_at_onset_years (via computation) | P1 |
| `TimeSinceDiagnosis.jape` | 3011 | Diagnosis-date / time-since-diagnosis / time-since-onset extraction | clinical_seizure.age_at_onset_years (via computation) | P1 |
| `TimeSinceOnset.jape` | 9435 | Diagnosis-date / time-since-diagnosis / time-since-onset extraction | clinical_seizure.age_at_onset_years (via computation) | P1 |
| `TimeSinceOnsetB.jape` | 5023 | Diagnosis-date / time-since-diagnosis / time-since-onset extraction | clinical_seizure.age_at_onset_years (via computation) | P1 |
| `TimeSinceOnsetRange.jape` | 1840 | Diagnosis-date / time-since-diagnosis / time-since-onset extraction | clinical_seizure.age_at_onset_years (via computation) | P1 |
| `Token2Verbs.jape` | 584 | Token→verb POS helper | shared linguistic helper | SKIP |
| `TwoSeizureFreqOneTimePeriod.jape` | 2131 | Seizure-frequency helper / cleanup / edge-case rules | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `YearToMonths.jape` | 1265 | Age token normalizer / range parser | clinical_seizure.age_at_onset_years — helper | P1 |
| `addSeziureType.jape` | 360 | Adds seizure-type attribute to detected seizure annotations | clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `addString.jape` | 730 | Attaches a normalised-string feature to matched spans | shared span-attribute helper | SKIP |
| `age3.jape` | 522 | Age token normalizer / range parser | clinical_seizure.age_at_onset_years — helper | P1 |
| `annotation-pruning.jape` | 1250 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `bratRename.jape` | 184 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `cleaning.jape` | 2569 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `cleaning2.jape` | 4168 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `clinicDate.jape` | 2067 | Date / DOB / clinic-date extraction (patient metadata) | document metadata (encounter_date) — not a phenotype field | P2 |
| `copy-lookups.jape` | 1666 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `dates.jape` | 365 | Date / DOB / clinic-date extraction (patient metadata) | document metadata (encounter_date) — not a phenotype field | P2 |
| `defaultProbability.jape` | 1566 | Certainty / probability-level assignment (Levels 1-5) | shared — Certainty enum across all fields | SKIP |
| `diagnosisA.jape` | 4155 | Diagnosis extraction / filter / hypothetical handling | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `docID.jape` | 189 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `dose-change.jape` | 547 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `doses.jape` | 317 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `drug_modifier.jape` | 437 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `endList.jape` | 190 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `epilepsy.jape` | 1134 | Top-level multi-phase pipeline definition for epilepsy phases | orchestration only — no direct schema mapping | SKIP |
| `exclude.jape` | 865 | Global exclusion / negation-context pass (marked 'DONT NEED - REMOVED FROM PIPELINE') | shared — legacy, no direct schema mapping | SKIP |
| `frequency.jape` | 3787 | Dose-frequency pattern rules (bd, tds, times per day, etc.) | medication.current_asms[].dose_text (Medication) | P1 |
| `furtherDiagnosis.jape` | 3520 | Second-pass diagnosis extraction after cleanup | epilepsy.type (EpilepsyType) | P1 |
| `implicitSeizure.jape` | 4737 | Seizure-instance detection (single / multiple / partial / previous) | clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `listPoint.jape` | 350 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `listSent.jape` | 515 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `longestTimePeriod.jape` | 383 | Time / duration token gazetteer / normalizer (from GATE ANNIE) | shared time helper — used by many field rules | SKIP |
| `lookup2seizure.jape` | 1116 | Promotes Lookup annotations to Seizure annotations | clinical_seizure.predominant_seizure_type (SeizureType) — helper | P1 |
| `main.jape` | 247 | Pipeline entrypoint / stage orchestrator | orchestration only — no direct schema mapping | SKIP |
| `mainSeizFreq.jape` | 76 | Seizure-frequency detection rules (counts, periods, since/during) | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `measurement.jape` | 250 | Measurement token normalizer (mg, g, ml) | medication.current_asms[].dose_text (Medication) | P1 |
| `medFinding.jape` | 704 | Medical-finding surface detection | mri.findings[] / eeg.ied_findings[] — shared lookup | P2 |
| `newLine.jape` | 172 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `newParagraph.jape` | 310 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `noMeds.jape` | 408 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `nounsplit.jape` | 310 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `numberRange.jape` | 1045 | Number / range parser | shared numeric helper — used by frequency + age rules | SKIP |
| `numbers.jape` | 571 | Number / range parser | shared numeric helper — used by frequency + age rules | SKIP |
| `onset.jape` | 252 | Age-at-onset / onset-date extraction | clinical_seizure.age_at_onset_years | P1 |
| `organisations.jape` | 409 | Organisation named-entity gazetteer (from GATE ANNIE) | UNUSED — irrelevant to our schema | SKIP |
| `partialDate.jape` | 1148 | Date / DOB / clinic-date extraction (patient metadata) | document metadata (encounter_date) — not a phenotype field | P2 |
| `pastTense.jape` | 342 | Past-tense marker rules (historic vs current) | shared — feeds medication.status (MedicationStatus.PRIOR) and Certainty.HISTORICAL | P2 |
| `prescription-coref.jape` | 1473 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `prescription-implicit.jape` | 2872 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `prescription-indicator.jape` | 392 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `prescription.jape` | 5512 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `prescription2.jape` | 769 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `prescriptionFilter.jape` | 2321 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `prescriptionFilterCSV.jape` | 880 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `prescriptionFilterCSVJAVA.jape` | 428 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `prescriptionNotFilterCSV.jape` | 514 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `prescriptionSentence.jape` | 683 | Prescription / drug / dose / frequency detection | medication.current_asms[] (Medication.generic_name, dose_text, status) | P1 |
| `probability.jape` | 3725 | Certainty / probability-level assignment (Levels 1-5) | shared — Certainty enum across all fields | SKIP |
| `probabilityWithin.jape` | 1040 | Certainty / probability-level assignment (Levels 1-5) | shared — Certainty enum across all fields | SKIP |
| `probabilitydrift.jape` | 1012 | Certainty / probability-level assignment (Levels 1-5) | shared — Certainty enum across all fields | SKIP |
| `pruning.jape` | 245 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `rangeOrNumber.jape` | 256 | Number / range parser | shared numeric helper — used by frequency + age rules | SKIP |
| `removeFreeasNegation.jape` | 327 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `removeUselessLookups.jape` | 654 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `routes.jape` | 736 | Drug route-of-administration parser (oral, IV, IM) | medication.current_asms[].dose_text (Medication) — extension | P2 |
| `seizure-frequency.jape` | 17661 | Seizure-frequency detection rules (counts, periods, since/during) | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `seizure-frequency1.jape` | 31110 | Seizure-frequency detection rules (counts, periods, since/during) | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `seizure-frequency2.jape` | 33643 | Seizure-frequency detection rules (counts, periods, since/during) | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `seizure-frequency3.jape` | 1053 | Seizure-frequency detection rules (counts, periods, since/during) | clinical_seizure.seizure_frequency (SeizureFrequency) | P1 |
| `seizureExclude2.jape` | 620 | Exclusion filter — removes false-positive seizure lookups | clinical_seizure.predominant_seizure_type (SeizureType) — filter, no direct extraction | P1 |
| `seizurechange.jape` | 42466 | Seizure-change / seizure-type transition rules (e.g. focal→bilateral TC) | clinical_seizure.predominant_seizure_type (SeizureType), compound.focal_to_bilateral_tc | P1 |
| `splitNounChunks.jape` | 328 | Tokenizer / sentence-splitter / lookup-scaffolding / cleanup helper | shared — no direct schema mapping (spaCy/medspaCy replaces) | SKIP |
| `stage1.jape` | 650 | Pipeline entrypoint / stage orchestrator | orchestration only — no direct schema mapping | SKIP |
| `status.jape` | 873 | Status keyword tagging (historic, current, planned) | medication.status (MedicationStatus), TemporalStatus | P2 |
| `tense.jape` | 1642 | Past-tense marker rules (historic vs current) | shared — feeds medication.status (MedicationStatus.PRIOR) and Certainty.HISTORICAL | P2 |
| `timeElapsedRemove.jape` | 690 | Time / duration token gazetteer / normalizer (from GATE ANNIE) | shared time helper — used by many field rules | SKIP |
| `times.jape` | 4391 | Time / duration token gazetteer / normalizer (from GATE ANNIE) | shared time helper — used by many field rules | SKIP |


### Groovy files (n=21)

| File | Bytes | Summary | Schema field(s) | Priority |
|---|---:|---|---|---|
| `BirthHistory.groovy` | 645 | BirthHistory serializer | birth_history | P2 |
| `Diagnosis.groovy` | 805 | Diagnosis serializer | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | P1 |
| `EpilepsyCause.groovy` | 667 | EpilepsyCause serializer | clinical_seizure.etiology_category (EtiologyCategory) | P1 |
| `Investigations.groovy` | 738 | Investigations serializer | eeg.*, mri.* — top-level investigation output | P1 |
| `MarkupBirthHistory.groovy` | 537 | Markup gold-standard serializer for Birthhistory — reads 'Original markups' AS | birth_history | SKIP |
| `MarkupDiagnosis.groovy` | 459 | Markup gold-standard serializer for Diagnosis — reads 'Original markups' AS | epilepsy.type (EpilepsyType), clinical_seizure.predominant_seizure_type (SeizureType) | SKIP |
| `MarkupEpilepsyCause.groovy` | 440 | Markup gold-standard serializer for Epilepsycause — reads 'Original markups' AS | clinical_seizure.etiology_category (EtiologyCategory) | SKIP |
| `MarkupInvestigations.groovy` | 731 | Markup gold-standard serializer for Investigations — reads 'Original markups' AS | eeg.*, mri.* — top-level investigation output | SKIP |
| `MarkupOnset.groovy` | 865 | Markup gold-standard serializer for Onset — reads 'Original markups' AS | clinical_seizure.age_at_onset_years | SKIP |
| `MarkupPatientHistory.groovy` | 829 | Markup gold-standard serializer for Patienthistory — reads 'Original markups' AS | comorbidities[], family_history | SKIP |
| `MarkupPrescription.groovy` | 619 | Markup gold-standard serializer for Prescription — reads 'Original markups' AS | medication.current_asms[] | SKIP |
| `MarkupSeizureFrequency.groovy` | 1026 | Markup gold-standard serializer for Seizurefrequency — reads 'Original markups' AS | clinical_seizure.seizure_frequency | SKIP |
| `MarkupWhenDiagnosed.groovy` | 825 | Markup gold-standard serializer for Whendiagnosed — reads 'Original markups' AS | clinical_seizure.age_at_onset_years (computed via encounter date) | SKIP |
| `Onset.groovy` | 822 | Onset serializer | clinical_seizure.age_at_onset_years | P1 |
| `PatientHistory.groovy` | 930 | PatientHistory serializer | comorbidities[], family_history | P2 |
| `Prescription.groovy` | 607 | Prescription serializer (CSV) | medication.current_asms[] | P1 |
| `PrescriptionJson.groovy` | 548 | Prescription serializer (JSON) | medication.current_asms[] | P1 |
| `RemoveDuplicate.groovy` | 1228 | Deduplicates overlapping PatientHistory annotations | comorbidities[] — dedup helper | P2 |
| `SeizureFrequency.groovy` | 1006 | SeizureFrequency serializer | clinical_seizure.seizure_frequency | P1 |
| `SeizureFrequencyFirstLetter.groovy` | 3119 | SeizureFrequency serializer (first-letter-only for corpus prep) | clinical_seizure.seizure_frequency | P1 |
| `WhenDiagnosed.groovy` | 842 | WhenDiagnosed serializer | clinical_seizure.age_at_onset_years (computed via encounter date) | P2 |

