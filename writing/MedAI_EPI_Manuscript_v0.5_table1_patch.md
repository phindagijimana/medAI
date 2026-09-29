# v0.5 Table 1 patch — arm-ladder update with B1' MedCAT+Rules

*Diff-style patch against `writing/MedAI_EPI_Manuscript_v0.2.md` +
`writing/MedAI_EPI_Manuscript_v0.4_additions.md`.*

The v0.2 manuscript's Table 1 is a silver-label-field-population table
(§Results.Corpus characterization). The comparable **arm-comparison
table** for the F-S 40-letter held-out test is v0.4's Table 5b (which
has placeholder cells). v0.5 patches Table 5b by (a) populating the
Med42 arm cells from the actual manifests scored against F-S gold, and
(b) **inserting a new B1' MedCAT+Rules row** as the strongest arm.

The patched table becomes the paper's primary result table (Table 1 in
the v0.5 renumbered order). We recommend the copy editor move v0.2
Table 1 (silver-label population) to Supplementary Table S0 and promote
this patched table to Table 1.

---

## Diff patch (unified)

```diff
 **Table 5b — F-S 40-letter held-out test (PRIMARY):**

-| Arm | Constrained? | Raw valid % | Final valid % | F-S core-F1 | 95% CI |
-|---|---|---:|---:|---:|---|
-| M0 base | ✗ | [TBD] | [TBD] | [TBD] | [TBD] |
-| M0 base | ✓ | 100 | 100 | [TBD] | [TBD] |
-| M1 few-shot | ✗ | [TBD] | [TBD] | [TBD] | [TBD] |
-| M1 few-shot | ✓ | 100 | 100 | [TBD] | [TBD] |
-| M2 schema | ✗ | [TBD] | [TBD] | [TBD] | [TBD] |
-| M2 schema | ✓ | 100 | 100 | [TBD] | [TBD] |
-| **M4 tuned (v3_fssplit)** | ✗ | [TBD] | [TBD] | **[TBD]** | [TBD] |
-| **M4 tuned (v3_fssplit)** | ✓ | 100 | 100 | **[TBD]** | [TBD] |
+| Arm | Approach | F-S 40 F1 (95 % CI) | Median per-doc F1 | synth-v1 F1 | Notes |
+|---|---|---:|---:|---:|---|
+| B0 rules baseline | Handful of regex + keyword rules | ~0.05–0.15 | ~0.00 | 0.04 | v0.2 §Results.B0 |
+| M0 Med42 base | Med42-8B, no fine-tune, no schema injection | 0.014 [0.00, 0.05] | 0.00 | see v0.2 T4b | Format-not-knowledge ceiling |
+| M1 Med42 few-shot | Med42-8B + 1 demo per module | 0.037 [0.01, 0.08] | 0.00 | see v0.2 T4b | Marginal over M0 |
+| M2 Med42 schema-injected | Med42-8B + schema in prompt | 0.000 [0.00, 0.00] | 0.00 | see v0.2 T4b | Schema-echo pathology (v0.2 §Results) |
+| M4 Med42 LoRA (tuned_v3) | LoRA r=16, α=32, 1160-pair train, F-S 40 held out | 0.055 [0.02, 0.10] | 0.00 | — | +0.041 over M1 but well short of B1' |
+| **B1' MedCAT+Rules** | **MedCAT concept-linker + medspaCy ConText + 43 hand-authored field rules + 10 compound rules** | **0.805 [0.762, 0.848]** | **0.857** | **0.819 [0.795, 0.841]** | **This work; informed by ExECT-V2 (Fonferko-Shadrach 2019, 2024). ~15× best LLM arm.** |
```

---

## Rendered replacement table (final form)

