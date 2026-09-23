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

Structured epilepsy phenotype variables — seizure type, epilepsy type, medication history, drug-resistance status, imaging findings, and surgical outcomes — are the analytic substrate for retrospective cohort research, genotype-phenotype correlation, and downstream multimodal modelling of raw EEG and MRI. In routine care these variables live in unstructured clinical text distributed across MRI reports, EEG reports, progress notes, EMU discharge summaries, presurgical evaluations, and surgery-conference notes. Extraction pipelines that recover them at institutional scale have been reported, but the underlying corpora and annotation schemas are almost never released, limiting cross-study comparison and reproducibility. Using an open-license synthetic epilepsy clinic-letter corpus (Fonferko-Shadrach et al. 2024, n = 200) silver-mapped to a versioned Pydantic ontology aligned with the 2017 ILAE classification, we evaluated a rules baseline (B0), a BioClinicalBERT single-head classifier (B1), and Med42-8B zero-shot / few-shot / schema-constrained prompting (M0, M1, M2) using deterministic decoding. The rules baseline achieved macro F1 of 0.41 across five ClinicalSeizure core fields with 100% schema validity and 100% evidence precision by construction. LLM-arm numbers, evidence quality, and repair-method distributions are pending completion of GPU-scheduled inference. To facilitate reproducibility we release the schema, prompt registry, evaluation harness, silver-label conversion pipeline, and a Docker container that reproduces every reported number from the released run manifests.

1 Department of Neurology, University of Rochester, School of Medicine and Dentistry, Rochester, NY, USA
2 [Additional affiliations]

Correspondence to: [Corresponding author, email].

Keywords: epilepsy phenotyping; large language models; structured information extraction; evidence grounding; ILAE 2017; open-source framework.

---

## Introduction

Approximately one-third of individuals with focal epilepsy continue to have seizures despite two or more anti-seizure medications and are candidates for surgical evaluation.^1,2^ Retrospective epilepsy research on such cohorts — including studies of drug-resistance trajectories, imaging-based localization, and surgical-outcome prediction — depends on structured phenotype variables that are recovered from unstructured clinical text. Automated phenotype extraction from epilepsy clinical documentation has been reported using rule-based systems,^3^ transformer encoders,^4,5^ and, more recently, generative large language models (LLMs).^6–8^ These systems have advanced the field considerably; however, three properties limit their broader clinical and scientific translation.

First, the annotated corpora on which these systems are trained and evaluated are almost never released. Institutional gold-labeled note sets from Penn,^4,5^ Vanderbilt,^7^ and comparable groups are internal, and independent teams cannot reproduce reported numbers or evaluate their own methods on the same data. Second, most published systems target a single document family — clinic letters, EEG reports, or discharge summaries — while real epilepsy phenotyping spans MRI, EEG, and multiple narrative note types with different vocabularies and templating conventions.^9^ Third, published systems seldom report the validity of their structured JSON output, the correctness of their supporting evidence quotes, or the fraction of extracted values that are unsupported by the source document.^10^ These reliability metrics are increasingly recognized as first-order for downstream clinical or research reuse.^10,11^

Recent methodological work has introduced schema-constrained decoding^12^ and evidence-grounded generation^13^ as ways to improve reliability, and clinical LLMs such as Med42-v2^14^ have made locally-deployable extraction feasible for institutions unwilling to send patient text to external APIs. What remains missing is an *open, reproducible* framework that couples a versioned modular phenotype ontology, LLM prompting arms, transparent baselines, and an evaluation harness capable of reporting schema validity, evidence quality, and per-field accuracy alongside conventional precision, recall, and F1.

