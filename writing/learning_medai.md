# learning_medai — MedAI-EPI session teaching document

**Purpose.** A guided walk-through of every substantive task performed in the MedAI-EPI session, framed as a teaching artifact rather than a diary. Each section names the *problem*, the *concept that solves it*, the *implementation pattern*, and *why the choice was made over alternatives*. Read top-to-bottom for the full arc; use the Table of Contents to dip into a specific topic.

## Table of Contents

1. Project context and framing decisions
2. Domain theory
3. Schema engineering (Pydantic v2)
4. Data provenance and open-corpus strategy
5. Prompt engineering as versioned artifacts
6. Extraction pipeline design (validate → repair → log)
7. Evidence grounding as a first-class metric
8. Baselines: rules (B0), BERT (B1), Med42 (M0–M2)
9. Evaluation harness (metrics, error taxonomy, bootstrap CI)
10. Reproducibility engineering (manifests, container, registries)
11. HPC / SLURM engineering
12. Debugging methodology
13. Programming concepts as applied
14. Session-specific decisions and their rationale
15. What is NOT done and why
16. LLMs, generative AI, prompt engineering, and fine-tuning — beginner to mastery (Med42-8B as running example)

---

## 1. Project context and framing decisions

**Starting state.** The repository was a general-purpose "MedAI Medical Analysis Platform" — a Flask + Med42-8B service exposing a `/analyze` endpoint that produced free-text summaries across cardiology, neurology, psychiatry, and emergency specialties. The pre-existing `paper_doc/` held two authored planning documents (a full Paper 1 blueprint and a literature review guide) that scoped a formal retrospective clinical NLP validation study of epilepsy phenotyping across heterogeneous documents.

**Pivot.** The general platform was narrowed to **MedAI-EPI**, an *epilepsy-specific research phenotyping assistant*. The word "research phenotyping assistant" is load-bearing: the paper protocol (§21) explicitly forbids diagnostic framing. Every user-facing string, prompt, and header was retrained on this language. "AI expert" was rejected as framing because it implies autonomous clinical judgment, which invites regulatory scrutiny and is scientifically indefensible.

**Two-shape strategy.** Recognizing that the full institutional cohort study (Shape B in the blueprint) is gated by IRB, corpus pull, annotator recruitment, and 3–6 months of adjudicated annotation, we defined an open-corpus-only **Shape A** methodology paper that de-risks and precedes Shape B. Shape A uses Fonferko-Shadrach 2024 + TUH EEG Corpus + PMC case reports — everything publicly available.

**Why this matters conceptually.** *Framing is a load-bearing engineering decision.* Once "MedAI-EPI is a diagnostic tool" is written anywhere in the codebase, reviewers hold the paper to that claim; regulatory posture becomes ambiguous; users interpret extracted values as diagnoses. Getting framing right in commit 1 avoids retroactive edits across dozens of files. The corresponding engineering discipline: every prompt template, README, disclaimer, HTML title, and error message says "research phenotyping" or "structured extraction", never "diagnostic support".

---

## 2. Domain theory

### 2.1 Why epilepsy phenotype extraction from text is hard

Structured phenotype variables — seizure type, epilepsy type, medication history, drug-resistance status, imaging findings, surgical outcomes — are the analytic substrate for retrospective cohort studies, genotype-phenotype correlation, drug-response research, and multimodal models over raw EEG/MRI. But they live in unstructured clinical text spread across MRI reports, EEG reports, progress notes, EMU discharge summaries, presurgical evaluations, surgery-conference notes, and procedure documentation.

Three complications:
- **Documentation heterogeneity.** Different note types cover different subsets of the phenotype. MRI reports have imaging findings but no medication history. Progress notes have semiology + drug list but usually not imaging.
- **Vocabulary drift.** ILAE 2017 replaced "complex partial" with "focal impaired-awareness", but older notes still use the earlier vocabulary.
- **Copy-forward artifacts.** EHR notes contain propagated content that may be years out of date; the same phrase can appear in ten notes but mean today's status in one and last year's status in another.

### 2.2 ILAE 2017 and 2010 as controlled vocabularies

The International League Against Epilepsy publishes two classifications that anchor the schema:
- **2017 seizure and epilepsy classification** (Fisher et al.) — six focal motor-onset subtypes, five focal non-motor-onset subtypes, distinct focal / generalized / combined / unknown epilepsy types.
- **2010 drug-resistance definition** — failure of two tolerated, appropriately-chosen, adequately-trialled anti-seizure medications to achieve sustained seizure freedom.

These are not just labels; they define the *ground truth* against which extraction is scored. Deviating from ILAE means the paper cannot cite prior work directly and reviewers reject it. Our `SeizureType`, `EpilepsyType`, `DrugResistanceStatus`, and `FocalMotorOnset` enums map 1:1 to the ILAE nomenclature.

### 2.3 Silver labels vs. gold labels

**Gold**: adjudicated by clinicians, ideally with inter-rater agreement and a documented adjudication log. Expensive, requires IRB, is the currency of clinical NLP publications.

**Silver**: automated or heuristic labels derived from partial gold via a mapping layer, or from a labeled corpus that is not native to your schema. Cheap, imperfect, disclosable — and *unblocks* development that would otherwise wait for gold.

We used silver labels three ways:
1. To convert Fonferko-Shadrach 2024's ExECT-v2 entity annotations into partial `EpilepsyPhenotype` records using `scripts/silver_label_fonferko.py`.
2. To seed B1 (BioClinicalBERT) training before institutional gold arrives.
3. To provide a *dev signal* for M0/M1/M2 prompt iteration.

Silver labels are **not** headline metrics. Any per-field F1 reported against silver in the manuscript is prefixed with "silver-metric" and disclosed in Limitations §5.4.

### 2.4 Evidence grounding

A clinical extraction system that emits `predominant_seizure_type: focal_impaired_awareness` without pointing at the source text is fundamentally auditless. A reviewer, a clinician, or another researcher cannot verify the extraction is a *reading* of the document rather than a *guess* from the model's prior.

**Solution**: every non-null value carries a verbatim minimal-sufficient quote from the source document. Two properties become measurable:
- **Evidence precision** — of all evidenced claims, what fraction has a quote that actually appears in the source (whitespace-normalized, case-insensitive substring)?
- **Unsupported claim rate** — 1 − evidence precision. This is the "hallucination rate" specific to information extraction.

The `Evidence[T]` type in `schema/evidence.py` enforces this at the schema level: value present ⇒ non-empty evidence_text required; value None + `certainty=not_documented` ⇒ evidence_text must also be None.

### 2.5 Bootstrap confidence intervals at patient level

For per-arm accuracy, the naive standard error assumes independent observations. But multiple documents come from the same patient (progress note + MRI + EEG for one epilepsy admission), and their extraction errors correlate. Naive CIs are too narrow.

**Solution**: nonparametric percentile bootstrap on patient-level means. Draw N patients with replacement, compute the mean accuracy across their documents, repeat 1,000 times, take the 2.5 % and 97.5 % percentiles. Implemented in `eval/metrics.py::bootstrap_ci`. This is the same procedure Fonferko-Shadrach used and the same the AutoHS paper cites (1,000 bootstrap replicates for AUC CIs).

### 2.6 Multiset scoring for list-valued fields

Fields like `MriModule.findings` are lists (`hippocampal_sclerosis`, `gliosis`, `encephalomalacia`). Naive scoring compares lists as strings and fails on ordering or when only some items are wrong. Correct approach: multiset (bag) difference.

If pred = `{hippocampal_sclerosis, gliosis, tumor}` and gold = `{hippocampal_sclerosis, gliosis, encephalomalacia}`:
- TP = pred ∩ gold = `{hippocampal_sclerosis, gliosis}` → count 2
- FP = pred − gold = `{tumor}` → count 1
- FN = gold − pred = `{encephalomalacia}` → count 1

Python's `collections.Counter` supports set-difference natively; implemented in `eval/metrics.py::score_field` (list branch).

---

## 3. Schema engineering (Pydantic v2)

### 3.1 Generics for evidence-wrapped values

Every extractable field is `Evidence[T]` where `T` is the concrete value type (e.g. `bool`, `LobarLocalization`, `SeizureFrequency`). Pydantic v2 supports generic models:

```python
from typing import Generic, TypeVar
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")

class Evidence(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")
    value: T | None = None
    certainty: Certainty = Certainty.NOT_DOCUMENTED
    ...
```

When resolved at module attribute time (`overall_normal: Evidence[bool]`), Pydantic emits a proper JSON schema with `"type": "boolean"` for `value`. This is what makes M2's schema-injection prompt work end-to-end.

### 3.2 The `extra="forbid"` discipline

`ConfigDict(extra="forbid")` on every module makes unexpected keys a validation error. In clinical extraction this catches:
- Model emissions with hallucinated fields (`"laterality_confidence": 0.87`).
- Schema drift between the code and the model's understanding.
- Prompt engineering typos where the model was told about a field that no longer exists.

