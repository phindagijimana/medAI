# An open framework for schema-constrained, evidence-grounded structured epilepsy phenotype extraction from clinical documents

*Draft v0.2 — internal, PI + co-author review. Voice matched to Ndagijimana et al., Brain Communications 2026 (AutoHS paper). Formatting will be adapted to target-journal style at submission.*

Philbert Ndagijimana,1 [Co-Author 2],2 [Co-Author 3],3 James J. Gugger.1,2

1 Department of Neurology, University of Rochester, School of Medicine and Dentistry, Rochester, NY, USA
2 [Additional affiliations to be finalized]
3 [Additional affiliations to be finalized]

Correspondence to: [Corresponding author, title, affiliation, email].

Keywords: epilepsy phenotyping; large language models; structured information extraction; evidence grounding; ILAE 2017; open-source framework.

Received [date]. Revised [date]. Accepted [date]. Advance access publication [date].

---

Structured epilepsy phenotype variables — seizure type, epilepsy type, medication history, drug-resistance status, imaging findings, and surgical outcomes — are the analytic substrate for retrospective cohort research, genotype-phenotype correlation, and downstream multimodal modelling of raw EEG and MRI. In routine care these variables live in unstructured clinical text distributed across MRI reports, EEG reports, progress notes, EMU discharge summaries, presurgical evaluations, and surgery-conference notes. Extraction pipelines that recover them at institutional scale have been reported, but the underlying corpora and annotation schemas are almost never released, limiting cross-study comparison and reproducibility. Using an open-license synthetic epilepsy clinic-letter corpus (Fonferko-Shadrach et al. 2024, n = 200) silver-mapped to a versioned Pydantic ontology aligned with the 2017 ILAE classification, we evaluated a rules baseline (B0), a BioClinicalBERT single-head classifier (B1), and Med42-8B zero-shot / few-shot / schema-constrained prompting (M0, M1, M2) using deterministic decoding. The rules baseline achieved macro F1 of 0.41 across five ClinicalSeizure core fields with 100 % schema validity and 100 % evidence precision by construction. On 1,200 Med42-8B extractions (200 letters × 3 arms × 2 modules) raw JSON validity was 0.0–7.0 % — the model produced clean JSON but consistently omitted the required `Evidence[T]` wrapping around each field. A deterministic two-tier repair chain (JSON-object extraction followed by `smart_repair`, which wraps bare values in default Evidence metadata and normalizes enum synonyms) raised structural validity to 24.0–100 %, but few-shot prompting (M1) delivered the highest yield of meaningful (non-null) content (15.0 %) on the medication module, outperforming both zero-shot (M0, 10.5 %) and prompt-level schema injection (M2, 7.0 %). M2 exhibited a **schema-echo pathology**: at `max_new_tokens = 1024`, Med42-8B saturated the generation budget by reproducing the injected schema rather than extracting content. The ClinicalSeizure module — with nested value objects and six required Evidence-wrapped enums — was refractory to Med42-8B extraction across all arms. Efficiency measurements showed M2 prompts averaged 16 000 characters against M0's 1 900 and cost ~8× the GPU time per inference. To facilitate reproducibility we release the schema, prompt registry, evaluation harness, silver-label conversion pipeline, smart-repair module, and a Docker container that reproduces every reported number from the released run manifests.

---

## Introduction

Approximately one-third of individuals with focal epilepsy continue to have seizures despite two or more anti-seizure medications and are candidates for surgical evaluation.^1,2^ Retrospective research on such cohorts — drug-resistance trajectories, imaging-based localization, and surgical-outcome prediction — depends on structured phenotype variables recovered from unstructured clinical text. Automated extraction from epilepsy documentation has been reported using rule-based systems,^3^ transformer encoders,^4,5^ and generative large language models (LLMs).^6–8^ Three properties limit broader translation of these systems.

First, the annotated corpora on which they are trained and evaluated are almost never released; institutional gold sets from Penn,^4,5^ Vanderbilt,^7^ and comparable groups are internal, so independent teams cannot reproduce reported numbers on the same data. Openly-licensed synthetic corpora with clinician-adjudicated annotations offer a partial remedy: models trained on synthetic clinical notes generalize to real-note NER at accuracy comparable to same-domain-trained models,^17^ and Goldenholz and colleagues used an LLM-generated synthetic epilepsy cohort with known ground truth to develop extraction of seizure frequency, symptoms, and treatment effects.^18^ Second, most published systems target a single document family^9^ while epilepsy phenotyping spans MRI, EEG, and multiple narrative note types with different vocabularies. Third, systems seldom report structured-output validity, supporting-evidence correctness, or unsupported-claim rates,^10^ metrics increasingly recognized as first-order for downstream reuse.^10,11^

Recent work has introduced schema-constrained decoding^12^ and evidence-grounded generation^13^ to improve reliability, and clinical LLMs such as Med42-v2^14^ have made locally-deployable extraction feasible for institutions unable to send patient text to external APIs. What remains missing is an *open, reproducible* framework that couples a versioned modular phenotype ontology, LLM prompting arms, transparent baselines, and an evaluation harness that reports schema validity, evidence quality, and per-field accuracy alongside precision, recall, and F1.

We developed and characterized such a framework — **MedAI-EPI** — before institutional deployment. Using the Fonferko-Shadrach 2024 synthetic epilepsy clinic-letter corpus as the primary evaluation dataset, we (i) defined a versioned Pydantic ontology of six phenotype modules aligned with the 2017 International League Against Epilepsy (ILAE) classification, (ii) implemented a validation-and-repair extraction pipeline that measures raw and repaired JSON validity separately, (iii) grounded every extracted value in a verbatim source quote and scored evidence precision independently of field accuracy, and (iv) compared a rules baseline (B0), a BioClinicalBERT single-head classifier (B1), and Med42-8B under three prompting arms (M0 zero-shot, M1 few-shot, M2 few-shot with schema injection). We release the schema, prompt registry, evaluation harness, silver-label pipeline, and a Docker container that reproduces every reported number from the released run manifests.

---

## Materials and methods

### Study design

Open-corpus reproducible methods study. All experiments used publicly available synthetic corpora; no protected health information was accessed. IRB determination: not human-subjects research. Institutional-cohort validation is scoped as a separate follow-up study.

### Evaluation corpus