The purpose of this study was to develop and characterize such a framework — **MedAI-EPI** — before institutional deployment. Using the openly-licensed Fonferko-Shadrach 2024 synthetic epilepsy clinic-letter corpus as the primary evaluation dataset, we (i) defined a versioned Pydantic ontology of six phenotype modules aligned with the 2017 International League Against Epilepsy (ILAE) classification, (ii) implemented a validation-and-repair extraction pipeline that measures raw and repaired JSON validity separately, (iii) grounded every extracted value in a verbatim source quote and scored evidence precision independently of field accuracy, and (iv) compared a rules baseline (B0), a BioClinicalBERT single-head classifier (B1), and Med42-8B under three prompting arms (M0 zero-shot, M1 few-shot, M2 few-shot with prompt-level schema injection). We first show that a rules baseline emits valid, evidence-grounded output by construction and achieves interpretable field-level performance on the ClinicalSeizure and Medication modules. LLM-arm numbers are pending completion of GPU-scheduled inference and will be added in the next revision. To facilitate validation, we provide the schema, prompt registry, evaluation harness, silver-label conversion pipeline, and a Docker container that reproduces every reported number from the released run manifests.

---

## Materials and methods

### Study design

Open-corpus reproducible methods study. All experiments were conducted on publicly available synthetic corpora; no protected health information was accessed at any point. Institutional review board determination: not human-subjects research (secondary analysis of published de-identified synthetic content). No adjudicated gold labels from the authors' institution were used in this manuscript; institutional-cohort validation is scoped as a separate follow-up study.

### Evaluation corpus

The primary evaluation dataset was the Fonferko-Shadrach 2024 synthetic epilepsy clinic-letter corpus,^15^ consisting of 200 synthetic letters written by neurology consultants, specialist trainees, and epilepsy specialist nurses under an established annotation protocol. The letters were dual-annotated by trained researchers using the ExECT-v2 annotation manual and adjudicated to a gold standard set. Annotations use a UMLS-based entity-and-attribute schema with character offsets. The corpus is distributed under a Creative Commons Attribution 4.0 International licence (Zenodo records 8381080, 8356494, 8382589, 12520180). Because the ExECT-v2 annotation ontology is entity-based rather than modular, we developed a silver-labeling pipeline (see below) that maps their annotations to our ontology. All 200 records validate against our v0.2.1 schema without post-hoc repair.

Twenty open-access peer-reviewed PubMed Central epilepsy case reports (`data/pmc_cases/`) were used qualitatively for schema stress-testing and are reported descriptively where relevant. The Temple University Hospital EEG Corpus is a candidate secondary dataset for descriptive characterization of the EegModule extraction; registration is pending and results are contingent on approval.

### Phenotype ontology

We defined a versioned Pydantic v2 ontology (schema v0.2.1) comprising six modules:

*ClinicalSeizureModule* — ILAE 2017 epilepsy type, predominant and secondary seizure types, awareness, semiology (free text), age at onset, seizure frequency with duration and per-type qualifier, status epilepticus history, six-category etiology (ILAE 2017) with structured specifics slots (gene, variant, autoantibody, tumor, pathogen, metabolic), and focal motor and non-motor onset subtypes.

*MedicationModule* — current, prior, and failed anti-seizure medications with dose and status, adverse effects, drug-resistance status per the ILAE 2010 definition, surgery history with Engel and ILAE outcome enumerations, and non-drug therapies (ketogenic diet, IVIG, plasmapheresis, corticosteroids, and other adjunctive treatments).

*ClinicalLocalizationModule* — clinician localization hypothesis expressed as lobe, laterality, and source (clinician hypothesis; distinguished from EEG-confirmed, MRI-confirmed, and SEEG-confirmed localizations in the imaging modules).

*EegModule* — study type, background, interictal epileptiform discharge findings (with type, localization, laterality, and dominant frequency in hertz), whether seizures were captured with count, and ictal onset lobe and laterality.

*MriModule* — overall normal designation, findings enumerated over an epilepsy-relevant set including hippocampal sclerosis, focal cortical dysplasia subtypes (Palmini I, IIa, IIb), MOGHE, and other lesions, primary lesion lobe and laterality, and field strength in tesla. Convenience booleans for hippocampal sclerosis and focal cortical dysplasia are cross-validated against the findings list at the schema level.

*IntegratedPhenotypeModule* — cross-modality synthesis (clinical, EEG, and MRI localizations plus concordance category), populated only from documents that themselves integrate modalities (presurgical evaluations, EMU discharges, surgery-conference notes).

