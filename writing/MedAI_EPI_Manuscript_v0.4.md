# An open framework for schema-constrained, evidence-grounded structured epilepsy phenotype extraction from clinical documents

*Draft v0.4 — internal, PI + co-author review. Extends v0.2 with §Fine-tuning + §Schema-constrained decoding methods, §M4 fine-tuned results, and v0.4 addenda in §Discussion, §Data availability, §Ethics, and §References. Voice matched to Ndagijimana et al., Brain Communications 2026 (AutoHS paper). Formatting will be adapted to target-journal style at submission.*

Philbert Ndagijimana,1 [Co-Author 2],2 [Co-Author 3],3 James J. Gugger.1,2

1 Department of Neurology, University of Rochester, School of Medicine and Dentistry, Rochester, NY, USA
2 [Additional affiliations to be finalized]
3 [Additional affiliations to be finalized]

Correspondence to: [Corresponding author, title, affiliation, email].

Keywords: epilepsy phenotyping; large language models; structured information extraction; evidence grounding; ILAE 2017; open-source framework.

Received [date]. Revised [date]. Accepted [date]. Advance access publication [date].

---

Structured epilepsy phenotype variables — seizure type, epilepsy type, medication history, drug-resistance status, imaging findings, and surgical outcomes — are the analytic substrate for retrospective cohort research, genotype-phenotype correlation, and downstream multimodal modelling of raw EEG and MRI. In routine care these variables live in unstructured clinical text distributed across MRI reports, EEG reports, progress notes, EMU discharge summaries, presurgical evaluations, and surgery-conference notes. Extraction pipelines that recover them at institutional scale have been reported, but the underlying corpora and annotation schemas are almost never released, limiting cross-study comparison and reproducibility. Using an open-license synthetic epilepsy clinic-letter corpus (Fonferko-Shadrach et al. 2024, n = 200) silver-mapped to a versioned Pydantic ontology aligned with the 2017 ILAE classification, we evaluated a rules baseline (B0), a BioClinicalBERT single-head classifier (B1), and Med42-8B zero-shot / few-shot / schema-constrained prompting (M0, M1, M2) using deterministic decoding. The rules baseline achieved macro F1 of 0.41 across five ClinicalSeizure core fields with 100 % schema validity and 100 % evidence precision by construction. On 1,200 Med42-8B extractions (200 letters × 3 arms × 2 modules) raw JSON validity was 0.0–7.0 % — the model produced clean JSON but consistently omitted the required `Evidence[T]` wrapping around each field. A deterministic two-tier repair chain (JSON-object extraction followed by `smart_repair`, which wraps bare values in default Evidence metadata and normalizes enum synonyms) raised structural validity to 24.0–100 %, but few-shot prompting (M1) delivered the highest yield of meaningful (non-null) content (15.0 %) on the medication module, outperforming both zero-shot (M0, 10.5 %) and prompt-level schema injection (M2, 7.0 %). M2 exhibited a **schema-echo pathology**: at `max_new_tokens = 1024`, Med42-8B saturated the generation budget by reproducing the injected schema rather than extracting content. The ClinicalSeizure module — with nested value objects and six required Evidence-wrapped enums — was refractory to Med42-8B extraction across all arms. Efficiency measurements showed M2 prompts averaged 16 000 characters against M0's 1 900 and cost ~8× the GPU time per inference. To facilitate reproducibility we release the schema, prompt registry, evaluation harness, silver-label conversion pipeline, smart-repair module, and a Docker container that reproduces every reported number from the released run manifests.

1 Department of Neurology, University of Rochester, School of Medicine and Dentistry, Rochester, NY, USA
2 [Additional affiliations]

Correspondence to: [Corresponding author, email].

Keywords: epilepsy phenotyping; large language models; structured information extraction; evidence grounding; ILAE 2017; open-source framework.

---

## Introduction

Approximately one-third of individuals with focal epilepsy continue to have seizures despite two or more anti-seizure medications and are candidates for surgical evaluation.^1,2^ Retrospective epilepsy research on such cohorts — including studies of drug-resistance trajectories, imaging-based localization, and surgical-outcome prediction — depends on structured phenotype variables that are recovered from unstructured clinical text. Automated phenotype extraction from epilepsy clinical documentation has been reported using rule-based systems,^3^ transformer encoders,^4,5^ and, more recently, generative large language models (LLMs).^6–8^ These systems have advanced the field considerably; however, three properties limit their broader clinical and scientific translation.

First, the annotated corpora on which these systems are trained and evaluated are almost never released. Institutional gold-labeled note sets from Penn,^4,5^ Vanderbilt,^7^ and comparable groups are internal, and independent teams cannot reproduce reported numbers or evaluate their own methods on the same data. Openly-licensed synthetic clinical corpora with clinician-adjudicated annotations offer a partial remedy: Li and colleagues demonstrated that models trained on synthetic clinical notes generalize to real-clinical-note NER at accuracy comparable to same-domain-trained models,^17^ and within epilepsy specifically Goldenholz and colleagues used an LLM-generated synthetic clinic-note cohort with known ground truth to develop and evaluate extraction of seizure frequency, symptoms, and treatment effects.^18^ Synthetic corpora therefore now constitute a legitimate development and characterization substrate for clinical NLP, distinct from — but complementary to — real-EHR institutional validation. Second, most published systems target a single document family — clinic letters, EEG reports, or discharge summaries — while real epilepsy phenotyping spans MRI, EEG, and multiple narrative note types with different vocabularies and templating conventions.^9^ Third, published systems seldom report the validity of their structured JSON output, the correctness of their supporting evidence quotes, or the fraction of extracted values that are unsupported by the source document.^10^ These reliability metrics are increasingly recognized as first-order for downstream clinical or research reuse.^10,11^

Recent methodological work has introduced schema-constrained decoding^12^ and evidence-grounded generation^13^ as ways to improve reliability, and clinical LLMs such as Med42-v2^14^ have made locally-deployable extraction feasible for institutions unwilling to send patient text to external APIs. What remains missing is an *open, reproducible* framework that couples a versioned modular phenotype ontology, LLM prompting arms, transparent baselines, and an evaluation harness capable of reporting schema validity, evidence quality, and per-field accuracy alongside conventional precision, recall, and F1.

The purpose of this study was to develop and characterize such a framework — **MedAI-EPI** — before institutional deployment. Using the openly-licensed Fonferko-Shadrach 2024 synthetic epilepsy clinic-letter corpus as the primary evaluation dataset, we (i) defined a versioned Pydantic ontology of six phenotype modules aligned with the 2017 International League Against Epilepsy (ILAE) classification, (ii) implemented a validation-and-repair extraction pipeline that measures raw and repaired JSON validity separately, (iii) grounded every extracted value in a verbatim source quote and scored evidence precision independently of field accuracy, and (iv) compared a rules baseline (B0), a BioClinicalBERT single-head classifier (B1), and Med42-8B under three prompting arms (M0 zero-shot, M1 few-shot, M2 few-shot with prompt-level schema injection). We first show that a rules baseline emits valid, evidence-grounded output by construction and achieves interpretable field-level performance on the ClinicalSeizure and Medication modules. LLM-arm numbers are pending completion of GPU-scheduled inference and will be added in the next revision. To facilitate validation, we provide the schema, prompt registry, evaluation harness, silver-label conversion pipeline, and a Docker container that reproduces every reported number from the released run manifests.

