# MedAI-EPI: An Open Framework for Schema-Constrained, Evidence-Grounded Structured Epilepsy Phenotype Extraction from Clinical Documents

**Version:** 0.1 (2026-09-22) — INTERNAL DRAFT for PI + co-author review.
**Status:** Methods locked; results are preliminary (B0 rules baseline only; M0/M1/M2 pending real Med42 GPU inference; B1 pending training on silver labels).
**Positioning:** methodology + open-benchmark paper. NOT a clinical-validation paper.
**Target venues:** JAMIA Open (methods slot), *Journal of Biomedical Semantics*, or npj Digital Medicine (short-format methods).

**Authors** (draft, to be finalized): `<YOUR_NAME>`\*, `<PI_NAME>`.
\*Corresponding: `<YOUR_EMAIL>`

---

## Abstract

**Background.** Epilepsy research increasingly depends on structured phenotype variables recovered from unstructured clinical text. Existing information-extraction pipelines are typically institutional, closed-source, or tied to a single document type, making cross-study comparison difficult and reproducibility poor.

**Objective.** To release an **open, reproducible, evidence-grounded** framework for structured epilepsy phenotype extraction from clinical documents, and to characterize its behaviour on publicly available annotated corpora before institutional deployment.

**Methods.** We define a versioned Pydantic ontology (schema v0.2.1) covering seven modules per the 2017 International League Against Epilepsy (ILAE) classification. Every extracted value carries a verbatim evidence quote from its source document. We implement six system arms — B0 rules baseline, B1 BioClinicalBERT single-head classifier, and Med42-8B M0/M1/M2 zero-shot / few-shot / schema-constrained prompting — and evaluate them on 200 dual-annotated synthetic epilepsy clinic letters (Fonferko-Shadrach 2024, CC-BY 4.0), silver-mapped to our schema. Deterministic decoding (seed=0, temperature=0) is used throughout the evaluation. Schema validity, evidence precision, unsupported-claim rate, and per-field precision/recall/F1 are computed with patient-level bootstrap 95% CIs.

**Results.** *[PRELIMINARY — full numbers pending GPU-node Med42 inference.]*
The B0 rules baseline achieves 100% schema validity and 100% evidence precision by construction, and a macro F1 of 0.41 on the five-field ClinicalSeizure core set. LLM arms (M0/M1/M2) will be reported in the next revision.

**Conclusions.** MedAI-EPI is released as an open framework — schema, prompts, extraction pipeline, evaluation harness, silver-labeled corpus, and Docker container — so that future epilepsy-phenotyping work can be reproducibly benchmarked. All artifacts are under permissive licenses; the framework is designed for research phenotyping, not autonomous clinical judgment.

**Keywords:** epilepsy, natural language processing, information extraction, large language models, structured output, evidence grounding, ILAE 2017, reproducibility.

---

## 1. Introduction

Epilepsy affects an estimated 70 million people worldwide. Structured phenotype variables — seizure type, epilepsy type, medication history, drug-resistance status, imaging findings, surgical outcomes — are the analytic substrate for retrospective cohort studies, genotype-phenotype correlation, treatment-response research, and multimodal machine-learning models over raw EEG and MRI. In practice, these variables live in unstructured clinical text: outpatient letters, EEG reports, MRI reports, EMU discharge summaries, presurgical evaluations, surgery-conference notes.

Traditional clinical information-extraction pipelines have made this problem tractable at institutional scale [1–3], but three limitations persist:

1. **Reproducibility gap.** Institutional annotation corpora are almost never released. Xie et al.'s 1,000-note Penn corpus, Adelson et al.'s Vanderbilt Engel/ILAE outcome set, and Abeysinghe et al.'s EMU-report corpus remain internal. Cross-study comparison relies on reported numbers rather than the same data.
2. **Document heterogeneity.** Most published systems target one document family (clinic letters, or EEG reports, or discharge summaries) [1, 2]. Real epilepsy phenotyping spans MRI, EEG, and multiple narrative note types.
3. **Reliability beyond F1.** JSON validity, evidence quality, and hallucination rate are increasingly recognized as first-order metrics [4], but they are seldom reported alongside per-field accuracy.