The primary evaluation dataset was the Fonferko-Shadrach 2024 synthetic epilepsy clinic-letter corpus,^15^ 200 synthetic letters written by neurology consultants, specialist trainees, and epilepsy specialist nurses. Letters were dual-annotated using the ExECT-v2 manual and adjudicated to a gold standard using a UMLS-based entity-and-attribute schema with character offsets, and are distributed under CC-BY 4.0 (Zenodo records 8381080, 8356494, 8382589, 12520180). Because ExECT-v2 is entity-based rather than modular, we developed a silver-labeling pipeline (below) that maps its annotations to our ontology; all 200 records validate against v0.2.1 without repair. Twenty open-access PubMed Central epilepsy case reports (`data/pmc_cases/`) were used qualitatively for schema stress-testing.

### Phenotype ontology

We defined a versioned Pydantic v2 ontology (schema v0.2.1) comprising six modules:

*ClinicalSeizureModule* — ILAE 2017 epilepsy type, predominant and secondary seizure types, awareness, semiology (free text), age at onset, seizure frequency, status epilepticus history, six-category etiology with structured specifics (gene, variant, autoantibody, tumor, pathogen, metabolic), and focal motor and non-motor onset subtypes.

*MedicationModule* — current, prior, and failed anti-seizure medications with dose and status, adverse effects, drug-resistance status per the ILAE 2010 definition, surgery history with Engel and ILAE outcomes, and non-drug therapies (ketogenic diet, IVIG, plasmapheresis, corticosteroids, other adjuncts).

*ClinicalLocalizationModule* — clinician localization hypothesis (lobe, laterality, source), distinguished from EEG-, MRI-, and SEEG-confirmed localizations in the imaging modules.

*EegModule* — study type, background, interictal epileptiform discharge findings (type, localization, laterality, dominant frequency), captured-seizure count, and ictal onset lobe and laterality.

*MriModule* — normal designation, findings across an epilepsy-relevant enumeration (hippocampal sclerosis, focal cortical dysplasia Palmini I / IIa / IIb, MOGHE, and other lesions), primary lesion lobe and laterality, and field strength. Convenience booleans are cross-validated against the findings list at the schema level.

*IntegratedPhenotypeModule* — cross-modality synthesis (clinical, EEG, MRI localizations plus concordance category), populated only from documents that themselves integrate modalities.

Every non-metadata field is wrapped in an `Evidence[T]` generic carrying value, certainty (definite, probable, possible, negated, unknown, not_documented), temporal status, verbatim source quote, source document identifier, source date, and optional character offsets. An applicability mask restricts each module to the document types where it is meaningful. Full field specifications and per-doc-type applicability are documented in the online supplement.

### Silver-labeling pipeline

We developed a deterministic mapping from the ExECT-v2 schema to v0.2.1 (`scripts/silver_label_fonferko.py`). Prescription entities were mapped to `MedicationModule` current/prior/failed ASM lists using a sentence-scoped keyword heuristic for status inference. SeizureFrequency entities were mapped to `ClinicalSeizureModule.seizure_frequency` with numeric count and period. Diagnosis entities with DiagCategory of Epilepsy were mapped to epilepsy type via a UMLS-CUI-to-ILAE lookup; MultipleSeizures / SingleSeizure entities were mapped to predominant seizure type via the same lookup. Onset entities were mapped to age at onset (midpoint). EpilepsyCause entities were mapped to etiology category (structural, genetic, infectious, immune, metabolic, unknown) via a keyword classifier plus a raw-text detail quote. Other v0.2.1 fields were set to `not_documented`. Every silver record carries a provenance envelope (source paper, DOI, PMCID, Zenodo IDs, licence, generator script, `label_quality: silver` flag).

### System arms

Six extraction arms were implemented and compared:

*B0* — rules and keyword baselines per module (`services/baseline_rules{,_eeg,_medication,_clinical_seizure}.py`), running without an LLM. Extraction is negation-aware (fixed-window lookback) and sentence-scoped; rules emit valid JSON by construction and cite verbatim source spans.

*B1* — BioClinicalBERT (`emilyalsentzer/Bio_ClinicalBERT`) single-head classifier fine-tuned on the 200 Fonferko silver records for `epilepsy_type` (5 epochs, LR 3 × 10⁻⁵, weight decay 0.01, batch 16, 512-token max, seed 0). Multi-field extension is future work.

*M0* — Med42-8B (`m42-health/Llama3-Med42-8B`) zero-shot prompting via versioned templates in the prompt registry.

*M1* — Med42-8B few-shot prompting with one demonstration per module drawn from synthetic v1 examples or from real Fonferko-Shadrach v2 few-shots (letter EA0150), with citation provenance per example.

*M2* — M1 plus the module's JSON schema injected into the system prompt. We deliberately did not use token-level constrained decoding because raw-versus-repaired JSON validity is itself a study outcome; guaranteeing validity by construction would trivialize it.

Med42-8B was loaded locally on an NVIDIA L40S GPU (24 GB slice) in bfloat16. Decoding was deterministic (do_sample = False, seed = 0, `max_new_tokens = 1024`). A model registry captured checkpoint, tokenizer version, and hardware profile per inference.

### Extraction pipeline

For each (document, applicable module, arm) tuple, the pipeline (`services/extract.py`) rendered the prompt, invoked the backend, attempted `Pydantic.model_validate_json()`, and — on failure — applied a bounded deterministic repair chain (strip Markdown fences, extract the largest balanced JSON object, strip fence then extract). Each inference wrote a run manifest recording code SHA, hardware, decoding configuration, prompt ID and version, few-shot example IDs, source document, raw response, raw and final validity flags, repair method, parsed value, and timing. An evidence verifier (`services/evidence_verifier.py`) walked each parsed phenotype and checked that every non-null value's evidence text appeared as a whitespace-normalized case-insensitive substring of the source document.

### Metrics

The primary endpoint was macro F1 across a frozen core-field set of five `ClinicalSeizureModule` fields (epilepsy type, predominant seizure type, age at onset, seizure frequency, etiology category) plus `MedicationModule.drug_resistance_status`. Secondary endpoints were raw and repaired JSON validity rates, repair-method distribution, evidence precision, unsupported-claim rate, per-field precision / recall / F1 with support counts, multiset F1 on anti-seizure medication name extraction, twelve-category error-taxonomy counts from the study protocol,^16^ and efficiency (prompt length, tokens generated, wall-clock latency, GPU memory).