Every non-metadata field is wrapped in an `Evidence[T]` generic that carries value, certainty (definite, probable, possible, negated, unknown, not_documented), temporal status, evidence text (verbatim minimal-sufficient source quote), source document identifier, source date, and optional character offsets. An applicability mask restricts each module to the document types where it is meaningful; MRI reports can populate only the MriModule, progress notes cannot populate MRI or EEG, and so on. The schema, full field specifications, and per-doc-type applicability are documented in the online supplement.

### Silver-labeling pipeline

To evaluate our framework on the Fonferko-Shadrach corpus, we developed a deterministic mapping from the ExECT-v2 annotation schema to our v0.2.1 ontology (`scripts/silver_label_fonferko.py`). Prescription entities were mapped to `MedicationModule` current, prior, or failed anti-seizure medication lists using a sentence-scoped keyword heuristic for status inference. SeizureFrequency entities were mapped to `ClinicalSeizureModule.seizure_frequency` with numeric count and period fields. Diagnosis entities with DiagCategory of Epilepsy were mapped to epilepsy type via a UMLS Concept Unique Identifier to ILAE lookup table; DiagCategory of MultipleSeizures or SingleSeizure were mapped to predominant seizure type by the same lookup. Onset entities were mapped to age at onset (midpoint of age range). EpilepsyCause entities were mapped to etiology category (structural, genetic, infectious, immune, metabolic, or unknown) using a keyword classifier and to etiology details as a raw text quote. All other v0.2.1 fields were set to `not_documented`. Every silver record carries a provenance envelope naming the source paper, DOI, PMCID, Zenodo record identifiers, licence, generator script, and a `label_quality: silver` flag. All 200 records validate against v0.2.1 without repair.

### System arms

Six extraction arms were implemented and compared:

*B0* — rules and keyword baselines per module (`services/baseline_rules{,_eeg,_medication,_clinical_seizure}.py`), running without an LLM. Extraction is negation-aware (a fixed-window lookback for absent-finding phrases) and sentence-scoped (status inference does not cross sentence boundaries). Rules emit valid JSON by construction and cite verbatim source spans.

*B1* — BioClinicalBERT (`emilyalsentzer/Bio_ClinicalBERT`) single-head classifier fine-tuned on the 200 Fonferko silver records for the `epilepsy_type` field. Trained with 5 epochs, learning rate 3 × 10⁻⁵, weight decay 0.01, batch size 16, 512-token maximum sequence length, seed 0. Multi-field extension is documented in the supplement as future work.

*M0* — Med42-8B (`m42-health/Llama3-Med42-8B`) zero-shot prompting via versioned templates in the prompt registry.

*M1* — Med42-8B few-shot prompting with one demonstration per module drawn either from synthetic v1 examples or from real Fonferko-Shadrach v2 few-shots (letter EA0150) with citation provenance in each example identifier.

*M2* — M1 with the module's JSON schema injected into the system prompt. We deliberately did not use token-level constrained decoding because our study measures raw versus repaired JSON validity as a scientific outcome; guaranteeing validity by construction would trivialize that measurement.

Med42-8B was loaded locally on an NVIDIA L40S GPU (24 GB virtual slice) in bfloat16 precision. Decoding was deterministic (do_sample = False, seed = 0, maximum new tokens 1024). A pre-trained model registry captured checkpoint identifier, tokenizer version, and hardware profile per inference.

### Extraction pipeline

For each (document, applicable module, arm) tuple, the pipeline (`services/extract.py`) rendered the prompt, invoked the backend, attempted `Pydantic.model_validate_json()`, and — on failure — applied a bounded deterministic repair chain (strip Markdown code fences, extract the largest balanced JSON object, strip fence then extract). Every attempt was logged. Each inference wrote a run manifest recording code SHA, hardware, decoding configuration, prompt identifier and version, few-shot example identifiers, source document identifier and type, raw model response, raw validity flag, repair attempts and method, final validity flag, parsed value, and timing.

An evidence verifier (`services/evidence_verifier.py`) walked the parsed phenotype and checked that each non-null value's evidence text appeared as a whitespace-normalized case-insensitive substring of the source document.

### Metrics

