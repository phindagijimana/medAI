# Weaknesses — account for, keep improving

Status: 2026-10-10. All F1 is **synthetic**. Do not add more ILAE strings to E (headline F1 did not move). Do not treat exam-QA (CoT, 70B, MedQA) as phenotyping.

**How to improve (in order).** Validator tags → `leo learn` Loop A (routing, ≥100 scored clashes/field) → Loop B (accept thresholds + 10% accepted audit) → versioned rule if the same pattern repeats → Loop C LoRA/BIO **paused**. Each extract change is a new `leo-v0.x` after a held-out re-score. Clicks never hot-reload Med42.

Why-tags that feed the loops: `wrong_value` / `wrong_status` / `quote_does_not_support` / `wrong_reader` / `copy_forward` / `missed`.

| Weakness | Accounted for today | Keep improving |
|---|---|---|
| **19/49 → 20/49 model-wrong still ACCEPT** | Letter table `eval/results/leo_error_capture_fs40.md`. Do **not** write rules from those hold-out rows. 8/20 are epilepsy type vs gold `unknown`. v0.9 rematch did not cut the leak (ASM 6→7) | Do not retune `--quote-entail` on EA0161–200 |
| **No real-note result** | Stated everywhere; research extract = `accepted` ∧ `specialist+llm` | IRB + secure compute; hold out a frozen test set |
| **LEO F1 ≤ model alone** (F-S 0.68 vs 0.70) | Audit trail (quote, source, review flag) is the product | Measure reviewer minutes + post-review F1, not pre-review micro-F1 |
| **Seizure type** under D17 (0.34 vs model 0.56) | Clash → review; model in `alternative`; `--disagree-llm candidate` opt-in | Loop A on real `reader_preferred`; flip display only if CI gate passes. Epilepsy type often the reverse — do not copy F-S 18 letters |
| **Stopped listed as current** | E: “was stopped”, later-stop-wins, PLAN/PMH, “that drug”, cluster-if / “can also use” / “may be considered” (`leo-v0.9`, written on EA0001–160). Sidecar `ctakes` opt-in | Validator `wrong_status`; keep sidecars opt-in so extra list items stay REVIEW |
| **Quote in note ≠ supports cell** | `--quote-entail` scored on L1C (10.49): auto P 0.87→0.91, R 0.59→0.48; 16 gold-correct demoted. **Default stays off** | Do not flip without a letter-bootstrap CI. Do not retune the entail lexicon on held-out letters |
| **Plan / “may be considered” as fact** (surgery, EEG done, ictal) | PLAN = hypothetical; sidecars `eeg-done`, `ictal` **opt-in**, never un-accept E. CPU: 408 sidecar-only, 0 ACCEPT (10.40) | Loop B: stop auto-accepting surgery/plans; sidecar on only after GPU both-readers + held-out precision |
| **Failed ASM reason** (rules ~4/27) | P1C + `fail-reason` sidecar (only if the reason is written) | `wrong_status` / Correct+quote; do not infer “failed” from a stop without a reason sentence |
| **Rescue vs “if she has a cluster”** | v0.5 rescue column; `rescue-if` sidecar opt-in. CPU rematch: item miss 1→0, list P 0.72→0.58 (FP 8→16) | Decide with a clinician whether hypothetical PRN counts; sidecar silence cannot demote E. Keep off default (10.40) |
| **Frequency** (ExECT-weak) | L1C already reads it; `freq` sidecar opt-in | Trained Xie/Decker **not** registered. Loop A if E vs L clash |
| **IED / EEG study type** | GPU X1C; `ied-silent` measured, **not** default (would auto-accept model-only IED) | Loop A / audit; do not ship `ied-silent` without real-note precision |
| **Focal onset / first feature** | X1C weak (7/12); `first-feature` only with “begins with” | Correct+quote; BIO onset head paused |
| **HS / extra MRI findings** | NegEx + `hs` sidecar opt-in; extra-lesion P ~0.50 | Review; no pixel model; do not dump catalogues into E |
| **DRE inferred vs as-stated** | E two-drug approximation; `dre` phrases only | Cannot judge adequate/tolerated trials — keep as review |
| **Silent auto-accept errors** | Validator **10% accepted audit** | Loop B uses audit + flagged; flagged-only rates are biased |
| **H2 LoRA fused worse (C5)** | `--h2` off fusion; not supported vs L2C | Loop C only after A/B, frozen hold-out, adapter must agree with E on E-easy cells |
| **Unsupported paper claims** | C5, F1 win, trust, real notes, “safe”, O raises C1 — reported, not claimed | Do not bury; do not retitle as an F1 win |
| **CPU: nothing accepted** | Documented; `--accepted-only` empty | Use GPU for research extract |
| **Roll-up hides change** | Per-note default; `visit_summary` display-only | Do not treat roll-up as scored; conflict flags still open |
| **Ontology picker lost to first-hit** | Exact match only; picker **off** | `--export-codes` after extract; do not put ICD/SCORE in E |
| **Engel / outcome** | No catalogue column; `--ext-detector engel` raises | New field first, then a reader — not a sidecar onto `surgery_history` |
| **Single-reviewer noise** | Tags + comment stored | Two-reader kappa on a subset before Loop A ships |
| **PHI on disk** | Owner-only job folder (24 h); opt-in `leo_training/` | Study copy is the record; do not commit reviews |

**Do not “fix” with:** more synonyms, CoT, 70B as default, live adapter from comments, majority vote of sidecars, synthetic `reviewed.csv` as training.

Detail: `IMPLEMENTATION.md`, `FIELD_SPECIALIST_DETECTORS.md` §9, `ACTIVE_LEARNING_PLAN.md`. Figures: `bin/leo evidence`.