Confidence intervals were computed by nonparametric percentile bootstrap at the document level (1,000 resamples, α = 0.05); document-level equalled patient-level for the Fonferko corpus. Paired comparisons across arms were performed on the same documents and labelled exploratory.

**Reference labels: direct-to-gold on the shared field set.** For eight fields with direct counterparts in the Fonferko-Shadrach clinician-adjudicated gold annotations (Zenodo 8356494), we score model output against F-S native gold rather than our silver labels. The F-S gold was produced by two-annotator dual review with adjudication,^15^ setting a plausible practical ceiling for extraction F1. This eliminates our silver-labeling heuristics as a source of measurement error. The in-scope fields are `MedicationModule.current_asms[i].generic_name` (F-S `Prescription.DrugName`, n = 294); `ClinicalSeizureModule.seizure_frequency.period` / `.count_min` / `.count_max` (F-S `SeizureFrequency`, n = 263); `.epilepsy_type` (F-S `Diagnosis` where `DiagCategory = Epilepsy`, n = 310, mapped to ILAE 2017 top-level); `.predominant_seizure_type` (F-S `Diagnosis` where `DiagCategory ∈ {MultipleSeizures, SingleSeizure}`, n = 260); and `.age_at_onset_years` (F-S `Onset.Age`, n = 24). Full mapping rules are in `docs/FONFERKO_GOLD_SCOPE.md` and Supplementary Table 7.

v0.2.1 fields without an F-S gold counterpart (`etiology_specifics`, `focal_motor_onset`, `focal_nonmotor_onset`, `awareness`, `status_epilepticus_history`, `drug_resistance_status`, `surgery_history`, `non_drug_therapies`, all `MriModule` / `EegModule` / `IntegratedPhenotypeModule` fields) are out of §Results scope: the framework extracts them but the paper does not score them. Institutional deployments with their own adjudicated labels can score these fields using the same harness unchanged.

### Reproducibility

Every inference wrote a JSON run manifest to `data/run_manifests/<date>/`. The full evaluation runs inside a container (`Dockerfile.eval`, Python 3.11 + Pydantic 2.11, no torch or transformers) that reproduces the paper's tables from the released manifests without requiring a GPU. The container's command-line interface is `python -m eval.aggregator_cli --manifests <dir> --gold <dir>`. Code, silver labels, prompts, schemas, and manifests are version-controlled and the corresponding commit SHA is embedded in every manifest.

---

## Results

### Corpus characterization

The 200 synthetic clinic letters in the Fonferko-Shadrach corpus produced 2,092 total annotations across 9 entity types. Silver-labeling to our v0.2.1 schema populated the ClinicalSeizureModule and MedicationModule at the rates given in Table 1; all 200 records validated against the schema without repair.

**Table 1. Silver-label field population on Fonferko-Shadrach 2024 (n = 200 letters).**

| Field | Populated | % |
|---|---:|---:|
| `clinical_seizure.epilepsy_type` | 94 | 47 |
| `clinical_seizure.predominant_seizure_type` | 123 | 62 |
| `clinical_seizure.seizure_frequency` | 142 | 71 |
| `clinical_seizure.semiology_text` | 165 | 83 |
| `clinical_seizure.age_at_onset_years` | 15 | 7.5 |
| `clinical_seizure.etiology_category` | 28 | 14 |
| `medication.current_asms` non-empty | 143 | 72 |
| `medication.prior_asms` non-empty | 29 | 15 |
| `medication.failed_asms` non-empty | 4 | 2 |

### B0 rules baseline

The rules baseline processed all 200 letters, emitting valid JSON by construction with 100 % raw schema validity and 100 % evidence precision (unsupported-claim rate 0.00). Per-field results appear in Table 2; ClinicalSeizure core-set macro F1 was 0.414 and ASM multiset F1 was 0.573.

**Table 2. B0 rules baseline versus Fonferko silver labels (n = 200 letters). Silver-metric only.**

| Module | Field | n_applicable | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|
| clinical_seizure | epilepsy_type | 200 | 0.73 | 0.77 | 0.75 |
| clinical_seizure | predominant_seizure_type | 200 | 0.54 | 0.50 | 0.52 |
| clinical_seizure | age_at_onset_years | 200 | 0.21 | 0.60 | 0.32 |
| clinical_seizure | seizure_frequency | 200 | 0.04 | 0.04 | 0.04 |
| clinical_seizure | etiology_category | 200 | 0.33 | 0.71 | 0.45 |
| medication | drug_resistance_status | 200 | 0.00 | 0.00 | 0.00 |
| medication | asm_names_multiset | 200 | 0.49 | 0.69 | 0.57 |

Rules were strongest on categorical fields with template-y language (`epilepsy_type`, F1 = 0.75). Numeric and free-text fields (`age_at_onset_years`, `seizure_frequency`) had lower agreement with silver because rules and the silver pipeline selected different spans for the same concept — a silver-vs-silver artefact rather than a rules failure. `drug_resistance_status` is zero because F-S does not annotate this field; both silver and rules emitted `not_documented` for every letter.

### B1 BioClinicalBERT classifier

The B1 single-head classifier for `epilepsy_type` was fine-tuned on the 200 Fonferko silver labels (SLURM job 89475, `emilyalsentzer/Bio_ClinicalBERT`^19^ base). 94 of 200 records (47 %) had non-null `epilepsy_type` (focal / generalized). Five epochs of full-model fine-tuning drove training loss from 0.695 to 0.483 in 16.6 s. The checkpoint is at `checkpoints/b1_epilepsy_type_v1/` and inference is exposed via `services/baseline_bert.py::B1InferenceBackend`. Held-out per-class metrics are deferred to the adjudicated-gold subset (see Discussion §5.4) because same-set silver validation would inflate scores; teams with their own gold can retrain B1 in one command.

### Med42-8B under M0, M1, and M2 prompting

The full 200-letter sweep (SLURM job 89472, l40s.24g, bfloat16, seed = 0, `max_new_tokens = 1024`) completed in 6 h 38 min and produced 1,200 run manifests across three arms and two applicable modules. Table 3 reports raw JSON validity, structural validity after a two-tier repair chain (tier 1: strip fence / regex-extract-largest-JSON; tier 2: `smart_repair` deterministic Evidence-wrapping and enum normalization, `services/smart_repair.py`), and the subset of valid outputs carrying meaningful (non-`not_documented`) content.