Without `forbid`, the pipeline silently accepts junk keys and the "raw validity rate" over-counts.

### 3.3 Cross-field validators

Model-level `model_validator(mode="after")` catches cross-field contradictions the type system can't:

```python
@model_validator(mode="after")
def _consistency(self) -> "Evidence[T]":
    if self.value is None:
        if self.certainty not in (NOT_DOCUMENTED, UNKNOWN, NEGATED):
            raise ValueError("value=None requires certainty in {…}")
    else:
        if not self.evidence_text or not self.evidence_text.strip():
            raise ValueError("value present requires non-empty evidence_text")
    ...
```

This encodes the *semantic* rule that a field cannot be simultaneously "extracted" and "not documented". Similar validator on `MriModule` enforces that if `hippocampal_sclerosis=True` then the `findings` list must actually contain an HS entry — catching internal inconsistency that would otherwise pass Pydantic's per-field type checks.

### 3.4 Discriminated enums with str base

```python
class Laterality(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    ...
```

`str, Enum` inheritance gives:
- JSON serialization uses the string value directly (`"left"` not `"Laterality.LEFT"`).
- Comparison with plain strings works.
- Pydantic accepts either the enum member or the string on input.

This is important when the LLM emits a string; Pydantic coerces it into the enum without an explicit `.parse()` call.

### 3.5 Schema versioning discipline

Every field, enum, or applicability edit bumps the schema version. This is enforced by convention: `SCHEMA_VERSION = "v0.2.1"` in `schema/ontology.py` + `EpilepsyPhenotype.schema_version: Literal["v0.2.1"]`. The Literal ensures Pydantic rejects records claiming they belong to a different version.

Locked test-set predictions must reference exactly one schema version. Recorded in every run manifest. This is what makes results reproducible six months later.

---

## 4. Data provenance and open-corpus strategy

### 4.1 Public-corpus taxonomy

| Corpus | Status | Access | What it covers |
|---|---|---|---|
| **Fonferko-Shadrach 2024** | Downloaded, silver-labeled | Zenodo, CC-BY 4.0 | 200 synthetic clinic letters with adjudicated ExECT-v2 annotations |
| **TUH EEG Corpus** | Pending registration | Temple U NEDC, free after form | ~30,000 EEG reports for silver-labeling |
| **PMC epilepsy case reports** | 20 fetched | NCBI E-utilities | Schema stress-test material |
| **Xie 2022 (Penn)** | Author-request only | Not open | Requested via outreach |
| **Adelson 2026 (Vanderbilt)** | Author-request only | Not open | Requested via outreach |

Only the first three are actionable without human negotiation. All silver-label engineering was scoped to what's downloadable.

### 4.2 Provenance envelope on every silver record

Every JSON produced by `scripts/silver_label_fonferko.py` carries a `provenance` block naming the source paper, DOI, PMCID, Zenodo record IDs, license, and generator script:

```json
"provenance": {
    "source_paper": "Fonferko-Shadrach B et al. 2024...",
    "source_doi": "10.1186/s13326-024-00316-z",
    "source_license": "CC-BY-4.0",
    "zenodo_records": ["8381080", "8356494", ...],
    "generator_script": "scripts/silver_label_fonferko.py",
    "label_quality": "silver"
}
```

Two purposes: (a) downstream code can *never* mistake silver for gold, and (b) reviewers can verify the corpus origin.

### 4.3 Idempotent, checksum-verified fetch

`scripts/fetch_fonferko_shadrach.py` uses the Zenodo API to fetch four deposits, verifies MD5 checksums against the API metadata, and only re-downloads if the local file is missing or the wrong size. This is important for reproducibility: users cloning the repo six months later must get bit-identical inputs.

---

## 5. Prompt engineering as versioned artifacts

### 5.1 Prompt registry pattern

Rather than embedding prompts as inline strings in extraction code, `services/prompt_registry.py` defines a `PromptTemplate` dataclass with `(module_name, arm, version)` as the primary key. Two lookup functions:

```python
def resolve(module_name: str, arm: str, version: str = "v1") -> PromptTemplate: ...
def for_arm(doc_type: DocumentType, module_name: str, arm: str, version: str) -> PromptTemplate: ...
```

Every prompt has:
- `system_prompt` — role framing, §21 language.
- `task_instruction` — module-specific.
- `output_directives` — arm-specific (M0/M1 free JSON, M2 strict schema).
- `few_shot` — a tuple of `FewShotExample`s each with its own citable `example_id`.
- `rationale` — why this template exists / change log.

### 5.2 Version bump discipline

Once a prompt has been used in an eval run, its content is *frozen*. To iterate, create v2 (e.g., `medication.M1.v2`) with a new `example_id`. The registry then contains both; the eval harness picks up whichever version the run manifest names.

This solves the version-skew problem that plagues LLM research: reported metrics can't be reproduced because the prompt has been silently edited since publication.

### 5.3 Real provenance for few-shot examples

The v1 examples were hand-written synthetic prose. v2 examples are adapted from Fonferko-Shadrach EA0150 with the `example_id` `medication.fewshot.fonferko-EA0150.v1`. When the paper is submitted, reviewers can trace every training / prompting artifact to a publicly cited source.

### 5.4 Prompt-level schema constraint vs. token-level

An obvious optimization for M2 (schema-constrained) would be Outlines / Instructor / Guidance — libraries that hijack the token-level logits to guarantee valid JSON emission. We deliberately did *not* use these.

**Why not.** The paper measures raw validity (does the model emit valid JSON on the first attempt?) as a scientific finding — it tells us how well the model has internalized structured output. Token-level constraints make raw validity ~100% by construction and destroy the measurement.

**What we did instead.** Inject the JSON schema into the system prompt (M2 templates), let the model attempt free-form generation, then apply a bounded deterministic repair chain post-hoc. The repair method (`strip_code_fence` / `regex_json_extraction` / `strip_fence_then_regex` / `failed`) is logged separately, so we can report both raw and repaired validity.

---

## 6. Extraction pipeline design (validate → repair → log)

### 6.1 ModelBackend protocol

Rather than hard-code Med42 into the extraction pipeline, `services/extract.py` defines a duck-typed protocol:

```python
class ModelBackend(Protocol):
    model_name: str
    model_cache_dir: str
    def generate(self, prompt: str, decoding: DecodingConfig) -> tuple[str, int | None]: ...
```

This is what lets us swap in `Med42Backend` (real GPU inference), `RulesMriBackend` (B0 rules), `B1InferenceBackend` (BERT), or `MockBackend` (unit tests) without touching the pipeline.

### 6.2 The extract → validate → repair loop

```python
def extract_module(*, module_cls, prompt, source_text, ..., backend, decoding, schema_version):
    prompt_str = prompt.render(source_text, module_schema=...)
    raw, tokens = backend.generate(prompt_str, decoding)
    parsed, err = try_parse(module_cls, raw)  # first attempt
    if parsed:
        mb.record_raw(raw, raw_valid=True, ...)
        return ExtractionResult(...)
    # Repair path
    mb.record_raw(raw, raw_valid=False, parse_error=err)
    repaired, method, attempts, err2 = _repair(module_cls, raw)
    mb.record_repair(method, attempts, final_valid=(repaired is not None), ...)
    return ExtractionResult(manifest=mb.finish(), module=repaired)
```

The `record_raw` / `record_repair` calls populate the manifest in stages, so even a failed extraction leaves a well-formed record on disk. Nothing is silently lost.

### 6.3 Applicability-driven multi-module router

`services/router.py` implements one document → one phenotype:

```python
def extract_phenotype(*, doc, source_text, backend, arm, ...):
    applicable = modules_for(doc.doc_type)   # from schema/applicability.py
    per_module = {}
    for name in applicable:
        prompt = resolve(name, arm)
        result = extract_module(module_cls=MODULE_CLASSES[name], prompt=prompt, ...)
        per_module[name] = result
        if result.module is not None:
            phenotype_kwargs[name] = result.module
    return PhenotypeExtractionResult(phenotype=EpilepsyPhenotype(**phenotype_kwargs), ...)
```

A failure in one module doesn't tank the others. Modules that fail extraction are left as `None` on the top-level phenotype, so downstream code can `if phenotype.mri is not None` before scoring.

---

## 7. Evidence grounding as a first-class metric

### 7.1 Whitespace-normalized substring match

`services/evidence_verifier.py` walks a populated phenotype, extracts every `Evidence` object with a non-null value, and checks its `evidence_text` appears in the source. Normalization: collapse whitespace runs, lowercase (case-insensitive is more realistic than strict for clinical text).

### 7.2 The three-way accounting

Each Evidence resolves to one of four buckets:
- **supported** — value present, quote in source
- **unsupported** — value present, quote NOT in source (hallucination)
- **missing evidence** — value present, empty evidence_text (schema failure)
- **not documented** — value absent, no check needed

