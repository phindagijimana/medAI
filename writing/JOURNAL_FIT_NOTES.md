# Journal-fit editorial pass — v0.2 trims

**Date:** 2026-09-28
**File touched:** `writing/MedAI_EPI_Manuscript_v0.2.md`
**Word count:** 8686 → 7030 (venv/bin/python `.split()`), delta = -1656 words.
**Headings preserved:** 26 (unchanged, `grep -c "^#"`).
**Untouched files:** `MedAI_EPI_Manuscript_v0.4.md`, `MedAI_EPI_Manuscript_v0.4_additions.md`.

## Target and rationale

Target journals: JAMIA (~4000 words primary text), JBI, npj Digital Medicine.
The pending v0.4 subsection additions add ~500 words; this pass trims v0.2 aggressively so that after v0.4 merger the primary text sits comfortably below the 4000-word cap with 200-word slack.

## Preserved verbatim (per instructions)

- Abstract (single paragraph after title/byline).
- All §heading text and heading count.
- Every citation reference number (^1^ through ^19^).
- Every filename mention (`services/med42_model.py`, `scripts/silver_label_fonferko.py`, `docs/FONFERKO_GOLD_SCOPE.md`, `docs/TRIPOD_LLM_CHECKLIST.md`, `docs/CORPUS_OUTREACH.md`, `docs/SCHEMA_V0_2.md`, `docs/FONFERKO_SHADRACH_MAPPING.md`, `docs/PROTOCOL_SHAPE_A.md`, `eval/error_taxonomy.py`, `services/tabular.py`, `services/baseline_bert.py`, `services/smart_repair.py`, `services/extract.py`, `services/evidence_verifier.py`, `checkpoints/b1_epilepsy_type_v1/`, `data/run_manifests/<date>/`, `data/run_manifests_maxtok4096/`, `data/pmc_cases/`, `Dockerfile.eval`, `eval.aggregator_cli`).
- All table captions and table body rows (no data touched).
- §Data availability, §Ethics, §Funding, §Competing interests, §Reproducibility (methods subsection), §Supplementary material — reviewer-mandatory items, left as-is.
- Every numeric result (F1, CI, p-values, token counts, wall-clock timings).

## Trims by section

1. **Front matter — duplicate affiliations/keywords block (~40 words).** Lines 21-27 duplicated the byline / affiliations / keywords already present in the title block. Removed the duplicate; single authoritative block remains.

2. **Introduction (~200 words).** Compressed the three-property enumeration (First/Second/Third) into denser sentences, dropped hedged "advanced the field considerably; however" framing, tightened the synthetic-corpora paragraph, replaced "The purpose of this study was to develop and characterize" with "We developed and characterized," and removed the "LLM-arm numbers are pending" sentence (no longer accurate — LLM arms are reported).

3. **Materials and methods — Study design (~50 words).** Dropped "no protected health information was accessed at any point" (redundant with "publicly available synthetic corpora") and consolidated the IRB determination sentence.

4. **Materials and methods — Evaluation corpus (~80 words).** Merged three sentences on the F-S annotation protocol into one; folded the PMC-cases sentence into the same paragraph.

5. **Materials and methods — Phenotype ontology (~120 words).** Trimmed each module description of examples that repeat the schema (e.g., "with duration and per-type qualifier" on seizure frequency, "IVIG, plasmapheresis, corticosteroids, and other adjunctive treatments" collapsed to "IVIG, plasmapheresis, corticosteroids, other adjuncts"). Kept the ontology-defining terms (ILAE 2017, ILAE 2010, Palmini I/IIa/IIb, MOGHE).

6. **Materials and methods — Silver-labeling pipeline (~100 words).** Removed the redundant closing sentence "All 200 records validate against v0.2.1 without repair" (repeated from §Evaluation corpus). Compressed enumeration of entity mappings without dropping any mapping rule.

7. **Materials and methods — System arms (~90 words).** Tightened arm descriptions; kept exact hyperparameters (LR, weight decay, batch size, seed) and every arm identifier.

