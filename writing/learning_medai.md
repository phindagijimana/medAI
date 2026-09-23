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
