# MedAI-EPI Paper 1 (Shape A) — Reviewer Packet

**For PI + co-author internal review, before preprint / journal submission.**

## Cover note (draft)

Dear `<PI_NAME>` and colleagues,

Attached is the v0.1 internal draft of **MedAI-EPI: An Open Framework for Schema-Constrained, Evidence-Grounded Structured Epilepsy Phenotype Extraction from Clinical Documents**. This is the Shape-A methodology / open-benchmark paper — the smaller, publicly-corpus-only cousin of the full Shape-B institutional study still gated by IRB.

**What I need from you:**
1. Sign-off on the **study protocol** (`docs/PROTOCOL_SHAPE_A.md`). Estimated read: 10 minutes.
2. Approval or amendment of the **provisional schema items** in `docs/SCHEMA_V0_2.md` §7 — etiology categories, focal motor / non-motor subtypes, ICD/RxNorm cross-references. Estimated read: 20 minutes.
3. Comments on the **manuscript draft** (`paper_doc/MedAI_EPI_Manuscript_v0.1.md`). Estimated read: 40 minutes. Sections most in need of your review are Discussion §5 and Limitations §6 — these are placeholders / skeletons that need clinical judgment before final numbers land.
4. Confirmation of author list + contributions (Manuscript §9).

**What is complete:**
- Schema v0.2.1 — ontology + evidence grounding + applicability mask.
- Extraction pipeline — 6 modules × 3 arms (18 v1 prompts + 4 Fonferko-adapted v2).
- Baselines — B0 rules for MRI + EEG + medication + clinical_seizure; B1 BERT head for `epilepsy_type` (training script released).
- Fonferko-Shadrach silver-label pipeline — 200 validated phenotype records.
- Evaluation harness — per-field P/R/F1, schema validity, evidence precision, unsupported-claim rate, error taxonomy, bootstrap CIs.
- Reproducibility container — `Dockerfile.eval`.
- Preliminary Table 3 numbers (B0 rules vs Fonferko silver — 100% schema validity, 100% evidence precision by construction, ClinicalSeizure macro F1 0.41).
- Full manuscript structure with real numbers where computable and clearly-marked PENDING placeholders where GPU inference is required.

**What is still pending:**
- Real Med42 M0/M1/M2 numbers → requires `sbatch scripts/slurm_m2_mri.sh` on the GPU node.
- B1 BERT training run → requires downloading `emilyalsentzer/Bio_ClinicalBERT` (~440 MB) and 5 epochs on GPU (~20 min) or CPU (~2 hr).
- TUH EEG Corpus registration approval (~1–2 weeks) and evaluation.
- Small adjudicated gold subset (~30 letters, `<PI_NAME>` or delegate: ~2 hours of clinician time) — would settle silver-vs-silver ambiguity flagged in Discussion §5.4.
- Response to `docs/CORPUS_OUTREACH.md` outreach emails (parallel track; not gating).

**Timeline** (per `docs/PROTOCOL_SHAPE_A.md`):
- Your review + amendments: **1 week**.
- Real Med42 run + B1 training + populated tables: **1 week**.
- Manuscript v0.2 with all numbers in place: **1 week after** the above.
- Preprint (medRxiv / arXiv): ~3–4 weeks total wall clock.

Please add comments inline in the docs directly, or reply-all with a comments file. Any concerns about scope, framing, or claims should surface *now* — the paper is structured so results-track changes don't reshape Methods.

Thank you for your time.

`<YOUR_NAME>`, `<YOUR_TITLE>`
`<YOUR_INSTITUTION>` — `<YOUR_EMAIL>`

---

## Where everything lives (navigation guide)

**Read in this order** for the fastest orientation:

| # | Document | Purpose | ETA to read |
|---|---|---|---|
| 1 | `docs/PROTOCOL_SHAPE_A.md` | 12-section study protocol; scope, RQs, methods, timeline, deliverables | 10 min |
| 2 | `paper_doc/MedAI_EPI_Manuscript_v0.1.md` | The manuscript itself | 40 min |
| 3 | `docs/SCHEMA_V0_2.md` | Ontology reference (v0.2.1) — needed to critique the extraction targets. Provisional items marked in §7 need your sign-off. | 20 min |
| 4 | `docs/TRIPOD_LLM_CHECKLIST.md` | Reporting-checklist mapping; shows what artifact backs each claim | 5 min |
| 5 | `docs/FONFERKO_SHADRACH_MAPPING.md` | Silver-labeling pipeline caveats and 852 open questions | 10 min |
| 6 | `docs/SCHEMA_V0_1_STRESS_TEST.md` | Corpus stress-test that surfaced the schema gaps we later addressed in v0.2. Historical context. | Optional |
| 7 | `docs/CORPUS_OUTREACH.md` | Parallel author-corpus outreach; separate from Shape A but informs the co-author list | Optional |

**Where to find the code:**

| Concern | Files |
|---|---|
| Schema definition | `schema/{ontology.py, evidence.py, enums.py, applicability.py}` |
| Prompt registry (22 templates) | `services/prompt_registry.py` |
| Extraction pipeline (validate + repair loop) | `services/extract.py` |
| Run manifest writer | `services/run_manifest.py` |
| Router (multi-module extraction) | `services/router.py` |
| Evidence verifier | `services/evidence_verifier.py` |
| Med42 backend (deterministic eval decoding) | `services/med42_backend.py` |
| B0 rules baselines | `services/baseline_rules{,_eeg,_medication,_clinical_seizure}.py` |
| B1 BERT training + inference | `services/baseline_bert.py` + `scripts/train_b1_epilepsy_type.py` |
| Eval metrics + aggregator + error taxonomy | `eval/{metrics.py, aggregator.py, error_taxonomy.py, aggregator_cli.py}` |
| Preliminary open-benchmark run | `scripts/run_open_benchmark.py` |
| Real Med42 GPU run | `scripts/run_m2_mri_real.py` + `scripts/slurm_m2_mri.sh` |
| End-to-end smoke tests (all green) | `scripts/smoke_test_all.py` |

**Where to find the data:**

| Corpus | Location | License | Role |
|---|---|---|---|
| Fonferko-Shadrach 2024 letters + gold annotations | `data/fonferko_shadrach_2024/zenodo_{8381080,8356494,8382589,12520180}/` | CC-BY 4.0 | Primary eval |
| Silver labels (adapted to our schema) | `data/fonferko_shadrach_2024/silver_labels_v0_2_1/` | CC-BY 4.0 (derivative) | Primary eval |
| PMC epilepsy case reports (20) | `data/pmc_cases/` | Per-article, CC-BY variants | Schema stress test |
| Run manifests (from smoke tests + eventual real inference) | `data/run_manifests/<date>/` | (gitignored; regenerated per run) | Reproducibility artifact |
| Preliminary open-benchmark results | `eval/results/` | (gitignored; regenerated) | Preliminary Table 3 |

---

## Response log template

Use this to log incoming reviewer feedback. Append below.

```
### Feedback from <NAME> (<DATE>)

**Section:** ...

**Comment:** ...

**Response / action:** ...
```

### Feedback from `<PI_NAME>` (`<DATE>`)

*(placeholder — populate as feedback arrives)*
