# MedAI-EPI Corpus Manifest Schema v1.0

**Universal spreadsheet-per-visit format** for all MedAI-EPI corpora (synth-v1/v2/v3, MTSamples, PMC, F-S, MIMIC-IV, etc.). One row per (patient × visit), stored as both CSV (Excel-viewable) and Parquet (analytical). Notes stored as `.txt` files, gold as `.json` files, joined via manifest.

## Column definitions

| Column | Type | Required | Description |
|---|---|---|---|
| `visit_id` | str | ✓ | Globally unique visit/encounter ID (e.g., `V000001` or `synth_v3_P003042_visit_5`) |
| `patient_id` | str | ✓ | Globally unique patient ID (e.g., `P003042`, `EA0001_pt`) |
| `corpus` | str | ✓ | Source corpus name (`synth_v1`, `synth_v2`, `synth_v3`, `mtsamples`, `pmc`, `fs`, `mimic_iv`) |
| `corpus_version` | str | ✓ | Corpus schema version (e.g., `v1.0`) |
| `patient_dob` | date | opt | Synthetic YYYY-MM-DD (consistent per patient); null if unknown |
| `patient_sex` | str | opt | Enum: `M`, `F`, `other`, `unknown` |
| `patient_race` | str | opt | Standardized enum or `unknown` |
| `patient_ethnicity` | str | opt | Standardized enum or `unknown` |
| `patient_zip3` | str | opt | First 3 digits of ZIP for regional analysis (HIPAA-safe) |
| `visit_date` | date | opt | YYYY-MM-DD; may be null for corpora without dates |
| `visit_number` | int | opt | Sequence for this patient (1, 2, 3, ...); null if unknown |
| `age_at_visit` | float | opt | Computed: `visit_date - patient_dob` in years |
| `note_type` | str | ✓ | Enum: `progress_note`, `new_patient_consult`, `telephone_fuv`, `emu_admission`, `ed_note`, `prc_summary`, `mri_report`, `eeg_report`, `neuropsych`, `discharge_summary`, `triage_call`, `inpatient_progress`, `clinic_letter`, `unknown` |
| `note_template` | str | opt | Template ID for synth-v3 (`A`-`L`); null for other corpora |
| `care_setting` | str | opt | Enum: `academic_medical_center`, `community_neurology`, `va`, `emu`, `ed`, `unknown` |
| `provider_persona` | str | opt | Enum: `attending_neurologist`, `neurosurgeon`, `app`, `fellow`, `radiologist`, `ed_physician`, `unknown` |
| `specialty` | str | opt | Enum: `neurology`, `neurosurgery`, `ed`, `radiology`, `neurophysiology`, `psychology`, `other`, `unknown` |
| `note_char_count` | int | ✓ | Character count of the note text |
| `note_word_count` | int | ✓ | Word count (whitespace-tokenized) |
| `note_section_count` | int | opt | Detected canonical sections |
| `note_language` | str | ✓ | ISO 639-1 code (`en` for all US corpora) |
| `generator_model` | str | opt | For synthetic corpora: `gpt-5.6-sol`, `gpt-5.6-luna`, `human_written`, `transcribed`, `template_generated`, etc. |
| `generator_seed` | int | opt | Random seed for reproducibility |
| `generator_tokens_in` | int | opt | OpenAI input tokens used |
| `generator_tokens_out` | int | opt | OpenAI output tokens used |
| `generator_cost_usd` | float | opt | Cumulative USD cost for this doc |
| `phenotype_profile` | str | opt | Enum: `newly_diagnosed`, `drug_responsive`, `drug_resistant`, `presurgical`, `post_surgical`, `autoimmune`, `developmental`, `status_epilepticus`, `unknown` |
| `note_path` | str | ✓ | Relative path to note text file (e.g., `documents/V000001.txt`) |
| `gold_path` | str | opt | Relative path to v0.2.1 gold JSON |
| `semantic_plan_path` | str | opt | Relative path to semantic plan (synth only) |
| `raw_source_path` | str | opt | Original file path (for imported/external corpora) |
| `gold_source` | str | opt | Enum: `semantic_plan_derived`, `gpt_silver`, `clinician_adjudicated`, `none`, `unknown` |
| `gold_conformant` | bool | opt | Pydantic v0.2.1 validation result |
| `silver_labeler` | str | opt | Model name for silver labels (e.g., `gpt-5.6-terra`) |
| `review_status` | str | opt | Enum: `unreviewed`, `reviewed`, `flagged`, `excluded` |
| `epilepsy_relevance_score` | float | opt | Computed relevance metric for filtered corpora (MTSamples, PMC) |
| `created_at` | datetime | ✓ | ISO 8601 timestamp |
| `created_by` | str | ✓ | Script + version (e.g., `generate_synth_v3_corpus.py v1.0`) |
| `ingest_batch` | str | opt | Batch identifier for grouped ingests |
| `notes` | str | opt | Free-text notes/tags |

## Files layout

```
data/eval_corpora/{corpus_name}/
├── manifest.csv                        # THIS SCHEMA
├── manifest.parquet                    # optional analytical format
├── documents/                          # Per-visit note text
│   └── {visit_id}.txt
├── gold_v0_2_1/                        # Per-visit v0.2.1 Pydantic gold (JSON)
│   └── {visit_id}.json
├── patients/                           # Per-patient semantic plans (synth only)
│   └── {patient_id}.json
├── gold_flat.csv                       # OPTIONAL long-format gold view
├── gold_brat/                          # OPTIONAL BRAT-compatible export
│   ├── {visit_id}.txt
│   └── {visit_id}.ann
├── run_metadata.json                   # Generation/ingest run metadata
└── README.md
```

## Long-format gold view (`gold_flat.csv`)

For quick field-level analysis:

```csv
patient_id, visit_id, field_path, value, certainty, temporal_status, evidence_text
P003042, V000005, clinical_seizure.predominant_seizure_type, focal_impaired_awareness, definite, current, "typical spells with impaired awareness"
P003042, V000005, clinical_seizure.epilepsy_type, focal, definite, current, ""
P003042, V000005, medication.current_asms[0].generic_name, lamotrigine, definite, current, "on lamotrigine 300 mg BID"
P003042, V000005, medication.current_asms[1].generic_name, levetiracetam, definite, current, "on Keppra 1000 mg BID"
```

Regenerable from `gold_v0_2_1/*.json` via `scripts/gold_json_to_flat_csv.py`.

## Cross-corpus normalization

Any external corpus (MTSamples, PMC, Synthea, MIMIC-IV, user-uploaded) can be normalized to this schema via `scripts/normalize_corpus_to_manifest.py --corpus {source} --input-dir {path} --output-dir {path}`.

Missing optional fields → `null`. Required fields → must be derivable from the source.

## Backwards compatibility

Existing corpora (synth-v1, synth-v2, MTSamples) that have partial manifests can be **backfilled** without regenerating notes/gold — a migration script computes derived fields and writes manifest.csv in the new format alongside existing files.

Corpus loaders in `scripts/run_medcat_rules_on_corpus.py` prefer manifest when present, fall back to file-glob when absent → **zero breakage** for legacy corpora.

## Version history

- **v1.0** (2026-09-30): Initial universal schema. Adopts spreadsheet-per-visit organization with per-file text/gold storage.