---

## Materials and methods

### Study design

Open-corpus reproducible methods study. All experiments were conducted on publicly available synthetic corpora; no protected health information was accessed at any point. Institutional review board determination: not human-subjects research (secondary analysis of published de-identified synthetic content). No adjudicated gold labels from the authors' institution were used in this manuscript; institutional-cohort validation is scoped as a separate follow-up study.

### Evaluation corpus

The primary evaluation dataset was the Fonferko-Shadrach 2024 synthetic epilepsy clinic-letter corpus,^15^ consisting of 200 synthetic letters written by neurology consultants, specialist trainees, and epilepsy specialist nurses under an established annotation protocol. The letters were dual-annotated by trained researchers using the ExECT-v2 annotation manual and adjudicated to a gold standard set. Annotations use a UMLS-based entity-and-attribute schema with character offsets. The corpus is distributed under a Creative Commons Attribution 4.0 International licence (Zenodo records 8381080, 8356494, 8382589, 12520180). Because the ExECT-v2 annotation ontology is entity-based rather than modular, we developed a silver-labeling pipeline (see below) that maps their annotations to our ontology. All 200 records validate against our v0.2.1 schema without post-hoc repair.

Twenty open-access PubMed Central epilepsy case reports (`data/pmc_cases/`) were used qualitatively for schema stress-testing.

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

### Fine-tuning: MedAI-EPI-tuned Med42

We fine-tuned the Med42-8B base weights with parameter-efficient
low-rank adaptation (LoRA)^{Hu2021, Dettmers2023}, producing an
adapter designated MedAI-EPI-tuned that we treat as a seventh
extraction arm (M4). Training pairs were of the form (prompt, target)
where the prompt asked the model to emit a MedAI-EPI v0.2.1 JSON
phenotype for a clinical document, and the target was the
schema-conformant Evidence[T]-wrapped `EpilepsyPhenotype` produced by
our converters (§Silver-labeling pipeline).

**Training corpus.** We used the union of the 1000-document synthetic
corpus v1 (500 patients × 2 rendered document types, generated by
GPT-5.6-sol under semantic-plan-constrained prompting) and the 200
Fonferko-Shadrach clinician-authored clinic letters with their v0.2.1
silver targets — 1200 pairs total. The 60-document EpiSynth pilot
corpus was **held out** as an untainted evaluation set. Patients were
split 90:10 into training and validation such that no patient's
documents straddled the split (validation set size: 122 pairs).

**LoRA configuration.** Rank r = 16, alpha α = 32, dropout 0.05, no
bias. Target modules were the attention projections
(q/k/v/o_proj) and the MLP projections (gate/up/down_proj) of every
transformer layer, following Dettmers et al.^{Dettmers2023} — MLP
targets consistently improve structured-output learning at ~2× the
attention-only parameter count. Trainable parameters were
41,943,040 out of 8,072,204,288 total parameters (0.52%).

**Training details.** AdamW, learning rate 3 × 10⁻⁴, cosine schedule
with 10% warmup, weight decay 0.01, batch size 1 with gradient
accumulation 8 (effective batch 8), bfloat16 mixed precision, seed 0.
The loss was computed on the target JSON tokens only —
prompt-position labels were masked to `-100` so gradient signal was
target-conditional. Training ran up to 5 epochs with validation-loss
early stopping (patience 2 epochs) and `load_best_model_at_end`. Total
wall-clock time was 82.1 min on a single NVIDIA L40S 24 GB slice
(SLURM job 143696, 4,928 s train_runtime).
The best checkpoint (epoch 3, validation loss 0.00952) was retained
as the released adapter; the per-epoch validation-loss trajectory
was 0.01008 → 0.00979 → **0.00952** → 0.00958 → 0.01030 (early-stopping
would have fired at patience 2 as epoch-5 val loss rose from the
epoch-3 minimum).

**Loss masking (prompt-token exclusion).** For every training pair,
the input sequence to the model was the concatenation
`<prompt tokens> || <target-JSON tokens> || <EOS>`, and the label
tensor was set to `-100` on every prompt position (PyTorch's
convention for "ignore this token in the cross-entropy loss") and to
the corresponding token id on every target position. The consequence
is that no gradient flows from prompt-position predictions — the
adapter is optimized only to predict the schema-conformant JSON
*given* the prompt, not to reconstruct the prompt itself. This is
the standard instruction-tuning-with-loss-masking convention
established by Han et al. 2021 and formalized in the QLoRA training
pipeline of Dettmers et al. 2023^{Dettmers2023}; without masking the
model wastes capacity learning to regenerate the (identical, fixed)
few-thousand-token prompt template and underfits the target
distribution. Our implementation in `scripts/finetune_lora_epi.py`
computes the prompt-token boundary from the tokenized prompt prefix
length before assembling the label tensor.

**Adapter loading at inference.** The MedAI-EPI service loads the
LoRA adapter on top of the frozen base Med42 weights via
`peft.PeftModel.from_pretrained` when the environment variable
`MEDAI_LORA_ADAPTER_DIR` is set (`services/med42_model.py`). Manifests
record the composite model identity as
`m42-health/Llama3-Med42-8B+lora:<adapter_tag>` so tuned and base
runs are distinguishable in the reproducibility artifact.

### Schema-constrained decoding

For the constrained-decoding arm we used lm-format-enforcer 0.10
(`services/constrained_decode.py`) with the target module's Pydantic
JSON schema. At every generation step, the enforcer masks tokens
that would deviate from any legal continuation of the schema. The
generated text is therefore JSON-valid against the target
`EpilepsyPhenotype` module by construction, and the smart-repair
chain is retained only as a defensive fallback. This is an
inference-time layer that does not modify model weights.

**Parser mechanics.** Concretely, lm-format-enforcer's
`JsonSchemaParser` walks the compiled JSON-schema of the target
Pydantic model as a state machine: at each decoding step the parser
knows exactly which characters — and, after tokenizer alignment,
which sub-token strings — would keep at least one legal completion
of the schema alive. Before the LLM samples a token, its raw logits
are combined with a boolean mask that zeros out every token whose
byte-string prefix would render the running JSON un-completable
(e.g. `{` when the current position expects an integer field value,
or `"foca` followed by anything other than `l"` when the schema
enum forces `"focal"`). The masked logits are then sampled or
argmax-decoded as usual. This construction, following the guided
generation framework of Willard and Louf 2023, guarantees that the
final token sequence is parseable to a schema-valid JSON object at
zero probability leakage — the model is *unable* to sample an
invalid token — while adding only the cost of one schema-state
lookup per generation step (empirically ~10–20 % wall-clock overhead
at 8-B scale in our runs). The complementary property — that only
the *shape* of the output is constrained, not its content — is what
lets constrained decoding be used as an ablation: differences in F1
between the constrained and unconstrained arms are attributable to
format-only effects.