8. **Materials and methods — Extraction pipeline (~80 words).** Merged two paragraphs on run manifests and evidence verifier into one. Preserved every logged field mentioned.

9. **Materials and methods — Metrics (~160 words).** Compressed the reference-labels paragraph without losing any of the eight in-scope fields, their F-S source, or the n counts. Removed hedged "should consider when interpreting our numbers" phrasing.

10. **Results — B0 rules baseline (~60 words).** Removed restatement of table numbers and hedged "primarily because" prose.

11. **Results — B1 BioClinicalBERT (~100 words).** Trimmed hyperparameter recap (already given in §System arms) and consolidated the deferral rationale.

12. **Results — Med42-8B M0/M1/M2 prose around Table 3 (~150 words).** Compressed the "Four observations follow" paragraph, dropped the standalone sentence about the MRI sanity run being reported earlier (folded into the previous sentence).

13. **Results — Sensitivity paragraph after Table 4a-sensitivity (~80 words).** Compressed without losing McNemar χ² / p values or the "model-scale-bound not token-budget-bound" conclusion.

14. **Results — Prose after Table 4b-gold and "Two conclusions" (~150 words).** Compressed the arm-ordering discussion and the B0-as-competitive-alternative point. All CIs and F1 values retained.

15. **Results — McNemar paragraph after Table 4c (~40 words).** Removed the redundant restatement of "quantify what the marginal CIs suggested."

16. **Results — Error-taxonomy prose and preliminary sensitivity paragraph (~180 words).** Removed the "Preliminary sensitivity analysis... in progress at time of writing" paragraph entirely — the final sensitivity results are already reported in Table 4a-sensitivity and the surrounding prose. This was stale draft text describing a run that has since completed.

17. **Results — Drug-resistance demonstration (~80 words).** Compressed the framing sentence and dropped hedged "with the strong caveat" phrasing.

18. **Results — Seizure-freedom paragraph (~50 words).** Compressed without losing the sensitivity numbers or the ClinicalSeizure-refractoriness link.

19. **Results — Cohort-question paragraph and post-Table 7 prose (~120 words).** Compressed the framing and the "internally consistent" paragraph; retained the field-F1-predicts-utility conclusion.

20. **Results — Efficiency (~80 words).** Removed "Prompt-length characterization from static analysis showed that" framing and consolidated the timing/VRAM sentences.

21. **Discussion opening paragraph (~80 words).** Compressed the Results recap so it does not restate every table.

22. **Discussion — Positioning subsection and downstream paragraphs (~250 words).** Trimmed the "we do not claim general medical AI" paragraph, tightened the ontology-not-generalizable paragraph, compressed the prior-work discussion (Fonferko-Shadrach, Xie, Abeysinghe, Adelson, Goldenholz) without dropping any citation, compressed the validity-vs-repair argument, and consolidated the limitations enumeration. All five numbered limitations preserved; the specialty-scope framing kept.

## Preserved-but-noted concerns for co-author review

- The removed "Preliminary sensitivity analysis... in progress at time of writing" paragraph (trim 16) referenced `data/run_manifests_maxtok4096/`. That directory reference now appears nowhere in the trimmed manuscript. If it should be surfaced in §Reproducibility or the sensitivity paragraph, please flag.
- The abstract still opens with the ~1200-character single paragraph; JAMIA typically requires a structured abstract at submission. Format conversion is out of scope for this pass.
- The v0.4 additions file (`writing/MedAI_EPI_Manuscript_v0.4_additions.md`) was not read during this pass; if any new subsection duplicates content I compressed, that overlap will need reconciliation at merge time.

## Verification

- `wc -w writing/MedAI_EPI_Manuscript_v0.2.md` → 7030 (was 8686).
- `grep -c "^#" writing/MedAI_EPI_Manuscript_v0.2.md` → 26 (unchanged).
- All numeric results, citation numbers, filepath mentions, and table captions retained.