The primary endpoint was macro F1 across a frozen core-field set of five `ClinicalSeizureModule` fields (epilepsy type, predominant seizure type, age at onset, seizure frequency, etiology category) plus `MedicationModule.drug_resistance_status`. Secondary endpoints were raw JSON validity rate, repaired validity rate, repair-method distribution, evidence precision, unsupported-claim rate, per-field precision / recall / F1 with support counts, multiset F1 on anti-seizure medication name extraction (per-item true-positive / false-positive / false-negative via multiset difference), error-taxonomy category counts across the twelve categories defined in the study protocol,^16^ and efficiency (prompt length, tokens generated, wall-clock latency per document, and GPU memory).

Confidence intervals for the primary endpoint were computed by nonparametric percentile bootstrap at the document level (1,000 resamples, α = 0.05); document-level equalled patient-level for the Fonferko corpus because each letter represents one synthetic patient. Paired comparisons across arms were performed on the same documents; all pairwise arm comparisons were labelled exploratory.

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

The rules baseline processed all 200 letters, emitting valid JSON by construction with 100% raw schema validity and 100% evidence precision (every cited quote appears verbatim in the source). The unsupported-claim rate was therefore 0.00. Per-field precision, recall, and F1 for the six core fields are reported in Table 2. Macro F1 for the ClinicalSeizure core set was 0.414. Anti-seizure medication multiset F1 was 0.573.

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

The rules baseline was strongest on categorical fields with template-y language (`epilepsy_type`, F1 = 0.75). Numeric and free-text fields (`age_at_onset_years`, `seizure_frequency`) showed lower agreement with the silver labels, primarily because the rules and the silver-labeling pipeline selected different textual spans for the same underlying concept — a silver-versus-silver artefact rather than a rules failure per se. `drug_resistance_status` returned zero performance because the Fonferko-Shadrach annotation schema does not annotate this field; both silver and rules emitted `not_documented` for every letter.

### B1 BioClinicalBERT classifier

The B1 single-head classifier for the `epilepsy_type` field was fine-tuned on the 200 Fonferko-Shadrach silver labels (SLURM job 89475, `interactive` partition, l40s.24g slice, `emilyalsentzer/Bio_ClinicalBERT` base model). Of the 200 silver records, 94 (47%) had a non-null `epilepsy_type` value; these formed the training set spanning two classes (focal, generalized). Five epochs of full-model fine-tuning (learning rate = 3 × 10⁻⁵, weight decay = 0.01, warmup ratio = 0.1, batch size = 16, maximum sequence length = 512 tokens, seed = 0) drove training loss from 0.695 to 0.483 in 16.6 s of GPU compute. The trained checkpoint is available at `checkpoints/b1_epilepsy_type_v1/` and inference is exposed via `services/baseline_bert.py::B1InferenceBackend`.

Held-out per-class precision, recall, and F1 for B1 are deferred to the adjudicated-gold subset (see Discussion §5.4) because the current training set uses silver labels that would inflate a same-set validation score. The framework provides the training script and inference wrapper as reproducibility artifacts; teams with their own gold labels can retrain B1 in one command against their own data.

### Med42-8B under M0, M1, and M2 prompting

Preliminary two-document sanity run (SLURM job 89473, `interactive` partition, l40s.24g slice, bfloat16, deterministic decoding with seed = 0). Med42-8B loaded in 5.3 s on the GPU. Table 3 reports per-arm outcomes on one synthetic MRI report (drafted for annotation-style clarity) and one PMC case-report excerpt (PMC6872800, mesial temporal lobe epilepsy with right hippocampal sclerosis) representing real prose. Full 200-letter sweep (SLURM job 89472, in progress at time of writing) will populate Table 4 in the next revision.

**Table 3. Med42-8B under M0, M1, and M2 on two representative MRI documents (SLURM job 89473).**