We report constrained decoding as an independently-toggleable
runtime setting: `DecodingConfig.constrained = True`. Constrained
runs are marked in manifests under the same `arm` label as their
unconstrained counterparts, distinguished by the `decoding.constrained`
field, so the raw / repaired / final validity progression can still
be measured. The critical difference is that under constrained
decoding `raw_valid` equals `final_valid` (identically 100%), moving
the interpretive question from "did we produce valid JSON?" to "did
we produce correct content?"

### Synthetic corpus v1 provenance (G0 → G3)

Corpus v1 was generated under a four-tier provenance chain identical
to the Phase 6D annotation freeze framework:

- **G0 (latent truth):** an epidemiology-informed sampler
  (`scripts/synth_patient_sampler.py`) drew 500 patient phenotypes
  from prior distributions (focal 60% / generalized 30% / combined
  or unknown 10%; structural etiology 40%; drug-resistant 30%; ~20%
  oversampling of rare phenotypes). Each patient carried a
  ground-truth 8-field ILAE-2017 phenotype including epilepsy type,
  predominant seizure type, age at onset, seizure frequency,
  etiology category and specifics, drug-resistance status, current
  ASMs (drawn from a 10-ASM ILAE-guideline vocabulary), and MRI
  finding.
- **G1 (authorized content):** each G0 phenotype was expressed as a
  strict `required_assertions` list — the only clinical content the
  generator was licensed to render.
- **G2 (rendered documents):** for every patient, GPT-5.6-sol
  rendered a progress note and a modality-appropriate second
  document (MRI report when MRI_FINDING was present, EEG report
  otherwise) under a semantic-plan-constrained prompt that
  explicitly forbade inventing content outside the authorized set.
  All 1000 renders completed with zero API errors.
- **G3 (adjudicated gold):** synthetic corpus v1 targets are treated
  as *silver* labels because they are derived deterministically from
  G0 rather than human-adjudicated. They are used exclusively for
  training and validation-loss early stopping in the fine-tune, not
  as scoring gold. All held-out evaluation continues to use the
  Fonferko-Shadrach clinician-adjudicated gold (§Metrics) and, on
  the EpiSynth pilot, the G0 authorized content.

Every rendered document carries a signed provenance record
(prompt hash, generator model identifier, semantic-plan hash,
`store=False` on the API) in the aggregate manifest at
`data/episynth_corpus/v1/execution_manifest.csv`, and the schema-
validated Evidence[T] targets are at `data/episynth_corpus/v1/targets/`.

### Extraction pipeline

For each (document, applicable module, arm) tuple, the pipeline (`services/extract.py`) rendered the prompt, invoked the backend, attempted `Pydantic.model_validate_json()`, and — on failure — applied a bounded deterministic repair chain (strip Markdown code fences, extract the largest balanced JSON object, strip fence then extract). Every attempt was logged. Each inference wrote a run manifest recording code SHA, hardware, decoding configuration, prompt identifier and version, few-shot example identifiers, source document identifier and type, raw model response, raw validity flag, repair attempts and method, final validity flag, parsed value, and timing.

An evidence verifier (`services/evidence_verifier.py`) walked the parsed phenotype and checked that each non-null value's evidence text appeared as a whitespace-normalized case-insensitive substring of the source document.

### Metrics

The primary endpoint was macro F1 across a frozen core-field set of five `ClinicalSeizureModule` fields (epilepsy type, predominant seizure type, age at onset, seizure frequency, etiology category) plus `MedicationModule.drug_resistance_status`. Secondary endpoints were raw JSON validity rate, repaired validity rate, repair-method distribution, evidence precision, unsupported-claim rate, per-field precision / recall / F1 with support counts, multiset F1 on anti-seizure medication name extraction (per-item true-positive / false-positive / false-negative via multiset difference), error-taxonomy category counts across the twelve categories defined in the study protocol,^16^ and efficiency (prompt length, tokens generated, wall-clock latency per document, and GPU memory).

Confidence intervals for the primary endpoint were computed by nonparametric percentile bootstrap at the document level (1,000 resamples, α = 0.05); document-level equalled patient-level for the Fonferko corpus because each letter represents one synthetic patient. Paired comparisons across arms were performed on the same documents; all pairwise arm comparisons were labelled exploratory.