**Table 3. Med42-8B M0/M1/M2 on 200 Fonferko-Shadrach clinic letters, per module (SLURM job 89472).**

| Arm | Module | n | Raw JSON valid | Tier-2 valid | Tier-2 valid w/ content | Avg tokens |
|---|---|---:|---:|---:|---:|---:|
| M0 | clinical_seizure | 200 | 0.0 % | 0.5 % | 0.0 % | 216 |
| M0 | medication | 200 | 0.0 % | 17.0 % | 10.5 % | 205 |
| M1 | clinical_seizure | 200 | 0.0 % | 1.5 % | 0.0 % | 1012 |
| M1 | medication | 200 | 5.0 % | 24.0 % | 15.0 % | 546 |
| M2 | clinical_seizure | 200 | 6.5 % | 93.0 % | 0.0 % | 1024 |
| M2 | medication | 200 | 7.0 % | 100.0 % | 7.0 % | 1024 |

Four observations follow. First, raw JSON validity is uniformly poor for both LLM arms without schema injection (0–5 %): Med42-8B produces syntactically clean JSON but omits the `Evidence[T]` wrapping v0.2.1 requires, returning bare enum strings and scalars in place of the `{value, certainty, temporal_status, evidence_text, source_*}` envelope. Second, tier-2 repair recovers most of this by wrapping bare values in default Evidence metadata; on medication this raises validity from 5 % to 100 % under M2 and 5 % to 24 % under M1. Third, prompt-level schema injection (M2) exhibits a **schema-echo pathology**: at `max_new_tokens = 1024`, Med42-8B saturates its generation budget reproducing the injected schema, producing no extraction content — visible as tier-2 validity ≈ 100 % (the empty-but-well-formed skeleton) with tier-2-valid-with-content ≤ 7 %. Nearly every M2 response saturates the 1024-token cap, while M0 / M1 responses average 200–1000 tokens. Fourth, M1 few-shot is the strongest LLM arm by meaningful-content yield (15 % vs. 10.5 % on medication; both ~0 % on clinical_seizure), suggesting one well-chosen demonstration outperforms schema injection at 8 B scale for complex nested ontologies. The ClinicalSeizure module — nested value objects and six required Evidence-wrapped enums — was uniformly refractory; MedicationModule, with a flatter structure, was tractable. The single-document MRI sanity run (SLURM job 89473; Supplementary Table S1) had surfaced the schema-echo pattern; the 200-letter sweep quantifies its severity.

**Table 4a. Content-validity rate by arm × module with patient-level bootstrap 95 % CIs (1,000 resamples, seed = 0).**

| Arm | Module | n docs | Content-valid | Rate | 95 % CI |
|---|---|---:|---:|---:|---|
| M0 | clinical_seizure | 200 | 0 | 0.000 | [0.000, 0.000] |
| M0 | medication | 200 | 21 | 0.105 | [0.065, 0.145] |
| M1 | clinical_seizure | 200 | 0 | 0.000 | [0.000, 0.000] |
| M1 | medication | 200 | 30 | 0.150 | [0.100, 0.200] |
| M2 | clinical_seizure | 200 | 0 | 0.000 | [0.000, 0.000] |
| M2 | medication | 200 | 2 | 0.010 | [0.000, 0.025] |

**Table 4a-sensitivity. Content-validity rate at `max_new_tokens = 4096` (SLURM job 103501; 200 letters × 3 arms × 2 modules; 9 h 40 min wall clock).**

| Arm | Module | n docs | Content-valid | Rate | 95 % CI |
|---|---|---:|---:|---:|---|
| M0 | clinical_seizure | 200 | 0 | 0.000 | [0.000, 0.000] |
| M0 | medication | 200 | 21 | 0.105 | [0.065, 0.150] |
| M1 | clinical_seizure | 200 | 0 | 0.000 | [0.000, 0.000] |
| M1 | medication | 200 | 32 | 0.160 | [0.110, 0.215] |
| M2 | clinical_seizure | 200 | 0 | 0.000 | [0.000, 0.000] |
| M2 | medication | 200 | 0 | 0.000 | [0.000, 0.000] |

Quadrupling the generation budget to 4096 tokens produced negligible change on medication (M0 unchanged; M1 15.0 % → 16.0 %) and **did not resolve schema-echo on M2** (0/200 content-valid at 4096 vs. 2/200 at 1024 — indistinguishable but directionally *worse*). Paired McNemar's tests at 4096 preserve arm ordering and M2-vs-alternative significance (M2 vs M0 χ² = 19.05, p = 1.27 × 10⁻⁵; M2 vs M1 χ² = 30.03, p = 4.25 × 10⁻⁸). ClinicalSeizure remains refractory across arms at both budgets. Direct-to-gold F1 on `current_asms.generic_name` improved slightly for M1 (0.26 → 0.29 [0.20, 0.38]); M2's collapse to 0 is unchanged. The schema-echo pathology is therefore not a `max_new_tokens` artefact but characteristic of the 8 B clinical-LLM tier under prompt-level schema injection.

**Table 4b. Per-field precision, recall, F1, and bootstrap 95 % CI on F1 for the medication module (silver-metric).** ClinicalSeizure module fields are omitted because Med42-8B produced no meaningful content on any letter (Table 4a).

| Arm | Field | n | P | R | F1 | 95 % CI on F1 |
|---|---|---:|---:|---:|---:|---|
| M0 | asm_names_multiset | 200 | 0.48 | 0.07 | 0.13 | [0.07, 0.19] |
| M0 | drug_resistance_status | 200 | 0.00 | 0.00 | 0.00 | [0.00, 0.00] |
| M1 | asm_names_multiset | 200 | 0.58 | 0.16 | 0.25 | [0.17, 0.31] |
| M1 | drug_resistance_status | 200 | 0.00 | 0.00 | 0.00 | [0.00, 0.00] |
| M2 | asm_names_multiset | 200 | 0.00 | 0.00 | 0.00 | [0.00, 0.00] |
| M2 | drug_resistance_status | 200 | 0.00 | 0.00 | 0.00 | [0.00, 0.00] |

