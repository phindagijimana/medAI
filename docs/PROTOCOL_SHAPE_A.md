# MedAI-EPI Paper 1 (Shape A) — Study Protocol

**Version:** 0.1, 2026-09-22  
**Status:** **Superseded** by `docs/EVAL_PROTOCOL_LEO.md` (frozen 2026-10-01) and `writing/MedAI_EPI_Manuscript_LEO.md`. Kept as history of the M0/M1/M2 research questions. Do not use RQ-A1–A6 as the submission hypotheses.

## 1. Rationale

The MedAI-EPI Paper 1 blueprint (`paper_doc/MedAI_Paper1_Heterogeneous_Clinical_Documents_Full_Blueprint.docx`, "Shape B") specifies a retrospective clinical NLP validation study over an adjudicated institutional cohort. That study is gated by IRB, cohort access, annotator recruitment, and pilot annotation — realistically **6–12 months**.

This protocol defines a smaller, **open-corpus-only** Shape A study that:

- Uses **only publicly available or freely licensable corpora**, no PHI, no IRB.
- Publishes the schema, pipeline, evaluation harness, and Docker container as the primary artifact.
- Reports **silver-metric** performance on Fonferko-Shadrach 2024 + (optionally) TUH EEG Corpus.
- Positions MedAI-EPI as an **open reproducible framework** for the community.
- **De-risks** and precedes the full institutional Shape B study.

Publishing Shape A first establishes priority, produces cite-able artifacts, and strengthens the eventual Shape B submission.

## 2. Explicit non-goals

- No claim of clinical accuracy on real EHR notes.
- No claim of heterogeneous-document generalization beyond what Fonferko + TUH support (progress notes + EEG reports; MRI / EMU / presurgical / conference NOT covered).
- No cross-institutional validation.
- No PEFT / fine-tuning experiment (§13 of the blueprint deferred to Strong version).
- No headline metrics on `MriModule`, `IntegratedPhenotypeModule`, or surgical outcomes — those fields will be reported *descriptively* only.

## 3. Research questions (Shape A)

| RQ | Question | Hypothesis |
|---|---|---|
| RQ-A1 | Can a locally-deployed clinical LLM (Med42-8B) produce a valid schema-conforming structured epilepsy phenotype from clinic-letter prose? | H1: raw JSON validity ≥ 0.80 for M2; post-repair ≥ 0.95. |
| RQ-A2 | Does prompt-injected schema constraint (M2) improve raw validity vs. zero-shot (M0) and few-shot (M1)? | H2: raw validity M2 > M1 > M0. |
| RQ-A3 | Does adding an evidence-grounding requirement (M3) reduce unsupported-claim rate at cost of validity? | H3: unsupported-claim rate M3 < M2. |
| RQ-A4 | How does a transparent regex/keyword rules baseline (B0) compare with LLM extraction on the same corpus? | H4: rules are precision-heavy; LLM arms recall-heavy. Expect P_rules > P_llm on template-y fields, R_llm > R_rules on prose fields. |
| RQ-A5 | Does a BioClinicalBERT single-head classifier (B1) trained on silver labels reach LLM zero-shot performance? | Descriptive only; test whether small supervised models can substitute for LLM prompting when labeled data (even silver) exists. |
| RQ-A6 | Efficiency: what is the token / latency cost of schema injection in the prompt? | Descriptive. Report M0/M1/M2 prompt length + latency per doc. |

## 4. Corpora

| Corpus | Coverage | License / access | Role |
|---|---|---|---|
| **Fonferko-Shadrach 2024** (200 synthetic clinic letters, dual-annotated + adjudicated with published κ) | Progress-note / clinic-letter prose covering clinical_seizure + medication modules | CC-BY 4.0 (Zenodo DOI 10.5281/zenodo.8381080) | **Primary evaluation corpus.** Silver-labeled to our v0.2.1 schema via `scripts/silver_label_fonferko.py`. |
| **TUH EEG Corpus** (Temple University, ~30,000 EEG reports) | EEG report prose covering the EegModule | Free after institutional registration | **Secondary (silver-only) evaluation.** Used for descriptive extraction rates on EegModule; not headline metric. **Contingent on registration.** |
| **PMC epilepsy case reports** (20 fetched via `scripts/fetch_pmc_epilepsy_cases.py`) | Heterogeneous case narratives; multiple doc types blended | Public, CC-BY variants | Schema stress test and exemplar analysis for the Limitations / qualitative section. |

**Not used**: PhysioNet MIMIC-IV-Note (no epilepsy labels), OpenI (few brain MRIs), CPRD (fee-based). Author-corpus outreach to Xie/Adelson/Liu is separate track (`docs/CORPUS_OUTREACH.md`) — not required for Shape A.

## 5. Experimental arms

Per paper Table 6, but restricted to what's feasible without adjudicated gold:

| ID | System | What it isolates |
|---|---|---|
| B0 | Rules / regex / keyword baseline (per module) | Transparent deterministic extraction. |
| B1 | BioClinicalBERT single-head classifier trained on silver labels | Supervised small-model contribution. Single field (`epilepsy_type`) in v0.1 of the paper; extend if time. |
| M0 | Med42-8B zero-shot via `services/prompt_registry.resolve(*, "M0")` | Base instruction-following on epilepsy prose. |
| M1 | Med42-8B few-shot (Fonferko-adapted example provenance) | In-context demonstration effect. |
| M2 | M1 + JSON-schema injected in prompt (no token-level constrained decoding) | Schema-constraint effect on raw-vs-repaired validity. |
| M3 | M2 + evidence-grounding requirement enforced post-hoc | Evidence quality effect on unsupported-claim rate. |

Deterministic decoding for eval: `do_sample=False, seed=0, max_new_tokens=1024`. Bound in `services/med42_backend.py::Med42Backend`.

## 6. Metrics (primary → secondary → descriptive)

**Primary endpoint**: macro F1 over the "core field set" of five ClinicalSeizure fields (`epilepsy_type`, `predominant_seizure_type`, `age_at_onset_years`, `seizure_frequency`, `etiology_category`) plus `drug_resistance_status`, plus multiset ASM-name F1. Computed per arm. Silver-metric on Fonferko.

**Secondary endpoints**:
- Raw validity rate (JSON parses on first response) per arm — paper §11.
- Repaired validity rate + repair-method distribution.
- Evidence precision (fraction of extracted values with an evidence quote that appears verbatim in the source).
- Unsupported-claim rate (1 − evidence precision).
- Per-field precision / recall / F1 with support counts.
- Bootstrap 95% CIs on primary endpoint (patient-level cluster; here doc-level since Fonferko is 1 letter ≈ 1 synthetic patient).
- Error-taxonomy category counts (Table 8 of the blueprint).
- Efficiency: prompt length (chars/tokens), latency per doc, GPU memory.

**Descriptive only** (no formal hypothesis testing):
- Extraction rates on TUH EEG (silver-only) for `EegModule` fields.
- Silver-label caveats analysis on Fonferko (agreement between our silver mapping and ExECT-v2's original annotations).

## 7. Timeline

| Week | Milestone |
|---|---|
| 0 (now) | Protocol approved. All engineering artifacts already committed and reproducible. |
| 1 | TUH registration submitted; epileptologist reviews `SCHEMA_V0_2.md` §7 provisional items; small clinician-adjudicated gold subset (~30 letters) begun on Fonferko. |
| 2 | Real Med42 M0/M1/M2 run on Fonferko via `sbatch scripts/slurm_m2_mri.sh` (needs a small extension for the clinic-letter arm). Preliminary M-arm numbers logged. |
| 3 | B1 trained on Fonferko silver, evaluated. Prompt v2 iterations from any M0/M1/M2 failure modes surfaced in week 2. |
| 4 | TUH access granted (if approved) → run M0/M1/M2 on ~500 TUH reports for the EEG descriptive section. |
| 5 | All numbers frozen. Tables 3–5 populated. Figures 1–5 drafted. |
| 6 | Manuscript v0.2 to PI + co-authors for internal review (this milestone). |
| 8 | Manuscript v0.3 incorporating review comments; preprint (medRxiv / arXiv-CS.CL). |
| 10 | Submission to target venue (JAMIA Open or npj Digital Medicine, methods slot). |

Weeks 1–4 have external gates (clinician time, TUH registration, GPU queue). Assume 50% of parallel wall-clock is available — timeline may stretch by ±2 weeks.

## 8. Deliverables

At submission:

- **Repository release** — versioned tag `v0.2.1-paper1` with code + schema + prompts + eval harness + Docker container.
- **Silver-label dataset** — 200 Fonferko-adapted phenotype records under `data/fonferko_shadrach_2024/silver_labels_v0_2_1/` (already committed).
- **Manuscript + supplement** — `paper_doc/MedAI_EPI_Manuscript_v*.md` (this line updated with the current version tag on submission).
- **TRIPOD-LLM reporting checklist** — `docs/TRIPOD_LLM_CHECKLIST.md` fully populated.
- **Reproducibility container** — `Dockerfile.eval` + published image tag.
- **Run manifests** — the exact manifests from the eval runs used to produce the paper's tables, released as supplementary material.

## 9. Governance

- No PHI touched at any point.
- All external corpora used under their stated licenses (CC-BY 4.0 for Fonferko-Shadrach; TUH per NEDC terms of use).
- Med42-8B used under its HuggingFace / Meta license terms.
- Paper framing (§21 of blueprint): "research phenotyping / information extraction", **not** diagnostic or clinical decision-support tool.

## 10. Author list & contributions (draft)

| Author | Contribution |
|---|---|
| `<YOUR_NAME>` | Engineering, schema design, evaluation, manuscript primary author |
| `<PI_NAME>` | Study design, epileptologist review, senior authorship |
| _(TBD)_ | Statistical review, second annotator (if manual gold subset produced) |
| _(TBD)_ | Domain review — pediatric epilepsy expertise if relevant |

## 11. Sign-off

PI sign-off on this protocol authorizes proceeding to weeks 1–8 above.

Signature: ______________________ Date: __________

Amendments: append to §12 below with date and initials.

## 12. Amendment log

(empty)
