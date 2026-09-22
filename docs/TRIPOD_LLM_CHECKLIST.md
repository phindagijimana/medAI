# MedAI-EPI reporting checklist (TRIPOD-LLM style)

Pre-filled skeleton mapping the paper's mandatory reporting items to concrete
artifacts already produced in this repository. Co-authors fill the "Manuscript
reference" column pointing at the section/page where each item is addressed
in the final draft.

TRIPOD-LLM is a reporting standard for studies developing or validating
LLM-based prediction/extraction systems. This checklist adopts its structure
and cross-references the paper blueprint (`paper_doc/MedAI_Paper1_*.docx`).

Legend for the "Status" column:
- ✅ artifact exists in the repo and can be cited directly
- 🚧 partial / silver-quality; needs strengthening before submission
- ❌ not yet produced

| # | Item | Status | Artifact / evidence | Manuscript reference |
|---|---|---|---|---|
| **Title & abstract** ||||
| 1 | Identify the study as LLM-based clinical information extraction | ✅ | `README.md` framing (§21 language) | (Abstract) |
| 2 | Structured summary: cohort, systems compared, primary metrics, main results | ❌ | Awaits results | (Abstract) |
| **Introduction** ||||
| 3 | Background: unstructured clinical documentation as barrier | ✅ | `paper_doc/*Literature_Review*.docx` §2.1 | (Intro §1) |
| 4 | Objective + research questions RQ1–RQ8 | ✅ | Blueprint Table 1 | (Intro §2) |
| **Methods — study design** ||||
| 5 | Retrospective clinical NLP validation study | ✅ | Blueprint Table 0 | (Methods §2.1) |
| 6 | IRB / DUA / PHI-compute approval | ❌ | Not yet obtained | (Methods §2.2) |
| **Methods — cohort & data** ||||
| 7 | Cohort inclusion/exclusion, patient-level splits, dedup, copy-forward detection | ❌ | Awaits institutional corpus | (Methods §2.3) |
| 8 | Document taxonomy (MRI/EEG/progress/EMU/…) | ✅ | Blueprint Table 2 | (Methods §2.4) |
| 9 | Phenotype ontology and versioning | ✅ | `schema/` (v0.2.1), `docs/SCHEMA_V0_2.md` | (Methods §2.5) |
| 10 | Coding standards used (ILAE 2017/2010, ICD-10-CM, SNOMED, HGNC, RxNorm) | ✅ | `docs/SCHEMA_V0_2.md` §7.1 | (Methods §2.5) |
| **Methods — annotation** ||||
| 11 | Annotator qualifications and adjudication protocol | ❌ | Annotation study not started | (Methods §2.6) |
| 12 | Annotation manual (definitions, negation, uncertainty, temporality) | ❌ | Awaits pilot | (Methods §2.6, Supplement) |
| 13 | Inter-annotator agreement (κ / IRR) | ❌ | Pilot output | (Methods §2.7) |
| 14 | External / bootstrap annotations used | ✅ | `data/fonferko_shadrach_2024/` (Fonferko-Shadrach 2024, CC-BY 4.0) | (Methods §2.8) |
| 15 | Silver-label pipeline (if used) | 🚧 | `scripts/silver_label_fonferko.py`, `data/fonferko_shadrach_2024/silver_labels_v0_2_1/` | (Methods §2.9) |
| **Methods — systems** ||||
| 16 | Baselines (B0 rules, B1 clinical-BERT) | 🚧 | `services/baseline_rules*.py` (MRI + EEG + medication) ✅; B1 `services/baseline_bert.py` scaffold only 🚧 | (Methods §3.1) |
| 17 | LLM prompting arms M0/M1/M2 | ✅ | `services/prompt_registry.py` (18 v1 + 4 v2 templates) | (Methods §3.2) |
| 18 | Model version + weights + tokenizer hash | ✅ | Recorded per inference in run manifest (`services/run_manifest.py`) | (Methods §3.3) |
| 19 | Decoding config (deterministic, seeded, temperature/top-p, max_new_tokens) | ✅ | `services/med42_backend.py` uses `DecodingConfig(do_sample=False, seed=0)` for eval | (Methods §3.4) |
| 20 | Prompt registry (versioned, change-history) | ✅ | `services/prompt_registry.py` with prompt_id / version fields | (Methods §3.5) |
| 21 | Schema-constrained decoding? Prompt-only or token-level? | ✅ | Prompt-only injection; token-level constrained decoding explicitly avoided to preserve raw-validity measurement per §11 | (Methods §3.6) |
| 22 | Evidence grounding methodology | ✅ | `services/evidence_verifier.py`; every Evidence carries source_doc_id + date + verbatim span | (Methods §3.7) |
| 23 | Applicability mask per doc type | ✅ | `schema/applicability.py` with `enforce()` guard | (Methods §3.8) |
| **Methods — evaluation** ||||
| 24 | Primary endpoint declared before test set opened | ❌ | Reviewer sign-off needed | (Methods §4.1) |
| 25 | Secondary endpoints (schema validity, evidence correctness, unsupported-claim rate) | ✅ | `eval/metrics.py` `ArmSummary` reports all three | (Methods §4.2) |
| 26 | Per-field metrics (P/R/F1 with support) | ✅ | `eval/metrics.py` `FieldMetrics` | (Methods §4.3) |
| 27 | Partial-list scoring for multi-valued fields | ✅ | `eval/metrics.py` uses multiset diff | (Methods §4.4) |
| 28 | Bootstrap CIs at patient level | ✅ | `eval/metrics.py::bootstrap_ci` (patient-clustered) | (Methods §4.5) |
| 29 | Error taxonomy (12 categories from Table 8) | ✅ | `eval/error_taxonomy.py` | (Methods §4.6, Supplement) |
| 30 | Doc-type stratification | ✅ | `eval/aggregator.py` scores per module respecting applicability | (Methods §4.7) |
| **Methods — implementation & reproducibility** ||||
| 31 | Hardware, GPUs, VRAM | ✅ | Recorded per manifest (`hardware.gpu_name`, `cuda_version`) | (Methods §5.1) |
| 32 | Software versions, seeds | ✅ | `run_manifest.hardware.torch`, decoding.seed | (Methods §5.1) |
| 33 | Container for reproducible eval | ✅ | `Dockerfile.eval` + `requirements.eval.txt` + `eval/aggregator_cli.py` | (Methods §5.2, Data Availability) |
| 34 | Code + data availability statements | 🚧 | Code: MIT (this repo). Fonferko-Shadrach: CC-BY 4.0 (already fetched). Institutional data: governance-dependent. | (Data Availability) |
| **Results** ||||
| 35 | Cohort flow diagram (Fig 1) | ❌ | Awaits cohort | (Results §6.1) |
| 36 | Architecture diagram (Fig 2) | ❌ | Draft in blueprint | (Results §6.2) |
| 37 | Experimental ladder (Fig 3): B0/B1 vs. M0→M2/M3 | ❌ | Awaits results | (Results §6.3) |
| 38 | Per-module + per-field results (Tables 3–4) | ❌ | Awaits results | (Results §6.4) |
| 39 | Evidence / hallucination / schema-validity metrics (Table 5) | ❌ | Awaits results | (Results §6.5) |
| 40 | Efficiency: latency, throughput, tokens/doc | 🚧 | Manifests already capture duration + tokens; needs aggregation table | (Results §6.6) |
| **Discussion & limitations** ||||
| 41 | Answer each RQ explicitly | ❌ | Awaits results | (Discussion §7) |
| 42 | Prospective / external validation caveats | ✅ | Fonferko-Shadrach available as external-validation slice (Flagship) | (Discussion §7.4) |
| 43 | Limitations: single-site, silver-label caveats, non-PEFT scope, LLM-family dependence | 🚧 | Silver-label caveats documented in memory; Minimum scope declared | (Limitations §8) |
| **Governance** ||||
| 44 | Statement of intended use (research phenotyping, not diagnosis/clinical DSS) | ✅ | `README.md` + `docs/SCHEMA_V0_2.md` §21 language | (Statement of intended use) |
| 45 | PHI + data-sharing constraints | 🚧 | Awaits IRB determination | (Governance) |
| 46 | Model licensing (Llama3-Med42-8B) and downstream restrictions | ❌ | Cite HuggingFace card + Meta license | (Governance) |

## Attribution to fill in on submission

- Corresponding author: __________________
- IRB approval number / determination: __________________
- Data-availability text: __________________
- Funding: __________________
- Conflicts of interest: __________________
- Author contribution statement (CRediT taxonomy): __________________

## Change log

- v0.2.1 initial draft — 2026-09-22. Reflects state at commit `<TBD>`.
- Regenerate this table after every schema version bump or after each
  results milestone. Keep the ✅/🚧/❌ column honest.