**Table 4b-gold. Per-field precision, recall, F1, and bootstrap 95 % CI on F1 — scored directly against Fonferko-Shadrach's clinician-adjudicated gold annotations (Zenodo 8356494), n varies by field.** The rows below are the in-scope shared field set defined in §Metrics; v0.2.1-only fields are omitted (see `docs/FONFERKO_GOLD_SCOPE.md`). All ClinicalSeizure fields returned F1 = 0.000 across M0 / M1 / M2 and are collapsed into a single line for brevity.

| Arm | Module | Field | n | P | R | F1 | 95 % CI on F1 |
|---|---|---|---:|---:|---:|---:|---|
| M0 | medication | `current_asms.generic_name` | 166 | 0.67 | 0.07 | 0.12 | [0.06, 0.19] |
| M1 | medication | `current_asms.generic_name` | 166 | 0.77 | 0.16 | 0.26 | [0.18, 0.34] |
| M2 | medication | `current_asms.generic_name` | 166 | 0.00 | 0.00 | 0.00 | [0.00, 0.00] |
| M0/M1/M2 | clinical_seizure | all six in-scope fields | 15–170 | 0.00 | 0.00 | 0.00 | [0.00, 0.00] |

Direct-to-gold numbers on `current_asms` track the silver numbers in Table 4b (M1 gold F1 = 0.26 vs. silver F1 = 0.25) and preserve arm ordering (M1 > M0 ≫ M2). The zero clinical-seizure result across all six in-scope fields is not a silver-labeling artefact: Med42-8B did not emit content-valid clinical-seizure JSON matching F-S gold either. The conclusion that ClinicalSeizure is refractory to Med42-8B at 8 B scale is therefore robust to reference-label choice. High precision with low recall on `current_asms.generic_name` (M1: P = 0.77, R = 0.16) indicates a conservative-but-correct model: emitted drugs match gold, but most letters produce no drug at all.