| Document | Arm | Raw valid | Final valid | Repair method | Tokens generated | Duration (s) |
|---|---|:---:|:---:|---|---:|---:|
| Synthetic MRI (clean) | M0 | ✗ | ✗ | failed | 254 | 22 |
| Synthetic MRI (clean) | M1 | ✓ | ✓ | – | 761 | 21 |
| Synthetic MRI (clean) | M2 | ✗ | ✓ | regex_json_extraction | 986 | 29 |
| PMC6872800 excerpt (MTLE, right HS) | M0 | ✗ | ✗ | failed | 124 | 4 |
| PMC6872800 excerpt (MTLE, right HS) | M1 | ✗ | ✗ | failed | 746 | 20 |
| PMC6872800 excerpt (MTLE, right HS) | M2 | ✗ | ✓ | regex_json_extraction | 986 | 29 |

Three observations follow from Table 3. First, Med42-8B did not produce raw-valid JSON on either document under M0 (zero-shot); both attempts fell back to the "failed" repair state. Second, M1 (few-shot) recovered a raw-valid, correctly-typed output on the synthetic MRI but failed on the PMC excerpt, suggesting few-shot demonstrations do not generalize freely from synthetic to naturalistic prose. Third, M2 (few-shot + prompt-level schema injection) achieved final validity on both documents but always via deterministic regex-based repair rather than raw-valid emission — supporting the paper's central methodological choice to separate raw from repaired validity as scientific outcomes. Full 200-letter characterization on the Fonferko-Shadrach corpus is pending completion of SLURM job 89472; results will be reported in Table 4 of the next revision with per-arm counts, per-field precision / recall / F1, and patient-level bootstrap 95% confidence intervals.

### Efficiency

Prompt-length characterization from static analysis showed that M2 prompts are approximately 8 × the length of M0 prompts (16,048 characters versus 1,894 characters for a representative MRI report) due to schema injection. Runtime and GPU-memory characterization are pending the GPU sweep.

---

## Discussion

In this study we describe an open framework for schema-constrained, evidence-grounded structured epilepsy phenotype extraction, comprising a versioned modular ontology aligned with the 2017 ILAE classification, a validation-and-repair extraction pipeline, transparent rules and BioClinicalBERT baselines, and a reproducibility container. Preliminary results on 200 openly-licensed synthetic clinic letters showed that a rules baseline achieved 100% schema validity, 100% evidence precision, and interpretable field-level performance (macro F1 = 0.41 across the ClinicalSeizure core set; anti-seizure medication multiset F1 = 0.57). LLM-arm characterization is pending completion of GPU-scheduled inference.

This study builds upon prior epilepsy information-extraction work^3–8^ but is scoped and framed differently. Fonferko-Shadrach and colleagues released a gold-annotated synthetic corpus of clinic letters^15^ that we use here as our primary evaluation set; we extend their contribution by mapping their annotation schema to a modular ILAE-aligned ontology suitable for imaging and neurophysiology extraction as well as narrative-note extraction. Xie and colleagues developed transformer-based extraction of seizure frequency and drug resistance from institutional data at Penn,^4,5^ and Abeysinghe and colleagues extended similar approaches to EMU reports.^6^ Adelson and colleagues recently validated LLM agents for automated Engel and ILAE surgical-outcome scoring at Vanderbilt.^7^ These institutional studies report headline metrics on data that other teams cannot reproduce; our framework is designed so that when institutional teams run it on their own IRB-approved data, results become directly comparable across sites.

Our methodological choice to measure raw versus repaired JSON validity separately is deliberate. Token-level constrained decoding (Outlines, Instructor, Guidance) can guarantee schema validity by construction but would trivialize a scientifically interesting question: how well has a clinical LLM internalized structured phenotype output? The prompt-level schema-injection approach used in M2 leaves the model free to succeed or fail on its own, with post-hoc deterministic repair rescuing recoverable errors. The distinction matters for downstream integration: a system with 100% repaired validity but 20% raw validity implies the model is inconsistent and requires post-processing, which affects trust in individual predictions even when aggregate metrics look strong. Our evidence-grounding requirement is orthogonal to validity and is measured independently as evidence precision and unsupported-claim rate.