Large language models (LLMs), particularly clinically fine-tuned models like Med42 [5], offer flexible extraction without task-specific supervision, but bring their own reliability concerns — brittle structured output, unsupported inference, and unstable behaviour across document types [6, 7].

This paper introduces **MedAI-EPI**, an open framework that couples: (i) a versioned modular epilepsy phenotype ontology aligned with ILAE 2017, (ii) a schema-constrained extraction pipeline with post-hoc validation and deterministic repair, (iii) evidence-span grounding as a first-class output, (iv) transparent baselines (rules + BioClinicalBERT) alongside LLM prompting arms, and (v) an evaluation harness that reports schema validity, evidence correctness, and per-field precision/recall/F1 with bootstrap CIs.

We evaluate MedAI-EPI on 200 synthetic epilepsy clinic letters from Fonferko-Shadrach et al. 2024 — the largest publicly annotated epilepsy-specific corpus available under an open license. Because the Fonferko-Shadrach annotation ontology is UMLS-entity-based rather than modular, we release a **silver-labeling pipeline** (`scripts/silver_label_fonferko.py`) that maps their gold annotations to our v0.2.1 schema. All 200 records validate under our schema without post-hoc repair.

**Contributions:**

- A versioned, Pydantic-validated, evidence-grounded epilepsy phenotype ontology (Schema v0.2.1) covering 6 modules and 8 open questions flagged for community review.
- 22 versioned prompt templates (6 modules × 3 arms + 4 real-provenance v2 few-shots from Fonferko-Shadrach) with a change-history log.
- A validation-and-repair extraction pipeline that measures raw and repaired validity separately, so schema-constraint effects are reported honestly.
- An evidence verifier that checks every extracted value has a verbatim source-text quote.
- Rules-baseline extractors for MRI, EEG, medication, and clinical-seizure modules.
- A BioClinicalBERT single-head training pipeline for the `epilepsy_type` field, trainable on the released silver labels.
- A reproducibility container (`Dockerfile.eval`) that runs the full evaluation on any conforming corpus in one command.
- All artifacts released under MIT (code) / CC-BY 4.0 (silver labels) / provenance-preserved for external corpora.

We deliberately do **not** claim clinical accuracy on real electronic health records. The Fonferko-Shadrach corpus is synthetic. Institutional validation on real notes is a follow-up study for which this framework is the substrate.

---

## 2. Related Work

*(Placeholder — to be expanded from `paper_doc/MedAI_Paper1_Literature_Review_Reference_Guide.docx`.)*

**2.1 Epilepsy-specific clinical NLP.** ExECT (Fonferko-Shadrach 2019) [1] pioneered clinic-letter phenotype extraction with rules + statistical NLP. Xie et al. (2022, 2023) [2, 8] extended to transformer-based extraction of seizure frequency, drug resistance, and longitudinal outcome dynamics, but on institutional Penn data. Decker et al. (2022) [3] and Abeysinghe et al. (2025) [9] tackled seizure typing and frequency from EHR notes. Adelson et al. (2026) [10] validated LLM agents for Engel/ILAE surgical outcome scoring.

**2.2 LLMs for clinical information extraction.** Agrawal et al. (2022) [11] established zero-shot/few-shot clinical extraction as viable across multiple tasks. Neveditsin et al. (2025) [4] evaluated structured-output robustness (JSON validity), motivating our raw-vs-repaired validity distinction. Li et al. (2025) [6] introduced knowledge-conditioning for hallucination reduction in radiology-report extraction.

**2.3 Structured generation.** Prior work uses token-level constrained decoding (Outlines, Guidance, Instructor) to guarantee schema validity by construction. We deliberately avoid this — because our study measures raw-vs-repaired validity as a scientific question, token-level constraints would trivialize the measurement. See Methods §3.6.