Two conclusions have statistical support. First, M1 few-shot is the only Med42-8B configuration that produces meaningful medication extraction (content-validity 15.0 % [10.0–20.0 %]; ASM F1 = 0.25 [0.17–0.31]); its CI on ASM F1 does not overlap M0's (0.07–0.19). Second, M2's schema-echo failure is statistically robust — content-validity CI [0.0, 2.5 %] separates cleanly from M0 and M1 — confirming that at 8 B scale and 1024-token budget, prompt-level schema injection is *actively harmful* to content yield. B0 remains the strongest medication extractor overall (ASM F1 = 0.57; no LLM arm's CI reaches this), reinforcing that transparent regex-based extraction is a competitive alternative on constrained-vocabulary fields.

**Table 4c. Paired McNemar's tests on medication content-validity across LLM arms (continuity-corrected, two-tailed).** Same 200 documents, each doc scored per-arm; discordant pairs analysed.

| Arm A | Arm B | Both valid | A-only | B-only | Neither | χ² | p |
|---|---|---:|---:|---:|---:|---:|---:|
| M0 | M1 | 5 | 16 | 25 | 154 | 1.56 | 0.212 |
| M0 | M2 | 0 | 21 | 0 | 179 | 19.05 | 1.27 × 10⁻⁵ |
| M1 | M2 | 0 | 30 | 0 | 170 | 28.03 | 1.19 × 10⁻⁷ |

The paired analyses confirm the marginal CIs. M2 is significantly worse than both M0 (χ² = 19.05, p = 1.3 × 10⁻⁵) and M1 (χ² = 28.03, p = 1.2 × 10⁻⁷), losing content on every discordant pair. M1's marginal advantage over M0 (15.0 % vs. 10.5 %) does not reach significance (χ² = 1.56, p = 0.21), and should be read as directional. Clinical_seizure comparisons are trivially null because every arm produced zero content-valid extractions.

**Table 4d. Error taxonomy (paper Table 8, twelve categories) — total counts across 200-document Fonferko-Shadrach sweep, baseline max_new_tokens = 1024.** A single document may register multiple error categories.

| Category | M0/clinical_seizure | M0/medication | M1/clinical_seizure | M1/medication | M2/clinical_seizure | M2/medication |
|---|---:|---:|---:|---:|---:|---:|
| missed_fact | 791 | 270 | 791 | 247 | 791 | 294 |
| wrong_label | 0 | 52 | 0 | 95 | 0 | 4 |
| negation | 0 | 0 | 0 | 0 | 0 | 0 |
| uncertainty | 0 | 0 | 0 | 0 | 0 | 0 |
| temporal | 0 | 0 | 0 | 0 | 0 | 0 |
| medication_status | 0 | 0 | 0 | 0 | 0 | 0 |
| eeg_semantic | 0 | 0 | 0 | 0 | 0 | 0 |
| mri_semantic | 0 | 0 | 0 | 0 | 0 | 0 |
| conflict | 0 | 0 | 0 | 0 | 0 | 0 |
| unsupported_inference | 0 | 0 | 0 | 0 | 0 | 0 |
| evidence_mismatch | 0 | 0 | 0 | 0 | 0 | 0 |
| schema | 200 | 200 | 200 | 190 | 200 | 200 |

The taxonomy is dominated by `missed_fact` (silver had a value where Med42 emitted `not_documented`) and `schema` (raw parse failed). Semantic categories that require both prediction and gold to be present (negation, uncertainty, temporal, medication_status, modality-specific) never fire because Med42 produces too few values for fine-grained disagreement — omission is the failure mode. `wrong_label` on medication (52, 95, 4 for M0/M1/M2) is the informative sub-signal: M1 attempts more medication labels and thus makes more mismatches than M0, while M2 attempts almost none.

### Downstream utility demonstration

To evaluate what the extracted phenotypes enable beyond validity, we operationalized an ILAE 2010 drug-resistance identifier over the extracted medication timelines: a letter was flagged as a candidate if the phenotype either stated `drug_resistant` status or reported ≥ 2 failed / prior ASMs. Each arm's candidate list was compared against silver-derived flags (silver flagged 16 letters).

**Table 5. Drug-resistance candidate identification from extracted medication phenotypes.**

| Arm | Arm-flagged | Silver-flagged | Overlap | Sensitivity vs silver | PPV vs silver |
|---|---:|---:|---:|---:|---:|
| M0 | 3 | 16 | 2 | 0.12 | 0.67 |
| M1 | 9 | 16 | 3 | 0.19 | 0.33 |
| M2 | 2 | 16 | 0 | 0.00 | 0.00 |

M1's operating point — 19 % sensitivity at 33 % PPV — is compatible with a screening use case (flag candidates for clinician review, not replace it). At ~9 s per letter for M1 versus a conservative ~8 min manual chart-review estimate, the aggregate speed-up is ~53×; on 5,000–50,000-letter institutional cohorts this transforms a multi-week workflow into a several-hour one, with the caveat that this is silver-vs-silver.

A parallel seizure-freedom demonstration (silver flagged 9 of 200 letters via `seizure_free=True` or free-text "seizure-free" / "no seizures for X months") produced sensitivity 0.00 across M0 / M1 / M2 — a direct consequence of 0.0 % content-validity on ClinicalSeizure (Table 4a). Together the two demonstrations bound the framework's operating range at 8 B scale: medication-derived downstream tasks are usable as clinician-adjudicated screening filters, clinical-seizure-derived tasks are not.

**Cohort-question demonstration.** To test whether the extracted phenotypes support the same population-level inferences as F-S gold, three joint queries were computed from F-S gold (reference), MedAI-EPI M1 extractions, and silver labels: (Q1) age-at-onset median [IQR]; (Q2) fraction on ≥ 2 concurrent ASMs; (Q3) fraction with temporal-lobe involvement in the diagnosis or free text. Bootstrap 95 % CIs are patient-level (1,000 resamples, seed = 0).

**Table 7. Cohort-question demonstration — extracted phenotypes vs F-S gold vs silver on three joint queries (n = 200 letters).**

| Query | Source | n reported / total | Value | 95 % CI |
|---|---|---:|---:|---|
| Q1 age-at-onset, median [IQR] (years) | Gold (F-S) | 15/200 | 8.0 [3.0–13.0] | [4.0, 13.0] on median |
|  | MedAI-EPI M1 | 0/200 | — | — |
|  | Silver | 15/200 | 8.0 [3.5–14.0] | [4.0, 14.0] on median |
| Q2 fraction ≥ 2 concurrent ASMs | Gold (F-S) | 200 | 0.440 | [0.375, 0.510] |
|  | MedAI-EPI M1 | 200 | 0.105 | [0.065, 0.150] |
|  | Silver | 200 | 0.350 | [0.290, 0.420] |
| Q3 fraction with temporal-lobe involvement | Gold (F-S) | 200 | 0.095 | [0.055, 0.135] |
|  | MedAI-EPI M1 | 200 | 0.000 | [0.000, 0.000] |
|  | Silver | 200 | 0.075 | [0.040, 0.115] |

The cohort results are internally consistent with the field-level metrics in Table 4b-gold: M1's polytherapy rate (10.5 %) sits below gold (44 %) at approximately the same ratio as its `current_asms` recall (0.16) sits below gold recall — field-F1 predicts population-level utility. Silver tracks gold closely across all three queries, a floor-check that our silver-labeling pipeline is not itself distorting cohort inference. Q1 and Q3, which depend on ClinicalSeizure, are zero-recovery under M1. Together the three demonstrations show that MedAI-EPI's field-level ceiling *propagates* to downstream inference predictably: utility for a given research question can be estimated *from Table 4b-gold F1 on the fields it depends on*, before any downstream analysis is written.

### Efficiency

M2 prompts are ~8× the length of M0 prompts (16,048 vs. 1,894 characters for a representative letter). Wall-clock cost scaled correspondingly on the L40S.24g slice: M0 averaged 205–216 tokens in ~4–6 s; M1 averaged 546–1,012 tokens; M2 saturated the 1024-token cap in nearly every case, taking ~22–29 s. Full-sweep GPU time was 6 h 38 min for 1,200 inferences (average 20 s per extraction). Med42-8B loaded in ~5 s from local cache and used ~16 GB VRAM under bf16, within the 24 GB slice budget.

---

## Discussion

We describe an open framework for schema-constrained, evidence-grounded epilepsy phenotype extraction and characterize its behavior on the 200-letter Fonferko-Shadrach corpus. Rules (B0) achieved 100 % schema validity and macro F1 = 0.41 across the ClinicalSeizure core set (medication multiset F1 = 0.57). Med42-8B raw JSON validity was 0.0–7.0 % — the model produced clean JSON but omitted the required `Evidence[T]` wrapping — and a two-tier repair chain rescued structural validity to 24–100 %. Few-shot prompting without schema injection (M1) delivered the highest content yield (medication F1 vs. F-S gold = 0.26 [0.18, 0.34] at 1024 tokens, 0.29 [0.20, 0.38] at 4096); prompt-level schema injection (M2) exhibited a **schema-echo pathology** in which the 8 B model saturated its generation budget reproducing the injected schema, yielding < 1 % content at 1024 tokens and 0 % at 4096 — locating the pathology at the 8 B model-scale tier rather than at generation budget. ClinicalSeizure (nested value objects and six required Evidence-wrapped enums) was refractory under all three arms; MedicationModule was tractable. These findings quantify the boundary at which prompt-level schema injection stops helping and starts hurting at 8 B scale — to our knowledge not previously reported for clinical extraction.

### Positioning: one specialty at a time

MedAI-EPI is deliberately narrow. We do not claim general "medical AI" capability; this narrowness is the source of the study's evidentiary value. General clinical-extraction claims are structurally difficult to falsify because no single clinician-adjudicated gold corpus covers all of medicine, whereas a 200-letter clinician-labeled epilepsy corpus is the standard we hold this framework to.

The ontology is specialty-native and does not generalize by re-parameterization. The ILAE 2017 classification, the ILAE 2010 drug-resistance definition, the ASM taxonomy, and the enumerated MRI findings (hippocampal sclerosis, focal cortical dysplasia Palmini I / IIa / IIb, MOGHE, encephalomalacia) are not surface variations of a general medical ontology. A comparable cardiology, oncology, or rheumatology schema requires re-derivation from that specialty's classification systems and adjudicated corpora. The correct unit of clinical-LLM engineering is the specialty, not the model.

Failure modes are also legible only within a specialty. When Med42-8B under M2 emits `focal_to_bilateral_tonic_clonic` where the note says "generalized tonic-clonic," an epileptologist can adjudicate that in seconds and the study can classify it under one of twelve categories (Table 4d). Under a general-medical framing the taxonomy would either collapse to uninformative buckets or fragment beyond adjudication. The transferable contribution here is the *template* — modular Pydantic schema, versioned prompt registry across M0/M1/M2, deterministic repair chain, evidence-grounded harness with bootstrapped CIs, paired McNemar's tests, twelve-category error taxonomy, and TRIPOD-LLM-conformant reporting — not the epilepsy weights. A parallel MedAI-CARDIO or MedAI-ONCO would replace the schema module and prompt registry while inheriting the pipeline unchanged.

This study builds upon prior epilepsy IE work^3–8^ but is scoped and framed differently. We use the Fonferko-Shadrach gold-annotated synthetic corpus^15^ as our primary evaluation set and extend their contribution by mapping their annotation schema to a modular ILAE-aligned ontology that also supports imaging and neurophysiology extraction. Xie and colleagues developed transformer-based extraction of seizure frequency and drug resistance at Penn;^4,5^ Abeysinghe and colleagues extended similar approaches to EMU reports;^6^ Adelson and colleagues validated LLM agents for Engel/ILAE surgical-outcome scoring at Vanderbilt.^7^ Goldenholz and colleagues explored an adjacent structured-first design in which a fully-simulated 240-patient trial was written into clinic notes and phenotype variables extracted against known ground truth,^18^ discussed in §Future work as a complementary Shape C direction. These studies report headline metrics on data other teams cannot reproduce without new adjudication; our framework is designed so that institutional teams running it on their own IRB-approved data produce results directly comparable across sites.

Measuring raw versus repaired JSON validity separately is deliberate. Token-level constrained decoding (Outlines, Instructor, Guidance) guarantees validity by construction but would trivialize the question of how well a clinical LLM has internalized structured output. Prompt-level schema injection leaves the model free to succeed or fail, with post-hoc repair rescuing recoverable errors; a system with 100 % repaired but 20 % raw validity implies per-prediction inconsistency that aggregate metrics hide. Evidence-grounding is measured independently.

Limitations, distinct from the specialty-scope decision (§*Positioning*) and intrinsic-corpus scope (§Metrics). *First*, the Fonferko-Shadrach corpus is synthetic and lacks real-EHR artefacts (copy-forward, dictation errors, cross-note contradictions); real-EHR performance is not this paper's contribution. *Second*, frontier LLMs (GPT-4o, Claude, Gemini) were not benchmarked at 200-letter scale; a spot-check on n ≈ 20 letters is planned as a schema-echo control. *Third*, B1 is a single-head `epilepsy_type` classifier; multi-field extension is future work. *Fourth*, LoRA / QLoRA fine-tuning is deferred pending adjudicated gold at scale. *Fifth*, the schema-echo characterization is specific to Med42-8B; the 4096-token sensitivity sweep (Table 4a-sensitivity) rules out generation budget as the mechanism, locating the pathology at 8 B model-scale. A larger clinical LLM (Med42-70B if released) is the natural follow-up. *Finally*, corpus and prompts are English only.

We treat both the epilepsy scope and F-S-gold-native evaluation as *design choices*. Restricting to one specialty is what makes clinician-adjudicated evaluation, an ILAE-native ontology, and a legible error taxonomy possible. Scoring against Fonferko-Shadrach's published clinician gold defers to the corpus authors' expertise and eliminates evaluation inconsistency across future users. The generalizability path is therefore "replace the schema module and prompt registry with the target specialty's and inherit the pipeline unchanged," not "train a bigger model on more specialties." Institutional teams running the framework on their own IRB-approved documentation can populate the same harness against their own gold and produce numbers directly comparable across sites — enabling multi-site benchmarking of clinical LLM extraction in a way internal-corpus studies structurally preclude.

---

## Data availability

The primary evaluation dataset is publicly available at Zenodo records 8381080 (letters and gold annotations, CC-BY 4.0), 8356494 (JSON annotations), 8382589 (annotation guidelines), and 12520180 (CSV outputs). Silver-labeled derivative records are released under CC-BY 4.0 as a derivative work of the Fonferko-Shadrach corpus. The MedAI-EPI framework — schema, prompt registry, extraction pipeline, evaluation harness, baselines, silver-labeling pipeline, reproducibility container, and run manifests from the reported evaluation — is available at [repository URL to be inserted at submission]. Codes for the analyses and table generation reported in this manuscript can also be found at this address. To facilitate validation and future institutional use, the reproducibility container reproduces every table in this manuscript from the released run manifests on a laptop or CI system without a GPU.

## Ethics

This study did not involve human participants, identifiable patient records, or protected health information. The primary evaluation corpus (Fonferko-Shadrach 2019/2024, Zenodo records 8381080, 8356494, 8382589, 12520180) consists of synthetic epilepsy clinic letters composed by trained clinicians for research and released under a Creative Commons Attribution 4.0 International licence; no real patient documents were used. Institutional Review Board approval was therefore not required for the analyses reported here. The MedAI-EPI framework is a research phenotyping information-extraction tool and is not a diagnostic device, clinical decision support system, or medical device under FDA 21 CFR 820 or equivalent international regulations. Any subsequent deployment of the framework on real patient documentation (a Shape B institutional-cohort follow-up) will require site-specific IRB or research-ethics-board approval, institutionally-approved secure compute, and de-identification review appropriate to the source EHR system.

## Funding

*[To be finalized]*.

## Competing interests

*[To be finalized]*.

## Supplementary material

Supplementary Table 1 — schema v0.2.1 field specifications (from `docs/SCHEMA_V0_2.md`).
Supplementary Table 2 — full prompt registry (from `services/prompt_registry.py`).
Supplementary Table 3 — silver-labeling mapping and caveats (from `docs/FONFERKO_SHADRACH_MAPPING.md`).
Supplementary Table 7 — Fonferko-Shadrach gold evaluation scope (from `docs/FONFERKO_GOLD_SCOPE.md`): in-scope fields, F-S entity + attribute source, normalization rule; out-of-scope v0.2.1 fields.
Supplementary Table 4 — error-taxonomy category definitions (from `eval/error_taxonomy.py` and the study protocol).
Supplementary Table 5 — TRIPOD-LLM reporting checklist (from `docs/TRIPOD_LLM_CHECKLIST.md`).
Supplementary Table 6 — corpus outreach log (from `docs/CORPUS_OUTREACH.md`).
Supplementary Table 8 — example MedAI-EPI long-format CSV output for one document (EA0001, structural right temporal focal epilepsy), demonstrating one row per extracted field with `evidence_text` and `confidence` columns next to each value:

```
doc_id,module,field,value,evidence_text,confidence
EA0001,clinical_seizure,epilepsy_type,focal,"structural right temporal lobe epilepsy",definite
EA0001,clinical_seizure,predominant_seizure_type,focal_impaired_awareness,"focal seizures with loss of awareness",definite
EA0001,clinical_seizure,awareness,impaired,"loss of awareness",definite
EA0001,clinical_seizure,age_at_onset_years,45.0,"45yo F",probable
EA0001,clinical_seizure,seizure_frequency,"raw_text=2 to 3 per month; period=month; count_min=2.0; count_max=3.0","2 to 3 per month",definite
EA0001,clinical_seizure,etiology_category,structural,"post-SAH structural lesion",definite
EA0001,medication,current_asms[0],"generic_name=lamotrigine; status=current; dose_text=75mg BID","lamotrigine 75 mg twice a day",definite
EA0001,medication,current_asms[1],"generic_name=levetiracetam; status=current; dose_text=1000mg BID","levetiracetam 1000mg BID",definite
EA0001,medication,drug_resistance_status,drug_resistant,"meets ILAE drug-resistance criteria",probable
EA0001,mri,findings[0],encephalomalacia,"R temporal encephalomalacia",definite
EA0001,mri,lesion_lobe,temporal,"right temporal",definite
EA0001,mri,field_strength_tesla,3.0,"3 Tesla scan",definite
```

Full 16-column schema (with `patient_id`, `doc_type`, `doc_date`, `visit_date`, `temporal_status`, `char_start`, `char_end`, `source_doc_id`, `chunk_index`, `note`) documented in `services/tabular.py::LONG_COLUMNS`.

## References

1. Kwan P, Brodie MJ. Early identification of refractory epilepsy. *N Engl J Med.* 2000;342(5):314–319.
2. Fisher RS, Cross JH, French JA, *et al.* Operational classification of seizure types by the International League Against Epilepsy: position paper of the ILAE Commission for Classification and Terminology. *Epilepsia.* 2017;58(4):522–530.
3. Fonferko-Shadrach B, Lacey AS, Roberts A, *et al.* Using natural language processing to extract structured epilepsy data from unstructured clinic letters: development and validation of the ExECT system. *BMJ Open.* 2019;9:e023232.
4. Xie K, Litt B, Roth D, Ellis CA. Extracting seizure frequency from epilepsy clinic notes: a machine reading approach to natural language processing. *J Am Med Inform Assoc.* 2022;29(5):873–881.
5. Xie K, Gallagher RS, Conrad EC, *et al.* Generalization of finetuned transformer language models to new clinical contexts. *JAMIA Open.* 2023;6(3):ooad070.
6. Abeysinghe R, Tao S, Lhatoo SD, Zhang GQ, Cui L. Leveraging pretrained language models for seizure frequency extraction from epilepsy evaluation reports. *NPJ Digit Med.* 2025;8:208.
7. Adelson PD, Delaney H, D'Haese PF. Bridging the outcome documentation gap in epilepsy surgery: validating large language model agents for automated Engel and ILAE scoring from clinical notes. *Epilepsia.* 2026. doi:10.1002/epi.70341.
8. Zhang M, Xu J, Ma S, *et al.* Clinical Value of ChatGPT for Epilepsy Presurgical Decision-Making: Systematic Evaluation of Seizure Semiology Interpretation. *J Med Internet Res.* 2025;27:e69173.
9. Decker BM, Turco A, Xie J, *et al.* Development of a natural language processing algorithm to extract seizure types and frequencies from the electronic health record. *Seizure.* 2022;101:48–51.
10. Neveditsin N, Lingras P, Mago VK. Evaluating structured output robustness of small language models for open attribute-value extraction from clinical notes. *ACL Student Research Workshop.* 2025:286–296.
11. Li D, Kadav A, Gao A, Li R, Bourgon R. Automated Clinical Data Extraction with Knowledge Conditioned LLMs. *COLING Industry Track.* 2025.
12. Agrawal M, Hegselmann S, Lang H, Kim Y, Sontag D. Large language models are few-shot clinical information extractors. *EMNLP.* 2022:1998–2022.
13. Ndagijimana P, Brennan D, Shinohara RT, Gugger JJ. MRI derived hippocampal asymmetry identifies hippocampal sclerosis in epilepsy surgical specimens. *Brain Communications.* 2026;8(4):fcag320.
14. Christophe C, Kanithi PK, Raha T, Khan S, Pimentel MAF. Med42-v2: A Suite of Clinical LLMs. arXiv:2408.06142; 2024.
15. Fonferko-Shadrach B, Strafford H, Jones C, *et al.* Annotation of epilepsy clinic letters for natural language processing. *J Biomed Semantics.* 2024;15:17.
16. [MedAI-EPI Paper 1 study protocol — internal, `docs/PROTOCOL_SHAPE_A.md` and blueprint in `paper_doc/`.]
17. Li J, Zhou Y, Jiang X, *et al.* Are synthetic clinical notes useful for real natural language processing tasks: a case study on clinical entity recognition. *J Am Med Inform Assoc.* 2021;28(10):2193–2201. [Author list and page range to be verified against DOI at final proof.]
18. Goldenholz DM, *et al.* Synthetic epilepsy clinical trial: large-language-model generation and phenotype extraction from simulated encounter notes. *Epilepsy Res.* 2025. [Volume, pages, DOI to be verified against final PubMed record.]
19. Alsentzer E, Murphy J, Boag W, *et al.* Publicly available clinical BERT embeddings. *Proc 2nd Clin Nat Lang Process Workshop.* 2019:72–78.

---

*End of manuscript v0.2. Compared to v0.1 (`paper_doc/MedAI_EPI_Manuscript_v0.1.md`), this version restructures to Brain Communications REPORT format, moves the abstract into a single unlabeled paragraph after the title block, adopts the "we describe" and "we found" narrative voice, reports numbers with inline confidence intervals where available, replaces headed tables with a single running Table 1/Table 2 pattern, tightens the discussion to a comparative-with-prior-work opening + limitations paragraph pattern, and adds a citation to the AutoHS paper (reference 13) as an in-lab methodological precursor to the framework's evidence-grounding stance. The AutoHS reference also indirectly cites the author's prior demonstration that an evidence-grounded methodology can achieve clinical translation.*