Evidence precision = supported / (supported + unsupported + missing). Unsupported-claim rate = 1 − evidence precision. Both reported per arm in the manuscript.

### 7.3 Why this is a "scientific" finding

Prior work reports F1 on extracted values. If a model gets high F1 but 40 % of its extractions are unsupported (i.e., correct by coincidence, not because it read the document), the F1 masks a fundamental unreliability. Evidence-grounding decouples the two questions.

---

## 8. Baselines: rules (B0), BERT (B1), Med42 (M0–M2)

### 8.1 B0 rules — transparent, precision-heavy

Four modules (`baseline_rules{,_eeg,_medication,_clinical_seizure}.py`) implement regex + keyword extraction with:
- **Negation awareness**: `_preceded_by_neg()` checks 30 chars before a match for "no", "without", "absent", etc.
- **Sentence-scoped context**: `_infer_status()` looks only within the current sentence boundary (`. ? ! ; \n`) to avoid cross-sentence contamination (the "Previously" that describes drug B doesn't leak onto drug A next door).
- **Priority ordering**: within `_FINDING_PATTERNS`, MOGHE / FCD Palmini subtypes are matched *before* generic FCD to avoid double-counting.
- **Anatomical synonyms**: `_LOBAR_WORDS` maps "hippocampal" → "temporal" so HS detection auto-fills lesion_lobe.

Rules emit valid JSON by construction (100 % schema validity), cite verbatim spans from the source (100 % evidence precision), and never hallucinate — but they miss anything that isn't in the regex bank.

### 8.2 B1 BioClinicalBERT — single-head classifier

`services/baseline_bert.py::train_epilepsy_type_head` fine-tunes `emilyalsentzer/Bio_ClinicalBERT` on the 200 Fonferko silver labels for the `epilepsy_type` field alone. Standard HuggingFace `Trainer` setup:
- Tokenize to 512 tokens (fits typical clinic letters).
- Multi-class head over the label set present in silver.
- 5 epochs, lr=3e-5, weight_decay=0.01, warmup_ratio=0.1.
- Save model + tokenizer + `label_map.json` (so inference can decode class IDs back).

Deliberately single-head for v0.1 of the paper — full multi-head is a v0.2 extension.

### 8.3 M0/M1/M2 Med42 — deterministic decoding

`services/med42_backend.py::Med42Backend` wraps the existing `Med42ModelService` with:
- `do_sample=False, seed=0` — deterministic across runs.
- `torch.bfloat16` on CUDA (fits Med42-8B in ~16 GB on the L40S.24g MIG slice; fp32 needs 32 GB and OOMs).
- Manual seed setting for both `torch` and `torch.cuda` before every generate.

The old Flask `/analyze` path uses sampling (`do_sample=True, temperature=0.3`), which is fine for interactive use but unacceptable for eval reproducibility. The backend isolates the eval-mode decoding.

---

## 9. Evaluation harness (metrics, error taxonomy, bootstrap CI)

### 9.1 Metric primitives

`eval/metrics.py`:
- `FieldMetrics` — TP/FP/FN/TN per field, with `n_applicable` (denominator excluding non-applicable-by-mask). Properties compute precision, recall, F1, accuracy.
- `ModuleScore` — dict of FieldMetrics, macro/micro F1 across fields.
- `ArmSummary` — everything reported per arm: schema validity (raw and repaired), repair method counts, evidence stats, per-module scores, efficiency (duration, tokens).
- `bootstrap_ci(values, n_resamples=1000, alpha=0.05, seed=0)` — patient-level bootstrap.

### 9.2 Manifest → ArmSummary aggregator

`eval/aggregator.py::aggregate_manifests` reads a directory tree of run manifests, groups by arm, and produces one `ArmSummary` per arm. Fields:
- Schema validity + repair method counts.
- Efficiency stats.
- Per-module scores (if gold labels are provided).
- Patient-level bootstrap CIs on final validity.

The aggregator runs in the Docker eval container without torch or transformers — the scoring is pure Python + Pydantic.

### 9.3 Error taxonomy (Table 8 of the blueprint)

`eval/error_taxonomy.py` classifies each (pred_evidence, gold_evidence) pair into one of twelve categories:

1. `missed_fact` — gold has value, pred None.
2. `wrong_label` — both present, values differ (fallback).
3. `negation` — pred says present, gold negates (or vice versa).
4. `uncertainty` — same value, different certainty enum.
5. `temporal` — same value, different temporal_status.
6. `medication_status` — mismatched current/prior/failed.
7. `eeg_semantic` — EEG-module value mismatch.
8. `mri_semantic` — MRI-module value mismatch.
9. `conflict` — unresolved disagreement.
10. `unsupported_inference` — evidence verifier flagged the pred quote as unsupported.
11. `evidence_mismatch` — same value, different evidence_text (both non-empty).
12. `schema` — pred JSON failed schema validity.

Categories are non-exclusive: a single field can raise `wrong_label` AND `evidence_mismatch` AND `temporal`. Reviewers can then read the reported counts to see *what kind* of errors dominate.

### 9.4 CLI for reproducibility

`eval/aggregator_cli.py` is the Docker container's default entrypoint:

```bash
docker run --rm -v $(pwd)/data:/data:ro -v $(pwd)/out:/out medai-epi-eval:v0.2.1 \
    python -m eval.aggregator_cli --manifests /data/run_manifests --gold /data/gold --out /out/report.json
```

Runs on CPU. Any reviewer can reproduce the paper's tables from the released manifests + gold labels without a GPU.

---

## 10. Reproducibility engineering (manifests, container, registries)

### 10.1 Per-inference run manifest

Every extraction — B0, B1, or LLM — writes a JSON manifest with:
- `run_id` (UUID prefix)
- `started_at` / `finished_at` / `duration_s`
- `code_sha` + `code_dirty` (from `git rev-parse` and `git status --porcelain`)
- `hardware` (hostname, python, torch, cuda_version, gpu_name)
- `schema_version`, `prompt_id`, `prompt_version`, `fewshot_ids`
- `model_name`, `model_cache_dir`
- `decoding` config (do_sample, temperature, top_p, max_new_tokens, seed)
- `source_doc_id`, `source_doc_type`, `source_length_chars`
- `raw_response` (full model output as string)
- `raw_valid`, `parse_error_raw`
- `repair_attempts`, `repair_method`, `final_valid`, `parse_error_final`
- `parsed_value` (dict; module JSON if final_valid else None)
- `arm`

This is the atomic reproducibility unit. If anyone questions a number in the paper, we point at the manifests directory.

### 10.2 Fluent builder pattern

`ManifestBuilder.start(...)` initializes the manifest with hardware / config / prompt / source info. As the pipeline runs, `.record_raw(response, ...)` and `.record_repair(method, ...)` populate stages. `.finish()` stamps the timestamp and returns a `RunManifest` dataclass.

**Why fluent builder over kwargs.** The pipeline's stages are inherently sequential (generate → parse → repair → finalize). A builder makes the sequence explicit and prevents *forgetting* to record intermediate state on error paths. If `try_parse` raises, `mb.record_raw(...)` and `mb.finish()` still run in the `except` block and produce a diagnosable manifest.

### 10.3 Container

`Dockerfile.eval` builds a minimal Python 3.11 image with only `pydantic` + code (no torch, no transformers, no Flask). The idea: scoring is CPU-only; keep the container small and dependency-light so it runs on any laptop or CI system. The full-blown Med42 inference happens elsewhere.

### 10.4 Prompt / schema / model registries

- **Prompt registry** — versioned templates in `services/prompt_registry.py`; every prompt has a `rationale` field capturing why it exists.
- **Schema registry** — `SCHEMA_VERSION` constant + `Literal` on the top-level phenotype; every field/enum edit bumps the version.
- **Model registry** — captured per-manifest via `model_name` + `model_cache_dir`. HuggingFace's cache dir holds the exact checkpoint SHA in its structure.

---

## 11. HPC / SLURM engineering

### 11.1 The four gotchas we hit (in order)

**(a) `typing_inspection` missing on compute node.** Python 3.9 on the compute node picked up `~/.local/lib/python3.9/site-packages/pydantic_settings` which requires `typing_inspection`. The venv's site-packages had the same problem. Fix: install into venv, and also install `eval_type_backport` because Python 3.9 can't parse `T | None` syntax at runtime even with `from __future__ import annotations`.

**(b) `venv activate` doesn't stick.** The SLURM script did `. venv/bin/activate` but `python` still resolved to `.local/lib/python3.9`. Fix: use `venv/bin/python` explicitly and `export PYTHONNOUSERSITE=1`.

**(c) `.env` file's `APP_HOME=` empty line overrides the script's export.** `set -a; . .env; set +a` blindly imports every KEY=VALUE, including `APP_HOME=` which nukes the SLURM script's earlier export. Fix: source `.env` FIRST, then set `APP_HOME` from `SLURM_SUBMIT_DIR`.

**(d) Med42-8B in float32 doesn't fit 24 GB.** The pre-existing `Med42ModelService` loads with `torch_dtype=torch.float32` (32 GB for 8B params). L40S.24g slices are 24 GB. Fix: `torch.bfloat16` on CUDA, fall back to `float32` on CPU.

### 11.2 Resumable runners

`scripts/run_open_benchmark_gpu.py` inspects existing manifests before running, indexes by `(source_doc_id, module, arm, prompt_version)`, and skips any tuple already completed. If a run hits the 12 h wall-clock, resubmit and it picks up where it left off. Critical for large sweeps.

### 11.3 Progress logging and ETA

The runner logs every 20 completed inferences with elapsed time and ETA:

```
progress: 60/1200 complete, elapsed=1240.1s, eta≈24000.5s (400.0 min)
```

This is what makes debugging a long-running job possible: you see whether it's stuck, running slow, or on track.

---

## 12. Debugging methodology

### 12.1 Failure mode analysis

For each SLURM failure, the debugging sequence was:
1. `sacct -j <jobid>` → get exit code + timing.
2. `tail logs/<job>.err` → find the last exception.
3. Grep the exception into the affected code path.
4. Fix root cause, not symptoms.

Root-cause fixes are always cheaper long-term than symptomatic patches. Example: when the first job died with `typing_inspection` missing, the wrong fix would have been to hack around `pydantic-settings` imports. The right fix was to identify that the venv wasn't being used, install the missing deps, and force venv usage via `PYTHONNOUSERSITE=1`.

### 12.2 Smoke tests before real jobs

Every code path that mattered had a smoke test using a mock backend. `scripts/smoke_test_all.py` exercises: 22 prompts render, router extracts 6 modules, evidence verifier scores, B0 rules run on MRI/EEG/medication, partial-list scoring correct, error-taxonomy classifier fires on the right categories. When the SLURM jobs failed, we knew the *pipeline* was correct — the failures were purely environmental.

### 12.3 Dry-run mode

`scripts/run_open_benchmark_gpu.py --dry-run` reports the planned inference count and skips loading the model. This caught scoping issues before spending GPU time.

---

## 13. Programming concepts as applied

### 13.1 Separation of concerns

The repository partitions:
- `schema/` — data model, no I/O
- `services/` — pipelines that consume schema
- `eval/` — scoring, independent of extraction
- `scripts/` — CLI entry points
- `docs/` — human-readable specifications
- `paper_doc/` and `writing/` — manuscript artifacts
- `data/` — fetched or generated data (mostly gitignored)

Each layer imports downward only. Schema knows nothing about services; services know nothing about scripts; scripts orchestrate services and read schema.

### 13.2 Fail-fast validation at boundaries

Every place data crosses a trust boundary — external corpus, user input, model output — is guarded by Pydantic validation. Trust is transitive: if `EpilepsyPhenotype.model_validate(json)` succeeds, downstream code doesn't need to check the shape again.

### 13.3 Idempotent operations

Every long-running operation is idempotent:
- Fetch script checks MD5 before re-downloading.
- Silver-label converter overwrites existing outputs (deterministic input → deterministic output).
- GPU runner skips already-completed manifests.

Idempotency = reproducibility + robustness to interruption.

### 13.4 Explicit over implicit

- Decoding config is a dataclass passed at every call, not a global.
- Version numbers are strings compared with `==`, not floating-point.
- Schema module applicability is a static table (`schema/applicability.py`), not runtime inference.

Explicit code is grep-able and diff-able. Six months from now, "why does this field appear on this doc type?" is answerable from a single file.

### 13.5 The dataclass frozen=True pattern

`FewShotExample` and `PromptTemplate` are frozen dataclasses. Once constructed, they cannot be mutated. If someone tries to "just quickly tweak a prompt in memory", they get a `FrozenInstanceError` — forcing them to bump the version instead.

### 13.6 Composition over inheritance

The extraction pipeline never subclasses `ModelBackend`. Backends are duck-typed via `Protocol`. `Med42Backend`, `RulesMriBackend`, `MockBackend`, `B1InferenceBackend` each independently satisfy the protocol. Zero inheritance chains; every backend is one file, self-contained.

### 13.7 Composition of extractors via applicability

The router doesn't hard-code "run these modules". It queries the applicability mask, iterates whatever the mask says, and assembles the top-level phenotype from whatever modules succeeded. Adding a seventh module tomorrow only touches: schema definition + one entry in `MODULE_CLASSES` + one entry in `applicability.MODULE_APPLICABILITY` + one prompt template. Zero changes to the router.

---

## 14. Session-specific decisions and their rationale

### 14.1 Deferring PEFT / fine-tuning

The blueprint's Shape B calls for M4–M6 arms (PEFT + PEFT+schema + PEFT+evidence). We deferred these because:
- Fine-tuning requires **adjudicated gold labels**, not silver.
- The blueprint explicitly says fine-tuning "should be evaluated against prompting rather than assumed necessary."
- The Minimum-version paper (§26) does not require PEFT.

Fine-tuning is a follow-up study. This paper is publishable without it.

### 14.2 Choosing open-corpus (Shape A) over IRB-gated (Shape B)

Shape A can ship in ~2–3 months; Shape B needs 6–12. Publishing Shape A first:
- Establishes citation priority on the problem.
- Produces cite-able methodology that Shape B references.
- De-risks Shape B (reviewers see the framework was validated on public data).
- Catalyzes the outreach emails (a preprint attached to a data-request email lands harder).

### 14.3 Skipping token-level constrained decoding

See §5.4. Would have been faster and simpler, but destroys the paper's raw-validity measurement.

### 14.4 Silver-label converter over waiting for gold

The silver-label converter (`scripts/silver_label_fonferko.py`) unlocked ~2 months of parallelizable work while the IRB and gold-annotation pipeline are on their own timeline. Silver labels are inferior to gold, but they are far superior to *nothing* for prompt iteration, B1 pretraining, and eval-harness bring-up.

### 14.5 Publishing the framework, not just the results

The Shape A paper's contribution is the framework, not the numbers. Even if Med42 M0/M1/M2 numbers underwhelm, the schema, prompts, evaluation harness, and Docker container are cite-able artifacts on their own. This is a hedge against results not going the way we hope.

---

## 15. What is NOT done and why

- **Real Med42 M0/M1/M2 numbers on Fonferko** — pending GPU queue availability. Jobs 89469/89470 submitted with all environmental fixes; expected to complete once scheduled.
- **B1 trained on real silver data** — code path exists, model download + train not yet run.
- **TUH EEG evaluation** — pending registration approval.
- **PI + co-author review of the manuscript** — awaiting distribution of the reviewer packet.
- **Adjudicated gold subset** — awaiting epileptologist time.
- **Institutional cohort (Shape B)** — blocked on IRB.

Each of these is a *known unknown*, called out in Discussion §5 and Limitations §6 of the manuscript. Reviewers who ask "why don't you have more data?" can be pointed at these gates and the outreach log at `docs/CORPUS_OUTREACH.md`.

---

## 16. LLMs, generative AI, prompt engineering, and fine-tuning — beginner to mastery (Med42-8B as running example)

This chapter is the standalone curriculum I wish I had before starting MedAI-EPI. It goes from "what is a language model" to "when do you fine-tune vs. prompt vs. retrieve," using the actual model in this project (Llama3-Med42-8B, ref^14^) as the running example. You can skip earlier subsections if you already know the material.

Sections build on each other:

- 16.1 What a language model actually is
- 16.2 Transformers, attention, and why "8B" means something
- 16.3 Pretraining → SFT → instruction-tuning: what Med42-8B is
- 16.4 Med42-8B specifically: architecture, training data, license, hardware
- 16.5 Loading and running the model (Hugging Face `transformers`)
- 16.6 Decoding — the knobs that actually matter
- 16.7 The context window and why long clinical notes break
- 16.8 Prompt engineering — the taxonomy (zero-shot / few-shot / CoT / …)
- 16.9 Prompt engineering — what actually helps and what doesn't
- 16.10 Schema-constrained output — three paradigms
- 16.11 The schema-echo pathology
- 16.12 Evidence grounding as a first-class LLM output
- 16.13 Fine-tuning taxonomy — full FT, PEFT/LoRA, QLoRA, DoRA
- 16.14 LoRA in detail (with rank / alpha / target-modules intuition)
- 16.15 When NOT to fine-tune
- 16.16 Retrieval-augmented generation (RAG)
- 16.17 Evaluating clinical LLMs rigorously
- 16.18 Ethics and safety for medical LLMs
- 16.19 What mastery looks like
- 16.20 Reading list

### 16.1 What a language model actually is

A language model is a function that takes a sequence of tokens and returns a probability distribution over the next token. That's it. Everything else — chatbots, code generators, clinical extractors — is that function applied autoregressively and wrapped in tooling.

Formally, for a sequence of tokens `x_1, x_2, …, x_n`, the model computes:

```
P(x_{n+1} | x_1, …, x_n)
```

To generate text, you sample or greedily pick `x_{n+1}`, append it to the sequence, and call the model again. Repeat until you hit a stop token or a length limit.

**Tokens are not characters and are not words.** They are subword units. In Llama3's tokenizer, "epilepsy" is one token; "lamotrigine" is two tokens; a rare drug like "rufinamide" might be three or four. This matters because:
- The model's context window is measured in tokens, not characters.
- Cost (API) and latency scale with tokens.
- Rare medical vocabulary uses more tokens than common English.

In our project, `services/med42_backend.py` logs `input_tokens=3200` before every call — that's the tokenizer's count, and we cap it at 3200 to leave room for the model's own generation up to `max_new_tokens=1024` inside Med42's 8192-token context.

### 16.2 Transformers, attention, and why "8B" means something

A transformer is the architecture underneath essentially every modern LLM (GPT, Claude, Llama, Med42, DeepSeek, Mistral, …). Its core operation is **attention**: for every position in the sequence, compute a weighted combination of all other positions, where the weights are learned. This lets the model relate distant tokens ("the patient" at position 12 to "she" at position 187).

A transformer is stacked layers. Each layer has:
1. A self-attention block (learned Q, K, V projections plus a heads mechanism)
2. A feed-forward block (two-layer MLP with a nonlinearity)
3. Normalization (usually RMSNorm in modern models like Llama3) and residual connections

**"8B" means ≈ 8 billion learned parameters.** For Llama3-8B: 32 transformer layers, hidden dimension 4096, 32 attention heads (grouped-query attention with 8 KV heads), MLP intermediate size 14336. Multiply and add: ~8 × 10⁹ float weights.

At **bfloat16** (2 bytes per parameter), 8B ≈ 16 GB of VRAM just for weights. Plus activations, KV cache, etc. That's why Med42-8B fits on a 24 GB L40S but not on a 16 GB T4. Larger models (70B, 405B) are 140 GB and 810 GB respectively — beyond single-GPU budgets, hence multi-GPU sharding or quantization.

**Grouped-query attention (GQA)** — Llama3 uses this. Instead of one KV head per attention head, KV heads are shared across groups. This trades some quality for large memory savings during autoregressive decoding, which is why 8B models feel snappy on modest hardware.

### 16.3 Pretraining → SFT → instruction-tuning: what Med42-8B is

Modern LLMs go through three training phases:

1. **Pretraining**. Trained on trillions of tokens from web text, books, code, papers, etc. Objective: predict the next token. Result: a "base model" that continues text but doesn't follow instructions well. Llama3-8B's pretraining corpus is 15 T tokens. This is *the* compute cost — pretraining an 8B model is millions of GPU-hours.

2. **Supervised fine-tuning (SFT)**. The base model is further trained on curated (instruction, response) pairs. Objective: same next-token prediction, but the loss is only applied to the response tokens. This teaches the model to obey instructions. Corpus size: 10K–100K high-quality examples.

3. **Preference alignment (RLHF, DPO, KTO, ORPO, ...)**. Human raters compare two model outputs; the model is trained to prefer the "better" one. This makes it safer / more helpful / more concise. Not always used, especially for research-focused models.

**Med42-8B** is Llama3-8B → SFT on a curated clinical-domain dataset (approx. 200K medical instruction–response pairs curated by the M42 Health team, per ref^14^). It is a *clinically instruction-tuned* Llama3. It still uses Llama3's tokenizer, Llama3's context window, and Llama3's architecture. What differs is the weights: attention and MLP parameters have been nudged toward clinical language patterns.

**Practical implication**: Med42-8B is better than base Llama3 at recognising clinical terminology and following instructions phrased in clinical language. It is NOT better at reasoning, arithmetic, coding, or general-domain tasks. When you ask it to emit JSON, it obeys because Llama3 was SFT'd on JSON — Med42 inherits that but does not amplify it.

### 16.4 Med42-8B specifically

- **HuggingFace ID**: `m42-health/Llama3-Med42-8B`
- **License**: Meta Llama 3 Community License + M42 addendum (research use permitted with attribution; commercial use gated by Meta's terms)
- **Base**: Llama3-8B-Instruct
- **Weights**: 16 GB in bfloat16 (fp16 also works; fp32 is 32 GB and requires >24 GB VRAM)
- **Context window**: 8192 tokens (Llama3 native; recent Llama3.1 goes to 128K but that's not what Med42 was trained on)
- **Tokenizer**: Llama3 SentencePiece with vocabulary ≈ 128K
- **Generation**: standard `transformers.AutoModelForCausalLM.generate()` — no special API

**In this project**: `services/med42_model.py` loads it in bfloat16 on CUDA; `services/med42_backend.py` wraps it in a `ModelBackend` protocol (defined at `services/extract.py:45`) that yields deterministic outputs (temperature=None, do_sample=False, seed=0) suitable for reproducible research runs. Every generate call logs `input_tokens`, `max_new`, `do_sample`, and `seed`.

**Why Med42-8B for this project** — three reasons:
1. Openly licensed (Shape A commitment: nothing in the pipeline requires a proprietary API)
2. Small enough to run on a single-GPU 24 GB slice (institutional research groups can deploy without a supercomputer)
3. Instruction-tuned on clinical text (better prior than base Llama3 for clinical vocabulary)

### 16.5 Loading and running the model

The complete "hello world" is short:

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

tok = AutoTokenizer.from_pretrained("m42-health/Llama3-Med42-8B")
model = AutoModelForCausalLM.from_pretrained(
    "m42-health/Llama3-Med42-8B",
    torch_dtype=torch.bfloat16,      # not float32 — you'll OOM on 24GB
    device_map="cuda",               # or "auto" for multi-GPU
)

prompt = "The patient has focal epilepsy. List anti-seizure medications:"
inputs = tok(prompt, return_tensors="pt").to("cuda")
outputs = model.generate(
    **inputs,
    max_new_tokens=256,
    do_sample=False,                 # greedy — reproducible
    temperature=None, top_p=None,    # ignored when do_sample=False
)
print(tok.decode(outputs[0][inputs.input_ids.shape[1]:],
                 skip_special_tokens=True))
```

Common mistakes I hit early:
- **Loading in `float32`** — needs 32 GB. Symptom: `CUDA out of memory: Tried to allocate ... GiB. GPU 0 has ... GiB free`. Fix at `services/med42_model.py`.
- **Forgetting `device_map`** — model sits on CPU, `.generate()` runs at 0.5 tok/sec.
- **User site-packages shadowing venv Python** — HPC gotcha; fix in `slurm_open_benchmark.sh` with `export PYTHONNOUSERSITE=1`.
- **HF weights not cached** — first launch downloads ~16 GB; on SLURM's default filesystem this can time out. Fix: pre-fetch once with `huggingface-cli download m42-health/Llama3-Med42-8B --local-dir model_cache/`.

### 16.6 Decoding — the knobs that actually matter

Once the model exists, generation is controlled by five parameters that determine EVERY published LLM number you'll ever read:

| Parameter | What it does | Research setting |
|---|---|---|
| `do_sample` | Enable stochastic sampling | **False** for reproducibility |
| `temperature` | Sharpen (< 1) or flatten (> 1) the next-token distribution | Ignored when `do_sample=False` |
| `top_p` | Restrict sampling to smallest set of tokens whose probability sums to `p` | Ignored when `do_sample=False` |
| `top_k` | Restrict sampling to top-`k` tokens | Ignored when `do_sample=False` |
| `max_new_tokens` | Cap on generated tokens | **Chosen deliberately** — trade off content vs. cost |
| `seed` | Random seed (only affects sampling) | **0** for reproducibility |

**The rule for research code**: `do_sample=False` (greedy decoding). Every call is deterministic; running the same prompt twice returns the same output. This is not the default in most tutorials — most examples show `do_sample=True, temperature=0.7` because they optimize for "feels natural" instead of reproducibility.

**In this project**: `services/med42_backend.py` and `services/run_manifest.py::DecodingConfig` enforce this. Every manifest carries `do_sample=False, temperature=None, top_p=None, seed=0`, and reviewers can re-run the exact call.

**`max_new_tokens` is the parameter you get wrong first**. Too small: the model runs out of budget mid-JSON. Too large: latency blows up. Our paper reports on 1024 (baseline) and 4096 (sensitivity) — the schema-echo pathology at M2 is largely a `max_new_tokens=1024` phenomenon; at 4096 it partially resolves (§Table 4a-4096 sensitivity, forthcoming).

### 16.7 The context window and why long clinical notes break

The context window is the maximum number of tokens the model can process at once, input + output combined. Llama3 (and Med42-8B) has 8192. If your prompt is 3000 tokens and `max_new_tokens=1024`, you use 4024 tokens — safe. If your prompt is 7500 tokens, only 692 tokens are left for generation — often not enough for a full Evidence-wrapped JSON.

**Chunking**. When a single note exceeds the context window, split it. The naive approach — chop every N tokens — is wrong because you split mid-sentence, mid-value-object, mid-clinician-quote. The smart approach: split on natural boundaries.

In this project, `services/chunker.py` does section-aware then paragraph-aware chunking with overlap. `chunk_text(text, max_chars=8000, overlap_chars=400)` returns a list of `Chunk` objects with `char_offset`, `section_hint`, and metadata. Downstream, `services/extract.py:extract_module_long()` runs the same per-module prompt on every chunk and `services/merge.py::merge_modules()` unions the results with Evidence-aware conflict rules.

**Why "8000 chars ≈ 2000 tokens" is a reasonable rule of thumb**: English prose is ~4 chars/token in Llama3's tokenizer. Clinical text with medical jargon is more like ~3.5 chars/token because rare words split into more subwords. If you need exact counts, tokenize.

**Context is not free.** Attention is quadratic in sequence length. A 4× longer prompt is 16× more compute (in the attention layers). The `max_new_tokens=4096` sensitivity sweep took ~9 h 40 min for 1200 inferences; the 1024 baseline took ~6 h 40 min. Budget for it.

### 16.8 Prompt engineering — the taxonomy

Prompting techniques, in rough order of complexity and cost:

| Technique | Description | When it helps | Overhead |
|---|---|---|---|
| **Zero-shot** | Just describe the task | Simple tasks, capable models | Free |
| **Few-shot** | Include example (input, output) pairs | Format-heavy tasks, teaching schema | ~1–5 examples worth of tokens |
| **Chain-of-thought (CoT)** | "Think step by step" | Multi-step reasoning, arithmetic | Doubles output length |
| **Self-consistency** | Sample multiple outputs, vote | Reasoning tasks, robust answers | N× cost |
| **Tree-of-thoughts** | Explore multiple reasoning branches | Complex planning | Very high cost |
| **ReAct** | Interleave Thought and Action steps with tool use | Tool-using agents | Depends on tools |
| **Schema injection (M2 in this paper)** | Embed the full output schema in the prompt | Structured output | Big prompt, sometimes helps, sometimes hurts (see 16.11) |

**In this project**: M0 = zero-shot; M1 = few-shot with one Fonferko-Shadrach-adapted example; M2 = few-shot + full Pydantic-derived JSON schema injected into the prompt. All three defined in `services/prompt_registry.py`, 22 versioned prompts total (6 modules × 3 arms + 4 v2 rewrites).

Chain-of-thought, self-consistency, tree-of-thoughts, ReAct — **none of these are used** in the current paper. Reason: for phenotype extraction, we care about *what the model got right*, not *how it reasoned*. CoT would help on multi-step numerical reasoning (e.g. "compute drug-resistance status from a list of failed ASMs plus their trial durations") but the paper doesn't currently ask multi-step questions.

### 16.9 Prompt engineering — what actually helps and what doesn't

Empirical rules I've extracted from this project and the broader literature:

**Things that reliably help**:
1. **Format anchoring**. Show the model exactly what you want, ideally with a syntactically valid example. M1 in our registry does this; it beats M0 (which just describes the schema).
2. **Specific over general**. "Extract the generic name of every anti-seizure medication mentioned" > "Extract medications."
3. **Named fields**. Prompt with the same field names the schema uses (`current_asms`, `drug_resistance_status`) so the model can pattern-match rather than guess mappings.
4. **Explicit `not_documented` handling**. If the note doesn't mention something, the model should say so — but only if you tell it that's allowed. Otherwise it hallucinates.
5. **Role priming (system prompt)**. "You are a research phenotyping assistant for epilepsy clinical documentation." primes the model into the right register.

**Things that hurt or don't help (contrary to popular advice)**:
1. **"Be concise" instructions**. The model often ignores them and sometimes truncates important content. Rely on `max_new_tokens` instead.
2. **Threats or emotional framing** ("your job depends on it"). Cargo-culting; effect on modern instruction-tuned models is near-zero and unreliable across model versions.
3. **Excessive schema injection (M2 phenomenon)**. Injecting a 12 KB JSON schema hurts an 8 B model — it eats the token budget and the model echoes back the schema instead of extracting content (see 16.11).
4. **Chain-of-thought where it's not needed**. For a lookup-style extraction, CoT wastes tokens and can *hurt* content-validity because the model spends its budget "thinking" instead of producing structured output.

**Iteration loop**:
1. Write a first prompt; run on 5 documents.
2. Look at raw outputs (not aggregate metrics). Find one failure mode. Fix.
3. Repeat until you plateau, then run on 20 documents.
4. Measure content-validity, F1, evidence precision.
5. Compare arms on the *same* documents (paired McNemar, not marginal comparison).

### 16.10 Schema-constrained output — three paradigms

Three ways to make an LLM emit valid structured output, with their tradeoffs:

**A. Prompt-level (what M2 does)**: put the schema in the prompt as a JSON Schema or Pydantic definition. Model is *asked* to comply.
- ✅ Model-agnostic; works on any LLM you can prompt.
- ✅ Cheap to implement (just concatenate schema string).
- ❌ Not enforced — the model can and does emit invalid JSON.
- ❌ Costs tokens: schema in every request.
- ❌ Big schemas can trigger schema-echo pathology (§16.11).

**B. Token-level constrained decoding** (`outlines`, `instructor`, `guidance`, `LM Studio`, Ollama structured output): during generation, the decoding loop *masks* impossible tokens so the output is guaranteed valid.
- ✅ 100% valid output by construction.
- ✅ Faster inference (no invalid tokens to sample).
- ❌ Requires access to the model's logits (not available on most API-only models like GPT-4o via public API without special settings; Claude has structured output; OpenAI has structured output).
- ❌ Can make the model "give up" — if the valid-token mask is too restrictive, the model emits `not_documented` when a valid answer existed. This is the *silent failure* that would trivialize our paper's methodology (§Discussion).

**C. Post-hoc repair** (what our two-tier repair chain does in `services/extract.py` and `services/smart_repair.py`): let the model emit whatever, then deterministic code fixes recoverable errors.
- ✅ Preserves the raw-vs-repaired-validity distinction (the paper's central methodology decision).
- ✅ Doesn't touch decoding — reproducibility preserved.
- ✅ You can measure the model's *unaided* structural competence.
- ❌ Repair rules take effort to build (enum normalization, Evidence-wrapping, brace-balance JSON extraction).
- ❌ Can't fix everything — some outputs are unrepairable.

Our paper uses **A + C**: schema in the prompt for M2 (to measure whether it helps or hurts at 8 B scale) and deterministic repair afterwards (to separate structural from content-level failures). We deliberately do NOT use B, so that the raw validity numbers mean something.

### 16.11 The schema-echo pathology (this paper's central negative result)

We hit a specific failure mode with M2 at `max_new_tokens=1024` that is worth understanding as a general LLM caveat:

**Symptom**: at M2 (few-shot + schema-injected), content-validity was 0.0–7.0 % across modules — worse than M0 (zero-shot) and M1 (few-shot). Bootstrap 95 % CI: [0.0 %, 2.5 %] on drug-resistance content — cleanly separated from M0 [6.5 %, 14.5 %].

**Diagnosis**: the injected schema is ~12 KB (a few thousand tokens). Combined with the few-shot example and the source document, the *input* is ~7 K tokens, leaving ~1 K for output. The 8 B model, given no clear directive to produce content, spent its output budget *echoing back the schema itself* — reproducing field names, enum definitions, and JSON structure but never populating values.

**Why it happens**: instruction-tuned LLMs are trained to be helpful. When asked to "produce JSON conforming to this schema," a small model that hasn't strongly internalized "produce EXTRACTED CONTENT that conforms" defaults to the safest interpretation: echo the structure. This is the LLM equivalent of a student copying the exam questions onto the answer sheet.

**How we characterized it**: paired McNemar's tests across arms (Table 4c). M2 vs M0: χ² = 19.05, p = 1.3 × 10⁻⁵. M2 vs M1: χ² = 28.03, p = 1.2 × 10⁻⁷. This isn't chance — it's a real, reproducible, statistically significant regression.

**How to fix it**:
1. Larger `max_new_tokens` (this is what the SLURM 103501 sensitivity sweep tests at 4096).
2. Bigger model (Med42-70B if released, or a frontier model — but that violates the open-framework thesis).
3. Token-level constrained decoding (§16.10 B) — but that hides the pathology, doesn't cure it.
4. Fine-tuning on structured extraction (§16.13) — expensive but principled.

**Broader lesson**: prompt engineering has model-scale-dependent behaviors. What works on GPT-4o may fail on Med42-8B. Always characterize on the model you'll actually deploy.

### 16.12 Evidence grounding as a first-class LLM output

Most LLM tutorials teach "make it output JSON" but stop there. For clinical or research use, that's not enough — you need to know *where in the source* every extracted value came from.

**Evidence grounding** means every extracted value carries a verbatim source quote (and, optionally, character offsets). In our schema, `Evidence[T]` (defined at `schema/evidence.py`) wraps every field:

```python
class Evidence(BaseModel, Generic[T]):
    value: T | None
    certainty: Certainty
    temporal_status: TemporalStatus
    evidence_text: str | None
    source_doc_id: str
    source_doc_type: DocumentType
    source_date: date
    char_start: int | None
    char_end: int | None
```

The Pydantic validator enforces the invariants:
- If `value` is present, `evidence_text` must be non-empty.
- If `value` is `None`, `certainty` must be `NOT_DOCUMENTED` or `UNKNOWN` or `NEGATED`.
- Character offsets must both be set or both be `None`.

**Why this matters for evaluation**: two separate metrics fall out — *field F1* (did the model extract the right value?) and *evidence precision* (did the quote actually support the value?). A model with high field F1 but low evidence precision is hallucinating the source. This is caught by `services/evidence_verifier.py`, which does whitespace-normalized substring match between the emitted quote and the source note.

**Why this is a first-class LLM design question**: instructing the model to emit `evidence_text` alongside `value` doubles the output tokens but gives you audit-grade output. Every clinical LLM should do this if the output will inform any research or clinical decision.

### 16.13 Fine-tuning taxonomy

When prompting isn't enough, fine-tuning is the next escalation. There are several paradigms, in rough order of compute cost:

| Technique | What it does | Params trained | VRAM | Typical use |
|---|---|---|---|---|
| **Full fine-tuning** | Retrain all weights | 100 % (8 B for Med42-8B) | 80+ GB | Big compute budget; large task-specific corpus |
| **LoRA** | Learn low-rank additive matrices per layer | ~ 0.1–1 % | 16 GB (bf16) | Modest budget; most research |
| **QLoRA** | LoRA over a 4-bit-quantized base model | ~ 0.1–1 % | 8 GB | Consumer GPU; tightest budget |
| **DoRA** | LoRA + directional decomposition | Similar to LoRA | 16 GB | LoRA replacement, slightly better in some benchmarks |
| **Adapter tuning** | Small MLPs inserted between layers | ~ 1 % | 16 GB | Older PEFT technique |
| **Prompt tuning / prefix tuning** | Learn a soft-prompt prefix | ~ 0.01 % | 8 GB | When labels are scarce |

**Full fine-tuning** is what most people mean when they say "fine-tuning," but it's rare in practice for large models because:
- 8 B model in bfloat16 = 16 GB weights + 16 GB gradients + 16 GB optimizer state (Adam) + activations = 64 GB minimum, usually 80+ GB.
- Catastrophic forgetting risk — the model forgets general capabilities while learning your narrow task.
- Requires 10K+ high-quality task examples.

**PEFT (parameter-efficient fine-tuning)** — a family of techniques that train a small fraction of parameters. LoRA is the dominant one.

### 16.14 LoRA in detail

LoRA (Low-Rank Adaptation, Hu et al. 2021) is the fine-tuning technique you'll use 90 % of the time for research on modern LLMs. The math:

Instead of updating a big weight matrix `W ∈ ℝ^{d × d}` directly, LoRA adds a low-rank decomposition:

```
W_new = W_frozen + (B × A)  where  B ∈ ℝ^{d × r},  A ∈ ℝ^{r × d},  r ≪ d
```

`W_frozen` is not updated. Only `A` and `B` are trained. For `d = 4096` and `r = 16`, you train `2 × 4096 × 16 = 131,072` parameters instead of `4096 × 4096 = 16,777,216`. That's a **128× reduction**.

**The parameters that matter**:
- **`r` (rank)**: 4–32 typical. Higher rank = more expressive but more params + more overfitting risk. Start at 8 or 16.
- **`alpha` (scaling factor)**: LoRA scales the update by `alpha / r`. Common practice: `alpha = 2 × r`. Governs how much the LoRA update "weighs" against the frozen base.
- **`target_modules`**: which layers get LoRA adapters. For decoder-only LLMs, standard choice is `["q_proj", "k_proj", "v_proj", "o_proj"]` (all four attention projections). Add `["gate_proj", "up_proj", "down_proj"]` for MLP LoRAs (more expressive, more params).
- **`dropout`**: 0.05–0.1 typical.
- **Learning rate**: 1e-4 to 3e-4 typical for LoRA (higher than full-FT because you're training fewer params).

**In this project (not yet run)**: `docs/PROTOCOL_SHAPE_A.md` sketches a follow-up experiment where Med42-8B is LoRA-tuned on the F-S silver labels for ClinicalSeizure extraction. Rationale: at M1 our ClinicalSeizure F1 is 0.00 (Table 4b-gold). Fine-tuning is the natural escalation, but §Discussion §Limitations #4 defers it pending adjudicated gold at sufficient scale — the F-S silver labels alone are too noisy to LoRA-train productively.

**Minimal LoRA code**:

```python
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM
import torch

base = AutoModelForCausalLM.from_pretrained("m42-health/Llama3-Med42-8B",
                                             torch_dtype=torch.bfloat16,
                                             device_map="cuda")
config = LoraConfig(
    r=16, lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05, bias="none",
    task_type="CAUSAL_LM",
)
model = get_peft_model(base, config)
model.print_trainable_parameters()   # e.g. "trainable: 4.2M / total: 8B (0.05%)"
```

Then train with `transformers.Trainer` or `trl.SFTTrainer` on your (prompt, target) pairs.

### 16.15 When NOT to fine-tune

Fine-tuning is not a first move. The order of escalation is usually:

1. **Prompt engineering first**. Cheap, no data required, one hour of iteration often beats a week of fine-tuning.
2. **Few-shot examples**. Free, mechanical, quantifiable.
3. **Retrieval-augmented generation (§16.16)**. Adds new knowledge without retraining.
4. **PEFT / LoRA**. Only when the above plateau and you have a real labeled dataset (>1K examples ideally).
5. **Full fine-tuning**. Rarely; big data + big compute + willingness to accept catastrophic forgetting.

**Signals you SHOULD fine-tune**:
- Prompt engineering has plateaued (M2 vs M1 curves cross).
- You have a specific output format (JSON schema) the model can't reliably produce.
- You have >1K adjudicated (input, output) pairs.
- Your task doesn't require general capability (fine-tuned models get worse at things they weren't fine-tuned on).

**Signals you should NOT fine-tune**:
- < 200 labeled examples.
- Task is a lookup or an aggregation ("count the seizures mentioned"), not a language-understanding one.
- Task needs to update dynamically (new drug added → RAG, not retrain).
- You haven't tried few-shot yet.

For MedAI-EPI: we deliberately deferred fine-tuning (§Discussion #4) because our labeled corpus is 200 silver documents — well below the threshold, and the silver labels themselves have known transformation errors that fine-tuning would only memorize.

### 16.16 Retrieval-augmented generation (RAG)

RAG adds external knowledge to an LLM at inference time by retrieving relevant documents and stuffing them into the prompt. Pattern:

1. Embed every knowledge-base document into a vector store (FAISS, Chroma, Qdrant, pgvector).
2. At query time, embed the query, find the top-k nearest documents.
3. Prepend those documents to the prompt: "Given these facts: [retrieved]. Answer: [query]"

**When RAG beats fine-tuning**:
- Knowledge changes frequently (new drug approved, guideline updated).
- You need to cite sources (medical, legal, research).
- Your task is knowledge-retrieval, not skill-acquisition.

**When RAG doesn't help**:
- Task is structural (produce this schema) — RAG has nothing to add.
- Latency-sensitive — retrieval + embedding round-trip adds hundreds of ms.
- Small knowledge base fits in the prompt anyway.

**For MedAI-EPI**: the codebase has legacy `services/*rag*.py` files from the pre-pivot general medical platform. These are unused in the current paper — the F-S clinic-letter extraction task is structural, not knowledge-retrieval. A future Shape B or C paper could integrate RAG for guideline-anchored extraction (e.g., "does this treatment plan comply with the current ILAE 2010 drug-resistance definition?").

### 16.17 Evaluating clinical LLMs rigorously

Common failure modes in LLM evaluation:

1. **Reporting only one metric**. F1 alone lies. Report P, R, F1, plus content-validity, plus evidence precision, plus per-field breakdowns.
2. **Marginal-comparison instead of paired**. When comparing arms on the same documents, use paired tests (McNemar, sign test), not marginal-CI overlap. `scripts/mcnemar_arm_comparisons.py`.
3. **No bootstrap CI**. Point estimates on n=200 without CIs are noise. Patient-level bootstrap, 1000 resamples, seed=0.
4. **Silver labels as gold**. Silver-labeling has its own error rate — compare to native gold when possible (`scripts/score_llm_arms_vs_fs_gold.py`).
5. **No error taxonomy**. Aggregate F1 hides *why* the model failed. `scripts/error_taxonomy_scan.py` classifies errors into 12 categories (missed_fact, wrong_label, negation, uncertainty, temporal, medication_status, eeg_semantic, mri_semantic, conflict, unsupported_inference, evidence_mismatch, schema).
6. **No downstream utility check**. Field F1 is not utility. `scripts/cohort_demo.py` shows how field-level F1 propagates to cohort-level inference — this is the honest utility story.

**TRIPOD-LLM checklist** (`docs/TRIPOD_LLM_CHECKLIST.md`): our completed reporting checklist for the manuscript. Analogous to CONSORT for clinical trials — enforces disclosure of prompt versions, decoding config, seed, corpus provenance, license, and per-field metric definitions.

### 16.18 Ethics and safety for medical LLMs

Non-negotiable rules for clinical NLP research:

1. **No PHI in prompts to external APIs**. Any GPT-4o/Claude API call means the text left your infrastructure. For real patient data this is an IRB-blocking issue. Med42-8B runs locally = no leakage. Frame the paper's contribution around this.

2. **Deterministic decoding for reproducibility**. Every research call: `do_sample=False, seed=0`. Reviewers should be able to re-run.

3. **Evidence grounding for auditability**. Every extracted value has a verbatim source quote — if a clinician disagrees with the extraction, they can look at the quote and adjudicate. No unauditable claims.

4. **"Research use only" framing**. MedAI-EPI is not a medical device (not FDA-cleared, not CE-marked). Manuscript §Ethics states this explicitly. The disclaimer appears in three places: the app UI first-visit modal, the README, and the manuscript.

5. **Failure-mode taxonomy included in publication**. Not hiding negative results (schema-echo pathology, ClinicalSeizure refractoriness). Negative results are the paper's contribution as much as positive ones.

6. **License compliance**. Med42's Meta Llama 3 Community License permits research use with attribution. Weights: cached from HuggingFace, not redistributed. Data: Fonferko-Shadrach CC-BY 4.0 with attribution.

7. **No autonomous clinical decisions**. Every extracted value is *research-grade phenotype data*, not a diagnosis. The tool assists a clinician; it does not replace one.

### 16.19 What mastery looks like

You're at "beginner": you can load Med42-8B, run `generate()`, and interpret its output.
You're at "intermediate": you can design a prompt, measure content-validity vs. structural-validity, and iterate.
You're at "advanced": you can characterize a model's failure modes (schema-echo, hallucination, negation confusion) and choose the right escalation (bigger context, few-shot, LoRA, RAG).

You're at "mastery" when:
1. You can read the Methods of an LLM clinical extraction paper and *reproduce the numbers* without asking the authors. (Prompt registry, deterministic decoding, versioned schema, per-inference manifest.)
2. You can tell when a model's poor performance is a *model* problem (needs fine-tuning), a *prompt* problem (needs different phrasing), a *schema* problem (task is over-specified), or a *data* problem (labels are wrong).
3. You know the tradeoffs of the three schema-constrained-output paradigms (§16.10) well enough to pick one for a new task in 5 minutes.
4. You've read at least one paper each on: attention mechanisms (Vaswani 2017), instruction tuning (InstructGPT, Ouyang 2022), LoRA (Hu 2021), RAG (Lewis 2020), TRIPOD-LLM (Gallifant 2024).
5. You can decide "should I run this on Med42-8B or on GPT-4o?" without a shrug — you know that Med42 gives you determinism + local weights + no PHI leakage but costs you raw capability, and you know when each side of the tradeoff wins.
6. You can say "the model isn't the bottleneck" and mean it — sometimes the schema is wrong, the corpus is unreliable, or the evaluation is measuring the wrong thing.

### 16.20 Reading list

Ordered from foundational to specialty. One-line summaries; read the papers.

1. Vaswani et al. 2017. "Attention Is All You Need." NeurIPS. — the transformer paper. Read once, revisit forever.
2. Radford et al. 2018/2019. GPT-1 / GPT-2 papers. — pretraining paradigm.
3. Ouyang et al. 2022. "Training language models to follow instructions with human feedback." — InstructGPT / RLHF for instruction tuning.
4. Hu et al. 2021. "LoRA: Low-Rank Adaptation of Large Language Models." ICLR. — the fine-tuning technique you'll use most.
5. Dettmers et al. 2023. "QLoRA: Efficient Finetuning of Quantized LLMs." — the consumer-GPU version of LoRA.
6. Lewis et al. 2020. "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks." — the RAG paper.
7. Christophe et al. 2024. "Med42-v2: A Suite of Clinical LLMs." arXiv 2408.06142. — the model in this project.
8. Alsentzer et al. 2019. "Publicly Available Clinical BERT Embeddings." — the B1 baseline.
9. Fonferko-Shadrach et al. 2019, 2024. ExECT and Annotation-of-epilepsy-clinic-letters papers. — the epilepsy NLP lineage.
10. Li et al. 2021. "Are synthetic clinical notes useful for real NLP tasks?" JAMIA. — the synthetic-corpus methodology precedent.
11. Gallifant et al. 2024. "TRIPOD-LLM Reporting Guidelines." — the clinical-LLM reporting standard we conform to.
12. Kwan and Brodie 2000. "Early identification of refractory epilepsy." NEJM. — the drug-resistance operationalization our downstream utility demo uses.
13. Fisher et al. 2017. ILAE seizure classification. — the ontology's canonical reference.

Skip: everything on "prompt engineering hacks" that promises Nx improvements without citing empirical evidence on your specific model. Those are almost always cargo-cult techniques that fail to reproduce.

---

## Appendix A: Key files at a glance

| File | Role |
|---|---|
| `schema/ontology.py` | The 6 phenotype modules |
| `schema/evidence.py` | `Evidence[T]` generic + `DocumentMetadata` |
| `schema/enums.py` | ILAE 2017/2010 canonical enums |
| `schema/applicability.py` | Per-doc-type module masks |
| `services/prompt_registry.py` | 22 versioned prompts |
| `services/extract.py` | Validate → repair → log pipeline |
| `services/router.py` | Multi-module extraction |
| `services/run_manifest.py` | Per-inference reproducibility unit |
| `services/med42_backend.py` | Deterministic-decoding Med42 wrapper |
| `services/evidence_verifier.py` | Evidence precision + unsupported-claim rate |
| `services/baseline_rules{,_eeg,_medication,_clinical_seizure}.py` | B0 rules baselines |
| `services/baseline_bert.py` | B1 BioClinicalBERT train + inference |
| `eval/metrics.py` | FieldMetrics + bootstrap CI |
| `eval/aggregator.py` | Manifest → ArmSummary |
| `eval/error_taxonomy.py` | 12-category error scorer |
| `eval/aggregator_cli.py` | Docker container entrypoint |
| `scripts/fetch_fonferko_shadrach.py` | Zenodo download + checksum verify |
| `scripts/silver_label_fonferko.py` | Fonferko → v0.2.1 silver labels |
| `scripts/analyze_fonferko_schema.py` | Schema-mapping report |
| `scripts/run_open_benchmark.py` | B0-arm run on Fonferko silver |
| `scripts/run_open_benchmark_gpu.py` | M0/M1/M2 GPU sweep |
| `scripts/slurm_open_benchmark.sh` | SLURM wrapper |
| `scripts/fill_manuscript_tables.py` | Manifest → Markdown Tables 5-9 |
| `scripts/smoke_test_all.py` | End-to-end smoke test |
| `docs/SCHEMA_V0_2.md` | Human-readable ontology reference |
| `docs/PROTOCOL_SHAPE_A.md` | Study protocol |
| `docs/REVIEWER_PACKET.md` | PI + co-author cover note |
| `docs/TRIPOD_LLM_CHECKLIST.md` | Reporting-checklist mapping |
| `docs/CORPUS_OUTREACH.md` | Author-corpus request tracker |
| `docs/FONFERKO_SHADRACH_MAPPING.md` | Silver-labeling caveats |
| `Dockerfile.eval` | Reproducible eval container |
| `paper_doc/MedAI_EPI_Manuscript_v0.1.md` | v0.1 manuscript |
| `writing/MedAI_EPI_Manuscript_v0.2.md` | v0.2 manuscript in AutoHS voice |

## Appendix B: Commit sequence (this session)

```
b244e7b  Non-blocking model load, .env sourcing in SLURM, GPU stack smoke test
3c887df  Rebrand vecta -> MedAI across source, env vars, and CLI launchers
6d796e4  Add MedAI-EPI paper track: schema v0.2.1, extraction pipeline, baselines, eval harness
76261bb  Batch: /extract endpoint, Fonferko-Shadrach corpus, B0 EEG+medication, error taxonomy, container
2e7074e  Add corpus-outreach tracker with four ready-to-send draft emails
b03194b  Shape A paper draft ready for PI/co-author review
583f054  GPU-side infrastructure: bf16 Med42 loading, resumable Fonferko sweep, table generator
```

Each commit builds on the previous. Reading them in order recapitulates the design evolution.

---

*End of `learning_medai.md`. If you want a specific section expanded or a topic added (e.g., "walk me through the router in more detail"), extend below.*