**2.4 Reporting standards.** We follow TRIPOD-LLM-style reporting for methods and reproducibility (Supplement A).

**Gap this paper addresses.** No open framework exists that combines (i) versioned modular epilepsy phenotype ontology aligned to ILAE 2017, (ii) evidence-grounded extraction with schema validity reported at both raw and repaired levels, (iii) baselines + LLM prompting arms + rules-baseline extractors, and (iv) a reproducibility container releasable under permissive licenses. This paper closes that gap for the epilepsy phenotyping community.

---

## 3. Methods

### 3.1 Study design

Open-corpus reproducible methods paper. All experiments run on publicly available corpora with permissive licenses. No PHI touched. IRB determination: not human-subjects research (secondary analysis of published de-identified synthetic corpora). No adjudicated gold labels from the authors' institution are used in this paper.

### 3.2 Phenotype ontology (Schema v0.2.1)

A Pydantic v2 ontology (`schema/`) defines six modules:

- **ClinicalSeizureModule** — epilepsy type (ILAE 2017), predominant + other seizure types, awareness, semiology (free text), age at onset, seizure frequency (with duration and per-type qualifier), status epilepticus history, etiology category (ILAE 2017 six-category) + etiology specifics (gene, variant, autoantibody, tumor, pathogen, metabolic), focal motor / non-motor onset subtypes.
- **MedicationModule** — current / prior / failed anti-seizure medications with dose and status, adverse effects, drug-resistance status (ILAE 2010), surgery history with Engel + ILAE outcome enums, non-drug therapies (ketogenic diet, IVIG, etc.).
- **ClinicalLocalizationModule** — clinician's localization hypothesis (lobe + laterality + source).
- **EegModule** — study type, background, IED findings (with dominant Hz), seizures captured, ictal onset lobe / laterality.
- **MriModule** — overall normal, findings (MOGHE, FCD Palmini I/IIa/IIb, HS, etc.), lesion lobe / laterality, convenience booleans for HS and FCD (with consistency validator), MRI-negative flag, field strength.
- **IntegratedPhenotypeModule** — cross-modality synthesis (only for documents that themselves integrate).

Every field is wrapped in `Evidence[T]` carrying value, certainty (definite / probable / possible / negated / unknown / not_documented), temporal status, evidence text, source document ID + date, and optional character offsets. See Supplement B (`docs/SCHEMA_V0_2.md`) for the complete specification.

**Applicability mask** (`schema/applicability.py`) restricts each module to the document types where it is meaningful. MRI-report documents can only populate MriModule; progress notes can only populate ClinicalSeizure / Medication / ClinicalLocalization.

Coding cross-references are optional first-class fields: `DocumentMetadata.icd10cm_codes`, `.snomed_ct_codes`, and `Medication.rxnorm_cui`. ILAE remains the primary phenotype vocabulary; ICD codes are cohort-validation metadata, never the extraction target.

### 3.3 Extraction pipeline

For each (document, module, arm) triple:

1. **Prompt render** — `services/prompt_registry.py` returns a versioned template (`{module}.{arm}.{version}`) with role preamble, task instruction, output directives, few-shot examples (M1/M2), and — for M2 — the module's JSON schema injected into the system prompt.
2. **Model generation** — `services/med42_backend.py` produces text under deterministic decoding (`do_sample=False, seed=0, max_new_tokens=1024`).
3. **Validation and repair** — `services/extract.py` attempts `Pydantic.model_validate_json(raw)`. If it fails, a bounded deterministic repair chain runs: (a) strip Markdown code fences, (b) regex-extract the largest balanced JSON object, (c) strip fence then regex. Every attempt is logged. The final validity flag distinguishes *raw-valid* from *repaired-valid* — the paper reports both.
4. **Evidence verification** — `services/evidence_verifier.py` walks the parsed phenotype and checks each non-null Evidence's quoted text appears verbatim (whitespace-normalized) in the source document.
5. **Manifest** — `services/run_manifest.py` writes a JSON record per inference with code SHA, hardware, decoding config, schema/prompt versions, raw response, parsed value, repair method, validity flags, and timing. Manifests are the atomic reproducibility unit.