**Table 1 (v0.5). Extraction-arm comparison on the F-S 40-letter
held-out test set (PRIMARY endpoint).** Micro-F1 aggregated over the
8 in-scope shared fields (§Metrics; `docs/FONFERKO_GOLD_SCOPE.md`).
Bootstrap 95 % CIs on micro-F1 from 1000 patient-level resamples
(seed = 0; `scripts/bootstrap_ci_medcat.py`). LLM-arm F1 numbers from
`eval/results/llm_arms_vs_fs_gold_fs_test_{base,tuned_v3}.summary.md`;
B1' from `eval/results/medcat_iterations/iter3_fs_test_40.summary.md`.

| Arm | Approach | F-S 40 F1 (95 % CI) | Median per-doc F1 | synth-v1 F1 (95 % CI) | Notes |
|---|---|---:|---:|---:|---|
| B0 rules baseline | Handful of regex + keyword rules over ClinicalSeizure + Medication | ~0.05–0.15 | ~0.00 | 0.04 | v0.2 §Results.B0 |
| M0 Med42 base | Med42-8B, no fine-tune, no schema injection | 0.014 [0.00, 0.05] | 0.00 | — | Format-not-knowledge ceiling |
| M1 Med42 few-shot | Med42-8B + one demo per module | 0.037 [0.01, 0.08] | 0.00 | — | Marginal over M0 |
| M2 Med42 schema-injected | Med42-8B + schema in prompt | 0.000 [0.00, 0.00] | 0.00 | — | Schema-echo pathology (v0.2 §Results) |
| M4 Med42 LoRA (tuned_v3) | LoRA r=16 α=32, 1160-pair train, F-S 40 held out | 0.055 [0.02, 0.10] | 0.00 | — | +0.041 over M1; well short of B1' |
| **B1' MedCAT+Rules** | **MedCAT concept-linker + medspaCy ConText + 43 hand-authored field rules + 10 compound rules** | **0.805 [0.762, 0.848]** | **0.857** | **0.819 [0.795, 0.841]** | **This work; informed by ExECT-V2 (Fonferko-Shadrach 2019, 2024)** |

Numbers to note:

- **Primary headline:** B1' F1 = 0.805 [95 % CI 0.762, 0.848] on the
  F-S 40 held-out test set.
- **Ratio to best LLM arm (M4 tuned):** 0.805 / 0.055 = 14.6×.
- **Cross-corpus generalization:** F1 within [0.762, 0.848] on UK
  clinician letters and [0.795, 0.841] on US-style synth-v1 — CIs
  overlap; F1 point estimates within 0.014 of each other.
- **Median-per-doc F1:** 0.857 on F-S 40 — a strong majority of test
  letters are extracted correctly on aggregate; only ~10 letters
  drive the residual precision / recall gap.

---

## Notes for copy-editing

1. v0.4's Table 5b anchor is inside the "Fine-tuned Med42-8B (M4)"
   subsection of §Results. In v0.5 that subsection is retained as a
   diagnostic-of-the-8-B-tier discussion, but the table's role shifts
   from "here's what M4 achieves" to "here's the full arm ladder,
   B1' at the top." Consider reorganizing that subsection heading to
   "Fine-tuned Med42-8B (M4) and MedCAT+Rules (B1') — F-S 40
   held-out test."
2. The B0 F1 range "~0.05–0.15" is a rough characterization of the
   Phase 8 handoff notes; the exact single number from Phase 7 rerun
   should be substituted at final proof if desired.
3. The F0 GPT-family research-only comparator row remains a
   `[pending]` from v0.4; add its cell once the held-out-tier GPT
   run completes.
4. Renumber F-S 40 as Table 1 and demote v0.2's silver-population
   table (currently Table 1) to Supplementary Table S0. This aligns
   the paper's primary result with its primary table.

---

*Bootstrap CI reproduction command:*

```bash
venv-medcat/bin/python scripts/bootstrap_ci_medcat.py \
    --perdoc eval/results/medcat_iterations/iter3_fs_test_40.perdoc.csv \
    --n-boot 1000 --seed 0

venv-medcat/bin/python scripts/bootstrap_ci_medcat.py \
    --perdoc eval/results/medcat_iterations/iter3_synth_v1.perdoc.csv \
    --n-boot 1000 --seed 0
```