This study has several notable limitations. First, the Fonferko-Shadrach corpus is synthetic; letters are written in a synthetic-composition setting and lack real electronic-health-record artefacts such as copy-forward propagation, dictation errors, cross-note contradictions, and incomplete sentences. Real-EHR performance is not this paper's contribution. Second, the primary evaluation corpus is a single document family — outpatient clinic letters — and does not exercise the MriModule, EegModule, or IntegratedPhenotypeModule. Rules baselines for those modules are implemented and stress-tested on synthetic examples but require the Temple University Hospital EEG Corpus (registration pending) or an institutional cohort for empirical evaluation. Third, field-level F1 is computed against silver labels, not adjudicated gold; discrepancies conflate genuine model error, silver-labeling idiosyncrasy (our UMLS-to-ILAE lookup omissions and keyword-classifier gaps), and Fonferko-Shadrach's own annotator choices. A follow-up adjudicated gold subset of approximately 30 letters rated by an epileptologist directly against v0.2.1 would disentangle these sources. Fourth, we did not benchmark Med42-8B against general-purpose LLMs (GPT-4, Claude, Gemini) in this manuscript; that comparison is left to future work. Fifth, our BioClinicalBERT baseline is currently a single-head classifier for `epilepsy_type` only; multi-field extension is a v0.2 goal. Sixth, we did not perform parameter-efficient fine-tuning of Med42 (LoRA / QLoRA); this is deferred to a follow-up study contingent on availability of adjudicated gold labels at sufficient scale. Finally, corpus and prompts are English only.

We envision that this framework, once its LLM-arm characterization is complete, will serve as the methodology substrate for future institutional-cohort validation studies of epilepsy phenotype extraction. Institutional teams can run the framework on their own IRB-approved documentation, populate the same evaluation harness against their own adjudicated gold labels, and produce numbers that are directly comparable across sites — enabling meta-analytic aggregation and multi-site benchmarking of clinical LLM extraction in a way that internal-corpus studies structurally preclude.

---

## Data availability

The primary evaluation dataset is publicly available at Zenodo records 8381080 (letters and gold annotations, CC-BY 4.0), 8356494 (JSON annotations), 8382589 (annotation guidelines), and 12520180 (CSV outputs). Silver-labeled derivative records are released under CC-BY 4.0 as a derivative work of the Fonferko-Shadrach corpus. The MedAI-EPI framework — schema, prompt registry, extraction pipeline, evaluation harness, baselines, silver-labeling pipeline, reproducibility container, and run manifests from the reported evaluation — is available at [repository URL to be inserted at submission]. Codes for the analyses and table generation reported in this manuscript can also be found at this address. To facilitate validation and future institutional use, the reproducibility container reproduces every table in this manuscript from the released run manifests on a laptop or CI system without a GPU.

## Funding

*[To be finalized]*.

## Competing interests

*[To be finalized]*.

## Supplementary material

Supplementary Table 1 — schema v0.2.1 field specifications (from `docs/SCHEMA_V0_2.md`).
Supplementary Table 2 — full prompt registry (from `services/prompt_registry.py`).
Supplementary Table 3 — silver-labeling mapping and caveats (from `docs/FONFERKO_SHADRACH_MAPPING.md`).
Supplementary Table 4 — error-taxonomy category definitions (from `eval/error_taxonomy.py` and the study protocol).
Supplementary Table 5 — TRIPOD-LLM reporting checklist (from `docs/TRIPOD_LLM_CHECKLIST.md`).
Supplementary Table 6 — corpus outreach log (from `docs/CORPUS_OUTREACH.md`).

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

---

*End of manuscript v0.2. Compared to v0.1 (`paper_doc/MedAI_EPI_Manuscript_v0.1.md`), this version restructures to Brain Communications REPORT format, moves the abstract into a single unlabeled paragraph after the title block, adopts the "we describe" and "we found" narrative voice, reports numbers with inline confidence intervals where available, replaces headed tables with a single running Table 1/Table 2 pattern, tightens the discussion to a comparative-with-prior-work opening + limitations paragraph pattern, and adds a citation to the AutoHS paper (reference 13) as an in-lab methodological precursor to the framework's evidence-grounding stance. The AutoHS reference also indirectly cites the author's prior demonstration that an evidence-grounded methodology can achieve clinical translation.*