### 3.4 System arms

| Arm | Description | Where implemented |
|---|---|---|
| **B0** | Regex / keyword rules per module, deterministic, precision-heavy | `services/baseline_rules{,_eeg,_medication,_clinical_seizure}.py` |
| **B1** | BioClinicalBERT single-head classifier trained on silver labels; currently released for `epilepsy_type` only | `services/baseline_bert.py`, `scripts/train_b1_epilepsy_type.py` |
| **M0** | Med42-8B zero-shot | Prompt IDs `<module>.M0.v1` |
| **M1** | Med42-8B few-shot (one synthetic or one Fonferko-adapted example) | Prompt IDs `<module>.M1.{v1,v2}` |
| **M2** | M1 + JSON schema injected in the prompt (**prompt-level** constraint only; no token-level constrained decoding) | Prompt IDs `<module>.M2.{v1,v2}` |
| **M3** | M2 + evidence-grounding requirement + evidence verifier scoring | Applied post-hoc via `services/evidence_verifier.py` |

Med42-8B (`m42-health/Llama3-Med42-8B`) is loaded locally on an NVIDIA L40S GPU (24 GB VRAM) with float32 weights. Inference deterministic; no sampling.

Constrained decoding is **deliberately avoided** at the token level (Outlines, Guidance, Instructor). Because the paper's second-order finding is *"does prompt-level schema constraint improve raw validity?"*, guaranteeing validity by construction would trivialize the measurement.

### 3.5 Evaluation corpus

**Fonferko-Shadrach 2024 (primary):** 200 synthetic epilepsy clinic letters written by neurology consultants, specialist trainees, and epilepsy nurses; dual-annotated using published guidelines with adjudicated gold standard. CC-BY 4.0 (Zenodo records 8381080, 8356494, 8382589, 12520180). Original ExECT-v2 annotations are entity-and-attribute (Diagnosis, Prescription, SeizureFrequency, PatientHistory, Investigations, EpilepsyCause, Onset, BirthHistory, WhenDiagnosed) with UMLS CUIs and offset spans.

**Silver-labeling pipeline** (`scripts/silver_label_fonferko.py`) maps their annotation schema to our v0.2.1 schema:
- `Prescription` → `MedicationModule.current_asms` / `prior_asms` / `failed_asms` (status inferred by sentence-scoped keyword heuristic).
- `SeizureFrequency` → `ClinicalSeizureModule.seizure_frequency` with `LowerNumberOfSeizures` / `UpperNumberOfSeizures` / `TimePeriod` mapped to `count_min` / `count_max` / `period`.
- `Diagnosis` (with `DiagCategory=Epilepsy`) → `epilepsy_type` via a CUI→ILAE lookup table (15 CUIs mapped in v0.1 of the pipeline).
- `Diagnosis` (with `DiagCategory=MultipleSeizures` or `SingleSeizure`) → `predominant_seizure_type` via CUI lookup.
- `Onset` → `age_at_onset_years` (midpoint of `AgeLower` / `AgeUpper`).
- `EpilepsyCause` → `etiology_category` (keyword classifier) + `etiology_details_text` (raw quote).
- `PatientHistory` (first non-trivial) → `semiology_text`.
- All other v0.2.1 fields set to `not_documented`.

The silver-labeling limitations are documented in `docs/FONFERKO_SHADRACH_MAPPING.md` and repeated in this paper's Limitations. All 200 letters produce Pydantic-valid records.

**Secondary (descriptive only)**: 20 open-access PMC epilepsy case reports (`data/pmc_cases/`) fetched via `scripts/fetch_pmc_epilepsy_cases.py`, used qualitatively for schema stress-testing and Limitations examples.