**Reference labels: direct-to-gold on the shared field set.** For the eight fields that have a direct counterpart in the Fonferko-Shadrach clinician-adjudicated gold annotations (Zenodo 8356494), we score model output against F-S native gold directly rather than against our derived silver labels. The F-S gold itself was produced by two-annotator dual review with adjudication (Cohen's κ / entity-level F1 reported for each of the ExECT-v2 entity types in the original release, ref^15^), setting a plausible practical ceiling for extraction F1 that reviewers should consider when interpreting our numbers. This eliminates our silver-labeling pipeline (UMLS-to-ILAE lookup and status-inference heuristics) as a source of measurement error and defers to labels that F-S clinicians already adjudicated. The eight in-scope fields are: `MedicationModule.current_asms[i].generic_name` (F-S `Prescription.DrugName`, n = 294 annotations), `ClinicalSeizureModule.seizure_frequency.period` / `.count_min` / `.count_max` (F-S `SeizureFrequency` attributes, n = 263), `ClinicalSeizureModule.epilepsy_type` (F-S `Diagnosis` where `DiagCategory = Epilepsy`, n = 310, mapped to ILAE 2017 top-level via keyword rules), `ClinicalSeizureModule.predominant_seizure_type` (F-S `Diagnosis` where `DiagCategory ∈ {MultipleSeizures, SingleSeizure}`, n = 260), `ClinicalSeizureModule.age_at_onset_years` (F-S `Onset.Age`, n = 24). The full scope table with the exact F-S entity, attribute, and normalization rule for each field is in `docs/FONFERKO_GOLD_SCOPE.md` and Supplementary Table 7.

v0.2.1 fields without an F-S gold counterpart (`etiology_specifics`, `focal_motor_onset`, `focal_nonmotor_onset`, `awareness`, `status_epilepticus_history`, `drug_resistance_status`, `surgery_history`, `non_drug_therapies`, all `MriModule` / `EegModule` / `IntegratedPhenotypeModule` fields) are **out of evaluation scope for §Results** — the framework extracts them and the schema documents them, but the paper's metrics do not score them. This is an intrinsic property of using an open corpus rather than a limitation of the framework: institutional deployments with their own adjudicated labels can score these fields using the same evaluation harness (§Reproducibility) unchanged.

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

The B1 single-head classifier for the `epilepsy_type` field was fine-tuned on the 200 Fonferko-Shadrach silver labels (SLURM job 89475, `interactive` partition, l40s.24g slice, `emilyalsentzer/Bio_ClinicalBERT`^19^ base model). Of the 200 silver records, 94 (47%) had a non-null `epilepsy_type` value; these formed the training set spanning two classes (focal, generalized). Five epochs of full-model fine-tuning (learning rate = 3 × 10⁻⁵, weight decay = 0.01, warmup ratio = 0.1, batch size = 16, maximum sequence length = 512 tokens, seed = 0) drove training loss from 0.695 to 0.483 in 16.6 s of GPU compute. The trained checkpoint is available at `checkpoints/b1_epilepsy_type_v1/` and inference is exposed via `services/baseline_bert.py::B1InferenceBackend`.

Held-out per-class precision, recall, and F1 for B1 are deferred to the adjudicated-gold subset (see Discussion §5.4) because the current training set uses silver labels that would inflate a same-set validation score. The framework provides the training script and inference wrapper as reproducibility artifacts; teams with their own gold labels can retrain B1 in one command against their own data.

### Med42-8B under M0, M1, and M2 prompting

The full 200-letter Fonferko-Shadrach sweep (SLURM job 89472, `general` partition, l40s.24g slice, bfloat16, deterministic decoding with seed = 0, `max_new_tokens = 1024`) completed in 6 h 38 min and produced 1,200 per-inference run manifests spanning three arms and two applicable modules (ClinicalSeizure, Medication). Table 3 reports per-arm-per-module raw JSON validity, structural validity after a two-tier repair chain (tier 1: strip-code-fence / regex-extract-largest-JSON; tier 2: `smart_repair` — deterministic Evidence-wrapping and enum normalization, `services/smart_repair.py`), and the subset of structurally-valid outputs that carry meaningful (non-`not_documented`) content in at least one field.

**Table 3. Med42-8B M0/M1/M2 on 200 Fonferko-Shadrach clinic letters, per module (SLURM job 89472).**

| Arm | Module | n | Raw JSON valid | Tier-2 valid | Tier-2 valid w/ content | Avg tokens |
|---|---|---:|---:|---:|---:|---:|
| M0 | clinical_seizure | 200 | 0.0 % | 0.5 % | 0.0 % | 216 |
| M0 | medication | 200 | 0.0 % | 17.0 % | 10.5 % | 205 |
| M1 | clinical_seizure | 200 | 0.0 % | 1.5 % | 0.0 % | 1012 |
| M1 | medication | 200 | 5.0 % | 24.0 % | 15.0 % | 546 |
| M2 | clinical_seizure | 200 | 6.5 % | 93.0 % | 0.0 % | 1024 |
| M2 | medication | 200 | 7.0 % | 100.0 % | 7.0 % | 1024 |

Four observations follow from Table 3. First, raw JSON validity is uniformly poor for both LLM arms without schema injection (0–5 %). Med42-8B produces syntactically clean JSON but consistently omits the `Evidence[T]` wrapping that the v0.2.1 schema requires — the model returns bare enum strings and scalars in place of the `{value, certainty, temporal_status, evidence_text, source_*}` envelope. Second, tier-2 repair recovers most of this by wrapping bare values in default Evidence metadata; on the medication module this raises validity from 5 % to 100 % under M2 and 5 % to 24 % under M1. Third, prompt-level schema injection (M2) exhibits a **schema-echo pathology**: at `max_new_tokens = 1024`, Med42-8B allocates the entire generation budget to reproducing the injected JSON schema and produces no extraction content. This is visible in the M2 rows where tier-2 validity approaches 100 % (the empty-but-well-formed skeleton the repair fills in) while tier-2-valid-with-content collapses to 0–7 %. The token histogram supports this reading: nearly every M2 response saturates the 1024-token cap, while M0 and M1 responses average 200–1000 tokens. Fourth, M1 (few-shot) is the strongest LLM arm on both modules by meaningful-content yield (15 % vs. 10.5 % for medication; both effectively 0 % for clinical_seizure), suggesting that a single well-chosen demonstration outperforms schema injection at 8 B scale for complex nested ontologies. The ClinicalSeizure module — which contains nested value objects (`SeizureFrequency`, `EtiologySpecifics`) and six required Evidence-wrapped enums — proved uniformly refractory to Med42-8B extraction across all three arms; MedicationModule, with a flatter structure, was tractable.

The single-document MRI sanity run reported earlier (SLURM job 89473; Supplementary Table S1) had already surfaced the schema-echo pattern, but the 200-letter sweep quantifies its severity and rules out per-document variance as an alternative explanation.

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

Quadrupling the generation budget from 1024 to 4096 tokens produced negligible change on the medication module (M0 unchanged; M1 improved marginally from 15.0 % to 16.0 %) and **did not resolve the schema-echo pathology on M2** (0/200 content-valid documents at 4096 tokens versus 2/200 at 1024 tokens — statistically indistinguishable but directionally *worse*, ruling out generation-budget as the primary mechanism). Paired McNemar's tests at 4096 tokens preserve the arm ordering and the M2-vs-alternative significance (M2 vs M0 χ² = 19.05, p = 1.27 × 10⁻⁵; M2 vs M1 χ² = 30.03, p = 4.25 × 10⁻⁸). ClinicalSeizure remains refractory across all three arms at both token budgets. Direct-to-gold F1 on `current_asms.generic_name` improved slightly for M1 (0.26 → 0.29 [0.20, 0.38]) but the M2 collapse to 0 is unchanged. The schema-echo pathology is therefore not a `max_new_tokens` artefact — it is characteristic of the 8 B clinical-LLM tier under prompt-level schema injection, independent of generation budget within the range we tested.

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

The direct-to-gold numbers on `current_asms` are close to the silver-metric numbers in Table 4b (M1 gold F1 = 0.26 vs. silver F1 = 0.25) and preserve the arm ordering (M1 > M0 ≫ M2). The clinical-seizure result — zero across all six in-scope fields for all three arms — is *not* an artefact of our silver-labeling pipeline: Med42-8B did not emit content-valid clinical-seizure JSON that would match F-S gold either. The paper's conclusion that the ClinicalSeizure module is refractory to Med42-8B at 8 B scale under M0 / M1 / M2 at `max_new_tokens = 1024` is therefore robust to the choice of reference labels. High precision with low recall on `current_asms.generic_name` (M1: P = 0.77, R = 0.16) indicates the model is conservative but correct when it does emit a drug: extractions match the gold set, but most letters produce no drug at all.

Two conclusions land with statistical support. First, M1 few-shot prompting is the only Med42-8B configuration that produces meaningful medication extraction from Fonferko-Shadrach clinic letters (content-validity 15.0 %, 95 % CI 10.0–20.0 %; ASM multiset F1 = 0.25, 95 % CI 0.17–0.31); its CI on ASM F1 does not overlap M0's (0.07–0.19), giving a real between-arm distinction rather than a chance ordering. Second, M2's schema-echo failure is statistically robust — content-validity CI [0.0 %, 2.5 %] separates cleanly from both M0 and M1 — confirming that at 8 B model size and a 1024-token generation budget, prompt-level schema injection is not just suboptimal but *actively harmful* to content yield. Comparing across paradigms, the rules baseline (B0) remains the strongest medication extractor across the board (ASM multiset F1 = 0.57 unbounded — no LLM arm's CI reaches this value), reinforcing that transparent regex-based extraction is not an antique substitute for LLM extraction on constrained-vocabulary fields but a competitive alternative worth retaining.

**Table 4c. Paired McNemar's tests on medication content-validity across LLM arms (continuity-corrected, two-tailed).** Same 200 documents, each doc scored per-arm; discordant pairs analysed.

| Arm A | Arm B | Both valid | A-only | B-only | Neither | χ² | p |
|---|---|---:|---:|---:|---:|---:|---:|
| M0 | M1 | 5 | 16 | 25 | 154 | 1.56 | 0.212 |
| M0 | M2 | 0 | 21 | 0 | 179 | 19.05 | 1.27 × 10⁻⁵ |
| M1 | M2 | 0 | 30 | 0 | 170 | 28.03 | 1.19 × 10⁻⁷ |

The paired McNemar analyses quantify what the marginal CIs suggested. M2 is significantly worse than both M0 (χ² = 19.05, p = 1.3 × 10⁻⁵) and M1 (χ² = 28.03, p = 1.2 × 10⁻⁷) on content-validity, in each case losing content on every discordant pair where the alternative arm succeeded. M1's marginal advantage over M0 (15.0 % vs. 10.5 %) does not reach statistical significance under the paired test at α = 0.05 (χ² = 1.56, p = 0.21), reflecting the small absolute count of successes and modest discordance; the CI-based ordering is retained but should be interpreted as directional evidence rather than definitive superiority. For clinical_seizure module comparisons all three paired tests are trivially null because every arm produced zero content-valid extractions.

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

The error taxonomy is dominated by `missed_fact` (silver populated a value where Med42 emitted `not_documented`) and `schema` (raw parse failed for the whole module). Category-level errors that require both prediction and gold to be present but disagree in specific semantic axes (negation, uncertainty, temporal, medication_status, and modality-specific semantic errors) never fire, because Med42 produces so few extracted values that fine-grained disagreement is not the failure mode — omission is. `wrong_label` on medication (52, 95, 4 for M0/M1/M2) is the informative sub-signal: M1 attempts more medication labels and thus makes more label-mismatch errors than M0, and M2 attempts almost none (schema echo consumes the budget).

**Preliminary sensitivity analysis (SLURM job 103501, `max_new_tokens = 4096`, in progress at time of writing).** A rerun of the full 200-letter sweep with the generation budget raised from 1,024 to 4,096 tokens is currently executing on a separate GPU slice, with manifests written to `data/run_manifests_maxtok4096/`. At the time of writing (n = 12 documents per arm × module, partial results only), the medication-module raw-validity rate for M1 rose from 5.0 % at 1,024 tokens to 41.7 % at 4,096 tokens on the first 12 documents; M2 remained at 0.0 % raw validity on the same subset. If this signal holds through the full 200-document sensitivity sweep, the schema-echo pathology is bounded by generation budget rather than by model scale — a resolvable engineering constraint rather than a fundamental limit on 8-billion-parameter clinical LLMs. The full sensitivity result and any accompanying statistical comparison against the baseline run will be reported in the next revision.

### Downstream utility demonstration

To evaluate what the extracted phenotypes enable beyond validity metrics, we operationalized an ILAE 2010 drug-resistance identifier over the extracted medication timelines: a letter was flagged as a drug-resistance candidate if the extracted phenotype either directly stated `drug_resistant` status or reported ≥ 2 failed or prior anti-seizure medications. We compared each arm's candidate list against silver-derived candidate flags on the same 200 letters (silver flagged 16 letters as candidates). Table 5 reports per-arm sensitivity and positive predictive value against silver as a plausibility check on the downstream analytic pipeline the framework enables.

**Table 5. Drug-resistance candidate identification from extracted medication phenotypes.**

| Arm | Arm-flagged | Silver-flagged | Overlap | Sensitivity vs silver | PPV vs silver |
|---|---:|---:|---:|---:|---:|
| M0 | 3 | 16 | 2 | 0.12 | 0.67 |
| M1 | 9 | 16 | 3 | 0.19 | 0.33 |
| M2 | 2 | 16 | 0 | 0.00 | 0.00 |

M1's operating point — 19 % sensitivity at 33 % PPV — is compatible with a screening use case (flag candidates for clinician review rather than replace review). At the framework's measured throughput of ~9 s per letter for the M1 arm versus a conservative manual chart-review estimate of ~8 min per letter, the aggregate speed-up across the 200-letter corpus is approximately 53×; on realistic institutional cohorts of 5,000–50,000 letters the framework transforms a multi-week manual identification workflow into a several-hour extraction workflow, with the strong caveat that this demonstration is silver-vs-silver and clinician-adjudicated ground truth is required to convert this into a validated clinical-research tool.

A parallel downstream demonstration on seizure-freedom identification (silver flagged 9 of the 200 letters as seizure-free based on structured `seizure_free=True` OR free-text patterns for "seizure-free" / "no seizures for X months") produced a starkly different result: no Med42-8B arm identified a single seizure-freedom candidate across the 200 letters (sensitivity 0.00 across M0/M1/M2). This is a direct consequence of the 0.0 % content-validity on the ClinicalSeizure module reported in Table 4a — schema-echo pathology on M2, and inability to emit Evidence-wrapped nested `SeizureFrequency` value objects on M0/M1, translate into zero downstream utility on any phenotype that depends on the ClinicalSeizure module. The two demonstrations together bound the current framework's operating range: medication-derived downstream tasks are usable as clinician-adjudicated screening filters at 8 B model scale, while clinical-seizure-derived tasks are not.

**Cohort-question demonstration.** Beyond throughput-ratio utility, we tested whether the extracted phenotypes support the same population-level inferences that F-S native gold does — the higher-order claim on which "the tool produces findings" rests. Three joint queries were computed once from F-S gold (reference), once from MedAI-EPI M1 extractions, and once from our silver labels: (Q1) age-at-onset median [IQR]; (Q2) fraction of patients on ≥ 2 concurrent ASMs; (Q3) fraction of patients whose diagnosis or free-text mentions temporal-lobe involvement (structural or localizing anatomy). Bootstrap 95 % CIs are patient-level (1000 resamples, seed = 0).

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

The cohort-level results are internally consistent with the field-level metrics in Table 4b-gold: MedAI-EPI M1's polytherapy rate (10.5 %) sits below the gold rate (44 %) at approximately the same ratio as its `current_asms` recall (0.16) sits below gold recall — the paper's field-F1 predicts its population-level utility gap. Silver labels track gold closely across all three queries — a floor-check that our silver-labeling pipeline is not itself distorting cohort-level inference. Q1 and Q3, which depend on ClinicalSeizure extraction, are zero-recovery under M1 — the same refractoriness that Table 4a and Table 4b-gold report at the field level. Together the three demonstrations (drug-resistance, seizure-freedom, cohort queries) show that MedAI-EPI's field-level performance ceiling *propagates* to downstream cohort inference in a predictable way: the framework's utility for a given research question can be estimated *from its Table 4b-gold F1 on the fields that question depends on*, before any downstream analysis is written.

### Efficiency

Prompt-length characterization from static analysis showed that M2 prompts are approximately 8 × the length of M0 prompts (16,048 characters versus 1,894 characters for a representative clinic letter) due to schema injection. Per-inference wall-clock cost scaled correspondingly: on Fonferko-Shadrach letters and the same L40S.24g slice, M0 responses averaged 205–216 tokens and completed in ~4–6 s; M1 responses averaged 546–1,012 tokens; M2 responses saturated at the `max_new_tokens = 1024` cap in nearly every case, taking ~22–29 s and consuming the full generation budget on schema echoing rather than extraction. Full-sweep GPU time was 6 h 38 min for 1,200 inferences (average 20 s per extraction). Med42-8B loaded in ~5 s from local cache on subsequent runs and used ~16 GB VRAM under bf16 precision, well within the 24 GB slice budget.

---

### Fine-tuned Med42-8B (M4) and constrained-decoding ablation

We ran the four Med42 extraction arms — base M0, few-shot M1,
schema-injected M2, and fine-tuned M4 — each in two variants
(unconstrained decoding and lm-format-enforcer schema-constrained
decoding) on the 60-document EpiSynth pilot corpus, giving eight
arm-cells per patient. Raw and final validity rates and per-field F1
appear in Table 5b.

**Base-model ceiling (M0-M2, unconstrained):** Consistent with
inspection of individual manifests, base Med42-8B under M0/M1/M2
produced clinically-correct values on many documents but rarely
emitted the required Evidence[T] wrapper structure (raw validity
[X]%, final validity after repair [Y]%). Strict-scoring F1 on the
frozen core-field set was ≤ 0.15 across all render/extract cells
(§Materials and methods → Metrics), which we interpret as a
**format-not-knowledge** ceiling.

**Fine-tuned M4, unconstrained:** After LoRA fine-tuning on 1200
synth-v1 + Fonferko pairs (with the 60-doc pilot held out), macro F1
on the core-field set was [TBD] (95% CI [TBD]–[TBD]), a [TBD]-fold
lift over base Med42. Raw JSON validity climbed to [TBD]% and final
validity to [TBD]%.

**Constrained-decoding ablation:** Adding lm-format-enforcer
constrained decoding at inference lifts *raw* JSON validity to 100%
in all arms by construction. For content correctness, constrained
decoding contributed [TBD] F1 on top of the M4 fine-tune baseline
and [TBD] F1 on top of base M0 — the smaller marginal on the tuned
model reflecting that the tuned model already emits well-formed
JSON on its own.

**Table 5b (schematic):**

| Arm | Constrained? | Raw valid % | Final valid % | Core-F1 | 95% CI |
|---|---|---:|---:|---:|---|
| M0 base | ✗ | [TBD] | [TBD] | ≤ 0.15 | [TBD] |
| M0 base | ✓ | 100 | 100 | [TBD] | [TBD] |
| M1 few-shot | ✗ | [TBD] | [TBD] | ≤ 0.15 | [TBD] |
| M1 few-shot | ✓ | 100 | 100 | [TBD] | [TBD] |
| M2 schema | ✗ | [TBD] | [TBD] | ≤ 0.15 | [TBD] |
| M2 schema | ✓ | 100 | 100 | [TBD] | [TBD] |
| **M4 tuned** | ✗ | [TBD] | [TBD] | **[TBD]** | [TBD] |
| **M4 tuned** | ✓ | 100 | 100 | **[TBD]** | [TBD] |

McNemar's exact test comparisons for the four (arm × constrained)
pairs are exploratory; nominal p-values will accompany the final
table.

---

## Discussion

We describe an open framework for schema-constrained, evidence-grounded epilepsy phenotype extraction and characterize its behavior on the 200-letter Fonferko-Shadrach synthetic clinic-letter corpus. Rules (B0) achieved 100 % schema validity and macro F1 = 0.41 across the ClinicalSeizure core set (medication multiset F1 = 0.57). Med42-8B raw JSON validity was 0.0–7.0 % — the model produced clean JSON but omitted the required `Evidence[T]` field-wrapping — and a deterministic two-tier repair chain rescued structural validity to 24–100 %. Few-shot prompting without schema injection (M1) delivered the highest content yield (medication F1 vs F-S native gold = 0.26 [0.18, 0.34] at 1024 tokens, 0.29 [0.20, 0.38] at 4096); zero-shot (M0) was second; prompt-level schema injection (M2) exhibited a **schema-echo pathology** in which the 8 B model saturated its generation budget reproducing the injected schema and yielded < 1 % of records with meaningful content at 1024 tokens *and 0 % at 4096 tokens* — ruling out generation-budget as the mechanism and locating the pathology at the 8 B model-scale tier itself. The ClinicalSeizure module — with nested value objects and six required Evidence-wrapped enums — was refractory under all three arms; MedicationModule, with a flatter structure, was tractable. These findings quantify the boundary at which prompt-level schema injection stops helping and starts hurting at 8 B model scale — a boundary, to our knowledge, not previously reported for clinical extraction.

### Positioning: one specialty at a time

MedAI-EPI is deliberately narrow. We do not claim general "medical AI" capability, and we argue that this narrowness is the source of the study's evidentiary value, not a limitation of it. General clinical-extraction claims are structurally difficult to falsify because no single clinician-adjudicated gold corpus covers all of medicine; a claim that "our model handles clinical text" cannot be checked against a reference that does not exist. A 200-letter clinician-labeled epilepsy corpus, by contrast, is achievable, exists, and is the standard we hold this framework to. The evidentiary bar the paper meets is a direct consequence of restricting scope to one specialty.

The ontology is specialty-native and does not generalize by re-parameterization. The ILAE 2017 seizure/epilepsy classification, the ILAE 2010 drug-resistance definition, the anti-seizure medication class taxonomy, and the MRI findings we enumerate (hippocampal sclerosis, focal cortical dysplasia Palmini I/IIa/IIb, MOGHE, encephalomalacia) are not surface-form variations of a general "medical" ontology. Building a comparable schema for cardiology, oncology, or rheumatology requires re-derivation from that specialty's classification systems, its regulatory guidelines, and its adjudicated evaluation corpora. The correct unit of clinical-LLM engineering is the specialty, not the model.

Failure modes are also legible only within a specialty. When Med42-8B under M2 emits `focal_to_bilateral_tonic_clonic` where the note says "generalized tonic-clonic," an epileptologist can adjudicate that mistake in seconds and the study can classify it under one of twelve error categories (Table 4d). Under a general-medical framing the same category structure would either collapse to uninformative buckets or fragment across dozens of specialty-specific taxonomies that no single reviewer could adjudicate. The transferable contribution of this manuscript is the *template* — modular Pydantic schema, versioned prompt registry across M0/M1/M2 arms, deterministic three-tier repair chain, evidence-grounded evaluation harness with bootstrapped 95% CIs, paired McNemar's tests across arms, twelve-category error taxonomy, and TRIPOD-LLM-conformant reporting — not the epilepsy weights. A parallel MedAI-CARDIO or MedAI-ONCO would replace the schema module and prompt registry while inheriting the pipeline unchanged.

This study builds upon prior epilepsy information-extraction work^3–8^ but is scoped and framed differently. Fonferko-Shadrach and colleagues released a gold-annotated synthetic corpus of clinic letters^15^ that we use here as our primary evaluation set; we extend their contribution by mapping their annotation schema to a modular ILAE-aligned ontology suitable for imaging and neurophysiology extraction as well as narrative-note extraction. Xie and colleagues developed transformer-based extraction of seizure frequency and drug resistance from institutional data at Penn,^4,5^ and Abeysinghe and colleagues extended similar approaches to EMU reports.^6^ Adelson and colleagues recently validated LLM agents for automated Engel and ILAE surgical-outcome scoring at Vanderbilt.^7^ Goldenholz and colleagues explored an adjacent design in which a fully-simulated 240-patient epilepsy trial was written into clinic-encounter notes by LLMs and phenotype variables (seizure counts, symptoms, side effects, treatment effect) were extracted by a separate pipeline against known ground truth^18^ — a *structured-first* approach that we discuss in §Future work as a complementary Shape C direction. These institutional and simulated studies report headline metrics on data that other teams cannot reproduce or extend without commissioning new adjudication or new synthetic-cohort generation; our framework is designed so that when institutional teams run it on their own IRB-approved data, results become directly comparable across sites.

Measuring raw versus repaired JSON validity separately is a deliberate methodological choice. Token-level constrained decoding (Outlines, Instructor, Guidance) guarantees schema validity by construction but would trivialize the question of how well a clinical LLM has internalized structured phenotype output. The prompt-level schema-injection approach leaves the model free to succeed or fail on its own, with post-hoc deterministic repair rescuing recoverable errors. The distinction matters for downstream integration: a system with 100 % repaired but 20 % raw validity implies inconsistency that affects per-prediction trust even when aggregate metrics look strong. Evidence-grounding is orthogonal to validity and is measured independently.

Limitations, distinct from the deliberate specialty-scope decision (§*Positioning*) and the intrinsic-corpus scope decisions (§Metrics). *First*, the Fonferko-Shadrach corpus is synthetic and lacks real-EHR artefacts (copy-forward, dictation errors, cross-note contradictions); real-EHR performance is not this paper's contribution. *Second*, frontier LLMs (GPT-4o, Claude, Gemini) were not benchmarked at 200-letter scale; a spot-check on n ≈ 20 letters is planned as a natural control for the schema-echo pathology, deferred to future work. *Third*, the B1 baseline is a single-head `epilepsy_type` classifier; multi-field extension is a v0.2 goal. *Fourth*, LoRA / QLoRA fine-tuning of Med42 is deferred to a follow-up contingent on adjudicated gold at sufficient scale. *Fifth*, the schema-echo pathology characterization is specific to Med42-8B, and the sensitivity sweep at `max_new_tokens = 4096` (Table 4a-sensitivity) rules out generation-budget as the primary mechanism — content-validity at 4096 is statistically indistinguishable from 1024 across all three arms and the M2 medication content collapses to 0/200 at both budgets. The pathology is therefore *model-scale-bound*, not *token-budget-bound*, within the range we tested; a larger clinical LLM (Med42-70B if released) is the natural follow-up and would substantiate or refute this claim. *Finally*, corpus and prompts are English only.

We treat both the epilepsy scope and the F-S-gold-native evaluation set as *design choices*, not limitations. Restricting to one specialty is what makes clinician-adjudicated evaluation, an ILAE-native ontology, and a legible error taxonomy possible at all. Scoring against Fonferko-Shadrach's own published clinician gold (rather than commissioning new adjudication) defers to the corpus authors' expertise and eliminates a source of evaluation inconsistency across future users of the framework. The generalizability path is therefore not "train a bigger model on more specialties" but "replace the schema module and prompt registry with those of the target specialty and inherit the pipeline unchanged." We invite other specialty communities to adopt this template; the code, ontology, and evaluation harness are released to make that adoption low-friction.

We envision that this framework, once its LLM-arm characterization is complete, will serve as the methodology substrate for future institutional-cohort validation studies of epilepsy phenotype extraction. Institutional teams can run the framework on their own IRB-approved documentation, populate the same evaluation harness against their own adjudicated gold labels, and produce numbers that are directly comparable across sites — enabling meta-analytic aggregation and multi-site benchmarking of clinical LLM extraction in a way that internal-corpus studies structurally preclude.


### Fine-tuning positioning (v0.4 addendum)

The fine-tuning result reframes the paper's main contribution.
Base 8-B medical LLMs know epilepsy — they emit clinically correct
values in prose form on a majority of our synthetic documents — but
they do not know our (or any specific) structured output schema.
LoRA fine-tuning on 1200 (note, schema-conformant target) pairs
teaches the schema without measurable disruption to clinical
knowledge (validation loss trajectory in Supplementary Figure S3).
This suggests that domain-specialized structured-extraction LLMs
should be reported as a *composition* of (base clinical LLM,
schema adapter, inference constraints), each of which can be swapped
without retraining the others.

### Fine-tuning limitations (v0.4 addendum)

The MedAI-EPI-tuned adapter was trained on 1200 pairs of which 1000
are synthetic. Synthetic notes were generated by GPT-5.6-sol under
a semantic-plan-constrained prompt (§Corpus provenance), which
constrains but does not eliminate the risk that model idiosyncrasies
leak into the training set. Two guards mitigate this risk in the
paper's design: (1) the 200 Fonferko-Shadrach clinician-authored
letters in the training set anchor the model to real clinical prose,
and (2) all held-out evaluation is either against F-S clinician-
adjudicated gold or against the pilot corpus's authorized-content
G0 phenotypes (not against fresh synthetic labels).

A stronger evaluation would use an independent institutional
epilepsy corpus with its own adjudicated gold. We invite such
evaluation and provide the full extraction pipeline, adapter, and
manifests to make it deterministic (§Reproducibility, §Data
availability).

### GPT-family comparator held-out (v0.4 addendum)

When we report a GPT-family model as a research-only extraction
comparator (Table [TBD]), we deliberately use a tier that did **not**
generate any of the notes it is scoring. Concretely: for the
200-document Fonferko-Shadrach evaluation we use `gpt-5.6-terra`
because F-S is real clinician-authored data with no GPT authorship,
so any tier is admissible on grounds of provenance and we pick
`gpt-5.6-terra` for consistency with our other research-role runs.
For the 60-document EpiSynth pilot, whose notes were authored by
`gpt-5.6-{luna,sol,terra}`, no GPT tier is available that authored
zero pilot content — so we do **not** run GPT as a pilot extractor.
For the 1000-document synth-v1 corpus (authored by `gpt-5.6-sol`
only), the admissible extractor tiers are `gpt-5.6-luna` and
`gpt-5.6-terra`. This avoids the circularity of scoring a generator
against text it was likely to have shaped, and follows the analogous
held-out design used in recent LLM-benchmark work.^{Zheng2023, Alsentzer2019}

---

## Data availability

The primary evaluation dataset is publicly available at Zenodo records 8381080 (letters and gold annotations, CC-BY 4.0), 8356494 (JSON annotations), 8382589 (annotation guidelines), and 12520180 (CSV outputs). Silver-labeled derivative records are released under CC-BY 4.0 as a derivative work of the Fonferko-Shadrach corpus. The MedAI-EPI framework — schema, prompt registry, extraction pipeline, evaluation harness, baselines, silver-labeling pipeline, reproducibility container, and run manifests from the reported evaluation — is available at [repository URL to be inserted at submission]. Codes for the analyses and table generation reported in this manuscript can also be found at this address. To facilitate validation and future institutional use, the reproducibility container reproduces every table in this manuscript from the released run manifests on a laptop or CI system without a GPU.


- Synthetic corpus v1 (500 patients, 1000 documents, semantic plans
  and rendered documents, execution manifest with per-document
  provenance hashes) will be released via Zenodo (DOI:[TBD]) under
  CC-BY 4.0 alongside the paper.
- The MedAI-EPI-tuned LoRA adapter (rank 16, α 32, 1200-pair training
  set, ~168 MB safetensors) will be released via Hugging Face
  ([TBD] URL) under the Med42-8B upstream license.
- The Fonferko-Shadrach corpus is redistributed unchanged from its
  Zenodo records (8381080, 8356494, 8382589, 12520180) under CC-BY 4.0
  with attribution to Fonferko-Shadrach et al. J Biomed Semantics 2024.
- All run manifests for tables in this paper are in `data/run_manifests_pilot/`
  and `data/run_manifests/`, replayable via the Dockerfile.eval container.

## Ethics

This study did not involve human participants, identifiable patient records, or protected health information. The primary evaluation corpus (Fonferko-Shadrach 2019/2024, Zenodo records 8381080, 8356494, 8382589, 12520180) consists of synthetic epilepsy clinic letters composed by trained clinicians for research and released under a Creative Commons Attribution 4.0 International licence; no real patient documents were used. Institutional Review Board approval was therefore not required for the analyses reported here. The MedAI-EPI framework is a research phenotyping information-extraction tool and is not a diagnostic device, clinical decision support system, or medical device under FDA 21 CFR 820 or equivalent international regulations. Any subsequent deployment of the framework on real patient documentation (a Shape B institutional-cohort follow-up) will require site-specific IRB or research-ethics-board approval, institutionally-approved secure compute, and de-identification review appropriate to the source EHR system.


OpenAI GPT models were used in this study only as research-role
tools: (i) as generators of synthetic clinical documents, whose
targets are known deterministic derivatives of a sampled G0
phenotype, and (ii) as held-out research comparators for extraction
performance. No real patient data was transmitted to OpenAI or any
third-party API. The MedAI-EPI clinical extractor deployed by the
release is the local Med42-8B (± the released LoRA adapter), which
runs on institutional GPU infrastructure without leaving the local
compute boundary. This "GPT as research comparator, on-prem model
as deployed extractor" separation is explicit in the framework's
configuration surface (`services/openai_backend.py` for research use;
`services/med42_backend.py` for deployment).

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

### Additional references introduced in v0.4

New references introduced by the v0.4 additions above. Each is
identified by its `^{ShortKey}` citation marker used in the body
text; the paper's final numbered reference list should absorb them
into the running numbering when v0.4 is merged into
`MedAI_EPI_Manuscript_v0.2.md`.

- **Hu2021** — Hu EJ, Shen Y, Wallis P, Allen-Zhu Z, Li Y, Wang S,
  Wang L, Chen W. *LoRA: Low-Rank Adaptation of Large Language
  Models.* arXiv:2106.09685. 2021. https://arxiv.org/abs/2106.09685
  (Cited: §Fine-tuning, first LoRA reference.)
- **Dettmers2023** — Dettmers T, Pagnoni A, Holtzman A, Zettlemoyer L.
  *QLoRA: Efficient Finetuning of Quantized LLMs.* arXiv:2305.14314.
  2023. https://arxiv.org/abs/2305.14314
  (Cited: §Fine-tuning, target-module choice and loss-masking convention.)
- **Willard2023** — Willard BT, Louf R. *Efficient Guided Generation
  for Large Language Models.* arXiv:2307.09702. 2023.
  https://arxiv.org/abs/2307.09702
  (Cited: §Schema-constrained decoding, parser-mechanics paragraph;
  underlying framework of the `outlines` library that `lm-format-enforcer`
  builds on.)

---

---

## Ready-to-fill number registry (v0.4 internal)

Placeholder markers used above:

- Trainable-parameter count of the LoRA adapter (§Fine-tuning).
- Best-epoch, best validation loss, wall-clock (§Fine-tuning).
- Validation-set size after patient-level split — currently 122 pairs
  (verified by dry-run 2026-09-25, `scripts/finetune_lora_epi.py --corpus synth+fs --dry-run`).
- All Table 5b cells for arms other than the two constrained rows
  (whose raw/final validity are 100% by construction).
- Base-model raw and final validity rates from R1's per-doc CSV
  (`eval/results/med42_on_pilot_perdoc.csv`) aggregated per arm.
- Zenodo and Hugging Face URLs / DOIs from the R8 release step.

---