**Contingent (Section 5.6)**: Temple University Hospital EEG Corpus (registration in progress) as a descriptive silver-only slice for the EEG module.

### 3.6 Metrics

**Primary endpoint:** macro F1 across the "core field set" of six fields: `clinical_seizure.{epilepsy_type, predominant_seizure_type, age_at_onset_years, seizure_frequency, etiology_category}` + `medication.drug_resistance_status`.

**Secondary endpoints:**
- Raw validity rate (raw JSON parses on first response).
- Repaired validity rate after the bounded repair chain.
- Distribution of repair methods used.
- Evidence precision (fraction of non-null values whose quote appears verbatim in source).
- Unsupported-claim rate = 1 − evidence precision.
- Per-field precision / recall / F1 with support counts (`eval/metrics.py`).
- Multiset F1 on ASM name extraction (per-item TP/FP/FN via `Counter` difference).
- Error-taxonomy counts across the 12 categories defined in the blueprint (`eval/error_taxonomy.py`).
- Efficiency: prompt length (chars), tokens generated, wall-clock latency per document, GPU memory.

**Confidence intervals**: patient-level nonparametric percentile bootstrap (1000 resamples, α=0.05) via `eval/metrics.py::bootstrap_ci`. Fonferko treats each letter as one synthetic patient, so patient-level = doc-level here.

**Statistical comparisons**: paired comparisons across arms on the same documents. No formal multiple-comparison correction; all pairwise arm comparisons labelled exploratory.

### 3.7 Reproducibility

Every inference emits a run manifest (see §3.3). Manifests + gold labels are fed to `eval/aggregator_cli.py`, which produces per-arm ArmSummary JSON + per-field CSV. The full evaluation runs inside a container (`Dockerfile.eval`) that pins Python 3.11 + Pydantic 2.11 — **no torch / transformers / Flask needed for scoring**, so any reviewer can reproduce the tables without a GPU. Med42 inference itself is separately scripted (`scripts/slurm_m2_mri.sh`) but the reproducibility surface for the paper's tables is CPU-only.

Code, silver labels, prompts, schemas, and manifests are all under version control; commit SHA is embedded in each manifest.

---

## 4. Results

*[PRELIMINARY — real Med42 numbers pending GPU-node inference. B1 numbers pending training on silver labels. TUH numbers contingent on registration approval.]*

### 4.1 Corpus characterization

**Fonferko-Shadrach 2024**: 200 synthetic clinic letters. 2,092 total annotations across 9 entity types. Silver-labeled to v0.2.1 with 100% Pydantic validity. Field population rates (Table 1):

**Table 1. Silver-label field population, Fonferko-Shadrach v0.2.1 (n=200 letters).**

| Field | n populated | % |
|---|---:|---:|
| clinical_seizure.epilepsy_type | 94 | 47% |
| clinical_seizure.predominant_seizure_type | 123 | 62% |
| clinical_seizure.seizure_frequency | 142 | 71% |
| clinical_seizure.semiology_text | 165 | 83% |
| clinical_seizure.age_at_onset_years | 15 | 7.5% |
| clinical_seizure.etiology_category | 28 | 14% |
| medication.current_asms (non-empty) | 143 | 72% |
| medication.prior_asms (non-empty) | 29 | 15% |
| medication.failed_asms (non-empty) | 4 | 2% |

### 4.2 B0 rules baseline on Fonferko silver

**Table 2. B0 rules baseline vs Fonferko silver labels.**

| Property | Value | Notes |
|---|---:|---|
| Documents processed | 200 | |
| Schema validity (raw) | 1.000 | Rules emit valid JSON by construction |
| Evidence precision | 1.000 | Rules cite verbatim spans |
| Unsupported-claim rate | 0.000 | Zero hallucinations by design |
| Total evidence objects checked | 2,166 | |

**Per-field F1 on the core set (Table 3):**

| Module | Field | n_applicable | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|
| clinical_seizure | epilepsy_type | 200 | 0.73 | 0.77 | 0.75 |
| clinical_seizure | predominant_seizure_type | 200 | 0.54 | 0.50 | 0.52 |
| clinical_seizure | age_at_onset_years | 200 | 0.21 | 0.60 | 0.32 |
| clinical_seizure | seizure_frequency | 200 | 0.04 | 0.04 | 0.04 |
| clinical_seizure | etiology_category | 200 | 0.33 | 0.71 | 0.45 |
| medication | drug_resistance_status | 200 | 0.00 | 0.00 | 0.00 |
| medication | asm_names_multiset | 200 | 0.49 | 0.69 | 0.57 |
| **clinical_seizure** | **macro F1** | | | | **0.414** |
| **medication** | **macro F1** | | | | **0.286** |

Interpretation: rules are precision-heavy on categorical fields (epilepsy type F1=0.75). Numeric / free-text fields (age at onset, seizure frequency raw text) show low agreement with silver — largely because our rules extract different spans than the Fonferko silver-labeling pipeline chose. This is a **silver-vs-silver artifact**, not a rules failure per se. Adjudicated gold on the same 30 letters (Section 5.4) would clarify.

`drug_resistance_status` F1 = 0.00 because Fonferko's ExECT-v2 does not annotate this field; both silver and rules return `not_documented` for every letter. Reported for completeness.

### 4.3 B1 BioClinicalBERT (epilepsy_type head)

*[PENDING — training runs on silver labels via `scripts/train_b1_epilepsy_type.py`. Expected outcome: F1 higher than B0 rules on epilepsy_type by ~5–10 points, but with silver-vs-silver over-fitting risk that we explicitly discuss.]*

**Table 4. B1 (BioClinicalBERT, single-head epilepsy_type) — pending.**

### 4.4 M0 / M1 / M2 Med42-8B extraction

*[PENDING — full Med42 GPU run scheduled via `sbatch scripts/slurm_m2_mri.sh` (medication + clinical_seizure arm extension needed). Manifests written to `data/run_manifests/<date>/` will be aggregated into Table 5.]*

**Table 5. M0 / M1 / M2 raw + repaired validity, per module — pending.**

**Table 6. M0 / M1 / M2 per-field precision / recall / F1 on Fonferko silver — pending.**

**Table 7. Repair-method distribution — pending.**

### 4.5 Evidence quality across arms

*[PENDING — evidence precision + unsupported-claim rate per arm from run manifests.]*

**Table 8. Evidence precision (verbatim substring match) per arm — pending.**

### 4.6 TUH EEG Corpus (descriptive only)

*[CONTINGENT — pending Temple University NEDC registration. Descriptive statistics on EegModule field-extraction rates from ~500 sampled TUH reports.]*

### 4.7 Efficiency

*[PENDING — from run manifests: prompt length, tokens generated, latency per document, GPU memory.]*

**Table 9. Efficiency by arm — pending.**

Preliminary observation from smoke tests: M2 prompts (~16,000 chars) are ~8× larger than M0 (~1,900 chars) due to schema injection. Whether this cost is offset by validity improvement is the primary tradeoff Table 9 will quantify.

### 4.8 Error taxonomy

*[PENDING — 12-category error breakdown from `eval/error_taxonomy.py` on M0/M1/M2 predictions vs Fonferko silver.]*

---

## 5. Discussion

*[PLACEHOLDER — final Discussion depends on Section 4 numbers. Skeleton with the argument shape:]*

### 5.1 What we can and cannot claim

MedAI-EPI, as reported here, is a **methodology + open-benchmark** contribution. It is **not** a clinical-accuracy claim. The Fonferko-Shadrach corpus is synthetic; extraction quality on real EHR text is a separate empirical question that the framework enables but does not answer.

### 5.2 Schema validity as a scientific finding

Even before M-arm numbers are reported, the B0 rules baseline demonstrates a design principle: **structured, evidence-grounded extraction can be reliable by construction**. Any degradation observed in the LLM arms is attributable to model / prompt behaviour, not to schema difficulty.

### 5.3 The raw-vs-repaired validity distinction

By deliberately avoiding token-level constrained decoding, we can report both raw validity (does the model emit valid JSON on first attempt?) and repaired validity (does deterministic post-hoc repair rescue invalid emissions?). This distinction matters for downstream integration: a system with 100% repaired validity but 20% raw validity implies the model is inconsistent, which affects trust in individual predictions even when aggregate metrics look strong.

### 5.4 Silver-label caveats

Every field-level F1 reported here compares one silver source (rules or LLM) against another (Fonferko silver). Discrepancies conflate three sources of disagreement:

1. Genuine model error.
2. Silver-labeler idiosyncrasy (our CUI→ILAE lookup omissions, keyword-classifier gaps).
3. Fonferko's own ExECT-v2 annotator choices (e.g., placing "subarachnoid haemorrhage" under `PatientHistory` rather than `EpilepsyCause`).

To disentangle these, we recommend a small adjudicated gold subset (~30 letters) rated by an epileptologist directly against v0.2.1 — a follow-up experiment.

### 5.5 Positioning relative to prior epilepsy NLP

Xie et al. and Adelson et al. report headline metrics on institutional data that cannot be reproduced by independent teams. MedAI-EPI's contribution is orthogonal: an open framework against which those (and future) internal results can be *directly and reproducibly compared* once each team runs the framework on their own IRB-approved data.

### 5.6 Framework use for future institutional studies

The natural next step is a Shape-B study using this framework on IRB-approved institutional data, with adjudicated gold annotations covering all six modules and heterogeneous document types (MRI + EEG + EMU + presurgical). That study is out of scope for this paper.

---

## 6. Limitations

1. **Synthetic corpus.** Fonferko-Shadrach letters are written by clinicians in a synthetic-composition setting; they lack the artifacts of real EHR text (copy-forward, dictation errors, cross-note contradictions, incomplete sentences). Real-EHR performance is not this paper's contribution.
2. **Single document type in the primary evaluation.** Fonferko is clinic letters only. MRI reports, EEG reports (until TUH), EMU discharges, presurgical evals, surgery conferences, and procedure notes are not evaluated. Rules baselines for these modules are implemented (`services/baseline_rules{,_eeg}.py`) but only stress-tested on synthetic examples.
3. **Silver-labeling ambiguity.** Field-level F1 is computed against silver, not adjudicated gold. Section 5.4 discusses the three-way conflation.
4. **Model choice.** Med42-8B is one clinical LLM among many. We do not benchmark against general-purpose LLMs (GPT-4, Claude, Gemini) in this paper — that comparison is left to future work.
5. **Prompt v2 iteration.** Prompt templates are frozen at their initial version for the reported results. Post-hoc prompt engineering that overfits to Fonferko is explicitly avoided.
6. **No PEFT / fine-tuning of Med42.** Deferred to a follow-up study; the schema, prompts, and eval harness accommodate it when the labeled data warrants it.
7. **B1 covers one field only.** Full B1 (all seven fields with heads) requires more silver labels or gold labels; released code makes this extension straightforward.
8. **English-only.** Corpus and prompts are English; extension to other languages requires vocabulary + prompt-level adaptation.
9. **Reporting checklist scope.** We follow TRIPOD-LLM style but do not claim full TRIPOD-LLM compliance in absence of a clinical-validation cohort.

---

## 7. Reproducibility

- **Code**: [github.com/phindagijimana/medai](https://github.com/phindagijimana/medai) (tag `v0.2.1-paper1` on publication).
- **Schema**: `docs/SCHEMA_V0_2.md` (v0.2.1). Machine-checkable at `schema/`.
- **Silver labels**: `data/fonferko_shadrach_2024/silver_labels_v0_2_1/` — 200 records, CC-BY 4.0.
- **Prompts**: `services/prompt_registry.py` — 22 versioned templates (18 v1 + 4 v2 with Fonferko-Shadrach provenance).
- **Container**: `Dockerfile.eval` (Python 3.11, Pydantic 2, no torch) reproduces all Section 4 tables from released manifests.
- **Manifests**: `data/run_manifests/` (from the runs that produced the paper's tables) will be attached as a Zenodo deposit at publication.
- **Reporting checklist**: `docs/TRIPOD_LLM_CHECKLIST.md`.

## 8. Ethics

No PHI touched. Fonferko-Shadrach 2024 letters are synthetic and CC-BY 4.0. Not human-subjects research; institutional IRB determination on file if requested.

## 9. Funding and conflicts of interest

*[TO FILL IN]*

## 10. References

*[Placeholder — final list to be curated. Anchor references below map to the Related Work callouts.]*

1. Fonferko-Shadrach B et al. (2019). Using natural language processing to extract structured epilepsy data from unstructured clinic letters: development and validation of the ExECT system. *BMJ Open* 9:e023232. doi:10.1136/bmjopen-2018-023232.
2. Xie K et al. (2022). Extracting seizure frequency from epilepsy clinic notes: a machine reading approach to natural language processing. *JAMIA* 29(5):873–881. doi:10.1093/jamia/ocac018.
3. Decker BM et al. (2022). Development of a natural language processing algorithm to extract seizure types and frequencies from the electronic health record. *Seizure* 101:48–51. doi:10.1016/j.seizure.2022.07.010.
4. Neveditsin N, Lingras P, Mago VK (2025). Evaluating structured output robustness of small language models for open attribute-value extraction from clinical notes. *ACL SRW*.
5. Christophe C et al. (2024). Med42-v2: A suite of clinical LLMs. arXiv:2408.06142.
6. Li D et al. (2025). Automated clinical data extraction with knowledge-conditioned LLMs. *COLING Industry Track*.
7. Agrawal M et al. (2022). Large language models are few-shot clinical information extractors. *EMNLP*: 1998–2022. doi:10.18653/v1/2022.emnlp-main.130.
8. Xie K et al. (2023). Generalization of finetuned transformer language models to new clinical contexts. *JAMIA Open* 6(3):ooad070.
9. Abeysinghe R et al. (2025). Leveraging pretrained language models for seizure frequency extraction from epilepsy evaluation reports. *npj Digital Medicine* 8:208.
10. Adelson PD, Delaney H, D'Haese PF (2026). Bridging the outcome documentation gap in epilepsy surgery: validating large language model agents for automated Engel and ILAE scoring from clinical notes. *Epilepsia*. doi:10.1002/epi.70341.
11. Fonferko-Shadrach B et al. (2024). Annotation of epilepsy clinic letters for natural language processing. *J Biomed Semantics* 15:17. doi:10.1186/s13326-024-00316-z.
12. Fisher RS et al. (2017). Operational classification of seizure types by the ILAE: position paper of the ILAE Commission for Classification and Terminology. *Epilepsia* 58(4):522–530.

---

## Appendices (in supplement)

- **A. TRIPOD-LLM reporting checklist** — `docs/TRIPOD_LLM_CHECKLIST.md`.
- **B. Full schema specification** — `docs/SCHEMA_V0_2.md`.
- **C. Prompt registry** — full text of every versioned template, `services/prompt_registry.py`.
- **D. Silver-labeling pipeline** — mapping tables and quality caveats, `scripts/silver_label_fonferko.py` + `docs/FONFERKO_SHADRACH_MAPPING.md`.
- **E. Fonferko-Shadrach schema stress-test** — `docs/SCHEMA_V0_1_STRESS_TEST.md`.
- **F. Corpus-outreach log** — `docs/CORPUS_OUTREACH.md` (for the co-author disclosure of parallel data-request tracks).
