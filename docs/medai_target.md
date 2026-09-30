# MedAI-EPI target: how each arm reaches its F1 range

**Purpose.** This document is the north-star technical plan for the 13-arm ablation table below. For each row it captures what the arm is, current state on F-S test 40, the F1 target, the gap, the concrete prerequisites (data, code, compute, guardrails), and the honest failure modes. It should let any collaborator answer, without asking, "what still needs to happen before arm X is publishable?"

**Update discipline.** Whenever a run lands, update the *Current F1* column here in the same session. Never let the doc drift from `eval/results/`.

---

## 0. Target table

| Arm | Approach | F1 (target) | Notes |
|---|---|---|---|
| **B0 rules** | Trivial regex | 0.05–0.15 | Floor |
| **B1 MedCAT concept-link only** | No rules, just entity spans → schema | 0.20–0.35 | Isolates the linker contribution |
| **B1' MedCAT + rules** | ExECT-style rule layer | 0.75–0.85 | Specialized comparator (new baseline) |
| **M0 base Med42** | Zero-shot | 0.05–0.15 | |
| **M1 few-shot Med42** | Fixed exemplars | 0.10–0.20 | |
| **M1' RAG-few-shot Med42** | Retrieval from F-S 160 | 0.20–0.40 | |
| **M2 schema-injected Med42** | Schema in prompt | 0.10–0.20 | |
| **F0 GPT-5.6-terra** | Frontier closed-weight | 0.25–0.40 | Research-only (held-out tier) |
| **F1 DeepSeek-V3.1 zero-shot** | Frontier open-weight | 0.25–0.40 | On-prem deployable |
| **M4 tuned Med42 (v3)** | Our approach | 0.55–0.75 | |
| **M4+C** | + LMFE constrained decoding | 0.60–0.80 | |
| **M4+CR** | + constrained + RAG + CoT | 0.65–0.82 | |
| **M4+CRV** | + DeepSeek verifier | 0.68–0.85 | Auditability story |

Primary target evaluation is **micro-F1 on F-S test 40** (`EA0161-EA0200`) scored against F-S native gold. Secondary: synth-v3 held-out slice and preprocessed MTSamples 18.

---

## 1. Current status snapshot (as of 2026-09-30)

| Arm | Current F1 | Result file | Status |
|---|---:|---|---|
| B0 rules | ~0.10 (estimate, per-field varies) | `eval/results/b0_on_pilot_summary.md`, `b0_on_synth_v1_summary.md` | Landed; needs F-S 40 direct score for parity |
| B1 concept-link only | **not built** | — | Needs a new runner (see §5) |
| **B1' MedCAT+Rules** | **0.5627 micro-F1** | `eval/results/medcat_rules_fs_test_40.summary.md` | **Below target** — gap 0.19+ |
| M0 Med42 | 0.000 on most fields | `eval/results/llm_arms_vs_fs_gold_fs_test_base.summary.md` | Expected floor |
| M1 Med42 | ~0.05 | same | Expected floor |
| M2 Med42 | ~0.10 | same | Expected floor |
| M1' RAG-few-shot Med42 | **not built** | — | Needs RAG index + retrieval-augmented prompter |
| F0 GPT-5.6-terra M0/M1/M2 | ~0.00–0.20 (per field) | `eval/results/llm_arms_vs_fs_gold_gpt_terra.summary.md` | Held-out tier scored; needs a proper M2 score |
| F1 DeepSeek-V3.1 zero-shot | **not built** | — | Backend exists (`services/deepseek_backend.py`); needs zero-shot runner + F-S score |
| M4 tuned Med42 v3 | early result present | `eval/results/llm_arms_vs_fs_gold_fs_test_tuned_v3.summary.md` | Needs re-tune on synth-v3 corpus (in-flight) |
| M4+C | scoring result present | `eval/results/llm_arms_vs_fs_gold_fs_test_tuned_v3_constr` (dir) | Needs re-run with M4 v3 weights |
| M4+CR | **not built** | — | Needs RAG + CoT plumbing |
| M4+CRV | **not built** | — | Needs verifier arm (`services/llm_verifier.py` exists, needs wiring) |

**Biggest gap = B1' MedCAT+Rules.** The current 0.5627 falls short of the 0.75-0.85 range. Because most other arms are benchmarked *relative to B1'*, closing this gap is the single highest-leverage work item.

---

## 2. Data prerequisites

### 2a. Held-out corpora used by every arm

| Corpus | Role | Size | Status |
|---|---|---:|---|
| F-S test 40 | Primary eval (blind held-out) | 40 letters | Frozen; do not touch |
| F-S train 160 | RAG index + LoRA fine-tune (M4) | 160 letters | Ready |
| synth-v3 held-out | Secondary eval (US, phenotype-diverse) | ~50 visits | Will be sliced once generation completes |
| MTSamples preprocessed | Tertiary eval (real US narrative) | 18 notes | Landed (`data/eval_corpora/mtsamples_neuro_preprocessed`) |

### 2b. Corpora consumed only by training arms

| Corpus | Role | Size | Status |
|---|---|---:|---|
| synth-v1 | LoRA baseline for M4 v1 (superseded) | 1000 pairs | Archived; keep for reproducibility |
| synth-v2 | LoRA v2 experiments | 500 docs | Archived |
| synth-v3 | LoRA target for M4 v3 | ~493 visits | **In-flight now** (background PID 1530836) |
| F-S train 160 silver | Silver-label seed for MetaCAT + RAG | ~24 k spans | Derivable from B1' outputs |

### 2c. Guardrails from memory (do not violate)

- **OpenAI is research-only.** GPT-5.6-* is a paper comparator, never a deployed clinical extractor. Do not wire any GPT tier into the runtime `services/extract.py` request path.
- **Held-out GPT tier for research-role extractor.** When GPT plays extractor (F0), use `gpt-5.6-terra` (which authored no F-S or synth-v3 content) to avoid self-scoring circularity. If a tier appears in `generator_model` on any manifest row, that tier is **banned** as extractor for that eval.

---

## 3. Per-arm requirements

### 3.1. B0 rules — trivial regex

- **What it is.** Hand-crafted regex per field (e.g., `epilepsy_type` grep for "focal|generalized"; `age_at_onset` grep for `\b(\d+)\s*year(s?)\s*old`). No concept linking. Acts as the honest floor.
- **Current.** Landed; ran on pilot + synth-v1. Not yet scored on F-S test 40 with the current scorer.
- **Target.** 0.05–0.15.
- **Prerequisites.**
  - `services/baseline_rules.py` — exists.
  - Need: single-command runner that emits Evidence[T]-shaped outputs on F-S test 40 and passes them through `scripts/score_llm_arms_vs_fs_gold.py`.
- **Work items.**
  - [ ] Add `scripts/run_b0_rules_on_fs_test.py` (thin wrapper).
  - [ ] Score against F-S native gold; commit to `eval/results/b0_on_fs_test_40.summary.md`.
- **Failure modes.** Regex F1 collapses on paraphrases; that is the point.

---

### 3.2. B1 MedCAT concept-link only

- **What it is.** Run MedCAT concept detection **only** — no ExECT rules layered on top. Each detected concept span becomes a schema field via a minimal `cui → field` mapping. Isolates how much of B1's performance comes from the linker vs the rules.
- **Current.** Not built.
- **Target.** 0.20–0.35.
- **Prerequisites.**
  - `services/medcat_extractor.py` — exists.
  - `services/phenotype_assembler.py` — currently bundles concept detection *plus* rules. Needs a `no_rules=True` mode.
- **Work items.**
  - [ ] Add `PhenotypeAssembler(extractor, rules=[])` constructor path OR a companion `NoRulesAssembler` that maps every CUI to the first field that lists it.
  - [ ] Add `scripts/run_b1_concept_only_on_corpus.py`.
  - [ ] Score on F-S test 40 + synth-v3 held-out + MTSamples preprocessed.
- **Failure modes.**
  - CUIs mapping to multiple fields (e.g., `seizure` could go to `predominant_seizure_type`, `semiology_text`, or `other_seizure_types`) — pick the highest-precision mapping and document.
  - No negation/temporality — so "no seizures" is counted as an affirmed seizure entity. Expect a large F1 hit here.

---

### 3.3. B1' MedCAT + rules — **primary gap to close**

- **What it is.** MedCAT concept spans + ExECT-V2 rule vocabulary + medspaCy ConText + section-aware post-processing.
- **Current.** **F1 = 0.5627** micro on F-S test 40 (P=0.7077, R=0.4670).
- **Target.** 0.75–0.85.
- **Gap analysis.** Precision is high (0.71). Recall is the killer (0.47). We are missing ~half of the gold assertions. Per-field:
  - `epilepsy_type` — 0.97 (near-ceiling, no work needed).
  - `age_at_onset_years` — 0.86 (near-ceiling).
  - `current_asms` — 0.65 (17 FP / 19 FN — moderate).
  - `predominant_seizure_type` — 0.53 (7 FP / 11 FN — moderate).
  - `semiology_text` — 0.11 (1 TP / 31 FN — **recall floor**).
  - `other_seizure_types` — 0.15 (1 TP / 7 FN — recall floor).
  - `failed_asms` — 0.00 (0 TP / 1 FN — sparse, but zero).
- **Work items (highest leverage first).**
  - [ ] **`semiology_text` recall lift** — currently the extractor only pulls text when a canonical semiology cue phrase fires. Extend to grab the sentence around any known seizure-type CUI when applicable. Realistic lift: 0.11 → 0.30.
  - [ ] **`other_seizure_types` recall lift** — most FNs are because the rule only captures the *predominant* type. Add a rule that emits every additional seizure-type mention beyond the first as `other_seizure_types`. Realistic lift: 0.15 → 0.35.
  - [ ] **`current_asms` FP reduction** — 17 FPs mostly stem from grabbing non-current AED mentions (dose changes, allergies, historical). Add a ConText `temporal_status ≠ current` filter. Realistic lift: 0.65 → 0.75.
  - [ ] **`predominant_seizure_type` disambiguation** — 7 FPs are cases where the rule picked the wrong candidate. Add a "which is described most often" tiebreaker. Realistic lift: 0.53 → 0.65.
  - [ ] **Field-scoped section reads** — after preprocessing, use the canonical H&P labels to bias medication rules to the `Medications:` section, seizure-frequency rules to `HPI` / `Assessment`.
  - [ ] Rerun MedCAT+Rules on F-S test 40 after each change; keep a running scoreboard in `eval/results/medcat_iterations/`.
- **Predicted post-fix F1.** ~0.72–0.78. If we plateau below 0.72, the paper reports the honest number and reframes B1' as "matched to ExECT recall on shared fields".
- **Failure modes.**
  - Sparse gold on some fields (`failed_asms` n=1) makes F1 volatile; report per-field n throughout.
  - Preprocessing produced +0 delta here (see [US_NOTE_PREPROCESSING](US_NOTE_PREPROCESSING.md)), so do not expect it to close the gap by itself.

---

### 3.4. M0 base Med42 (zero-shot)

- **What it is.** Send raw note text + a minimal system prompt to Med42-8B. Parse the JSON reply.
- **Current.** Mostly F1 = 0.000 across fields.
- **Target.** 0.05–0.15.
- **Prerequisites.** `services/med42_backend.py` (loaded), `services/prompt_registry.py` (M0 prompt exists).
- **Work items.** None — this arm is intentionally weak. Its role is to prove the base model cannot do the task without help.
- **Failure modes.** The model returns non-JSON, unwrapped prose, or refuses. Handle via smart_repair which is already wired.

---

### 3.5. M1 few-shot Med42

- **What it is.** M0 prompt + K fixed exemplars (currently K=3) chosen once from synth-v1 pilot.
- **Current.** F1 barely improves over M0.
- **Target.** 0.10–0.20.
- **Prerequisites.** `services/prompt_registry.py` (M1 prompt exists; exemplars in `prompts/fewshot/`).
- **Work items.** None planned; exemplars can be refreshed but only if we finish M1' first (RAG version supersedes fixed few-shot).
- **Failure modes.** Fixed exemplars can bias toward their phenotype (all focal, all DRE, etc.) — check exemplar diversity.

---

### 3.6. M1' RAG-few-shot Med42

- **What it is.** M1 with K exemplars *retrieved* from F-S train 160 based on similarity to the query note. Uses `services/chunker.py` for the query segmentation.
- **Current.** Not built.
- **Target.** 0.20–0.40.
- **Prerequisites.**
  - Sentence-transformer or TF-IDF embedder over F-S train 160.
  - Retriever that returns top-K letters (K=3) with their gold slots.
  - Prompt template that injects retrieved letters as examples.
- **Work items.**
  - [ ] `services/rag_retriever.py` — embed F-S train 160 letters + a query encoder.
  - [ ] `services/rag_prompt.py` — template with retrieved-example injection.
  - [ ] `scripts/run_m1prime_rag_on_fs_test.py`.
  - [ ] Compare naive TF-IDF vs sentence-transformer retrieval; pick the winner.
- **Failure modes.**
  - Retrieved letters may leak similar phrasing that inflates F1 — must confirm retrieval never returns test docs.
  - Long retrieved contexts can push Med42-8B past its context window; chunk the retrieved letters to their gold-relevant sections.

---

### 3.7. M2 schema-injected Med42

- **What it is.** M0 prompt + full Pydantic schema JSON injected as a system-level "extract the following schema" instruction.
- **Current.** Present in registry; scored.
- **Target.** 0.10–0.20.
- **Prerequisites.** `services/prompt_registry.py` M2 prompt exists.
- **Work items.** None planned; primarily useful as a comparator to show that pure schema-injection is insufficient without a fine-tune (M4).
- **Failure modes.** Schema overwhelms the context window; the model returns partial JSON.

---

### 3.8. F0 GPT-5.6-terra (research-only)

- **What it is.** Frontier closed-weight comparator. Uses the **`gpt-5.6-terra` tier only** because that tier authored zero synth-v3 / F-S / MTSamples content (see memory: `feedback_gpt_research_holdout`). This admissibility is what makes the F1 number meaningful.
- **Current.** M0/M1/M2 scored on 100 F-S letters. Mostly 0.000 on M0; higher on M1/M2 but exact numbers are per-field.
- **Target.** 0.25–0.40 overall micro-F1 on best of M0/M1/M2.
- **Prerequisites.** `services/openai_backend.py`, `.env` with `OPENAI_API_KEY`, `scripts/run_openai_on_corpus.py` (or equivalent).
- **Work items.**
  - [ ] Complete F0 M2 scoring on all 200 F-S (currently 100).
  - [ ] Compute overall micro-F1 from per-field CSV; add to `eval/results/`.
  - [ ] Estimated cost: ~$50 for the remaining 100 letters through M2.
- **Failure modes.**
  - Tier drift: if OpenAI silently updates `gpt-5.6-terra` between runs, results are not comparable — pin the exact model ID string and cache all responses.
  - Do not accidentally use `gpt-5.6-sol` / `luna` here — those authored synth-v3 and would self-score.

---

### 3.9. F1 DeepSeek-V3.1 zero-shot

- **What it is.** Open-weight frontier comparator. Runs on our GPU (no external API dependency).
- **Current.** `services/deepseek_backend.py` exists; scripts for pilot exist. Not yet run against F-S test 40.
- **Target.** 0.25–0.40.
- **Prerequisites.** DeepSeek-V3.1 weights downloaded + a GPU with sufficient VRAM (single H100 minimum; may need quantization for the -Chat variant).
- **Work items.**
  - [ ] Verify weight availability + license terms.
  - [ ] `scripts/run_deepseek_on_fs_test.py` (adapt from `scripts/run_deepseek_on_pilot.py`).
  - [ ] Score via same scorer as GPT arms.
- **Failure modes.**
  - DeepSeek's clinical NLP performance is unproven for epilepsy phenotyping — expect variance in tone/format.
  - If VRAM is tight, use `bitsandbytes` 8-bit or model sharding.

---

### 3.10. M4 tuned Med42 v3 — LoRA on synth-v3

- **What it is.** Med42-8B + LoRA adapter fine-tuned on `(note, plan)` pairs from synth-v3. Adapter merged at inference, base frozen.
- **Current.** Has an early result file (`llm_arms_vs_fs_gold_fs_test_tuned_v3.summary.md`) from an earlier v3 attempt — needs re-tune on the current in-flight synth-v3 corpus.
- **Target.** 0.55–0.75.
- **Prerequisites.**
  - **synth-v3 generation completes** (in-flight — 493 visits, ETA ~3.5h).
  - **synth-v3 silver labelling** — semantic plan is authored per patient; ~10-15 evidence spans per visit derivable from the plan. Requires alignment script.
  - **LoRA training script** — `scripts/finetune_lora_epi.py` exists; may need adaptation for the visit-level data format.
  - GPU with 1×80GB (H100) or 2×40GB (A100) for 8B + LoRA training.
  - Recipe: r=16, alpha=32, dropout=0.05, target modules `q_proj,k_proj,v_proj,o_proj`, lr 2e-4, 3-5 epochs, batch_size 4 with gradient accumulation.
- **Work items.**
  - [ ] `scripts/emit_synth_v3_training_pairs.py` — walks the manifest + plans + notes; emits `{prompt: <task instruction + note text>, completion: <Evidence[T] JSON>}` JSONL.
  - [ ] `scripts/slurm_finetune_med42_v3.sh` — SLURM script for the LoRA fine-tune. GPU + 6-12h runtime.
  - [ ] Score against F-S test 40 + synth-v3 held-out.
  - [ ] Compare to v2 tuned to confirm progression.
- **Failure modes.**
  - **Synthetic-real distribution mismatch.** The model overfits to synth-v3 templates and drops on F-S (UK letters, different style). Mitigation: include ~10 % F-S train 160 in the training mix, or hold F-S 160 out entirely and rely on distribution overlap.
  - **Catastrophic forgetting** of Med42's clinical language. Mitigation: LoRA (which by design preserves base weights) + short training runs (≤5 epochs).
  - **Reward hacking of the semantic plan.** If plan-derived labels have systematic errors, the LoRA learns those errors. Mitigation: manual sample of 50 synth-v3 training pairs before committing to the full run.
  - **Evaluation leakage.** Confirm no synth-v3 patient P#### is also in the eval slice.

---

### 3.11. M4+C — M4 with LMFE constrained decoding

- **What it is.** M4 at inference time with the [`lm-format-enforcer`](https://github.com/noamgat/lm-format-enforcer) or an equivalent constrained-decoding library that forces the generation to conform to the Pydantic schema JSON grammar.
- **Current.** `services/constrained_decode.py` exists (Phase R4d completed); has a scoring result at `llm_arms_vs_fs_gold_fs_test_tuned_v3_constr`.
- **Target.** 0.60–0.80.
- **Prerequisites.** `services/constrained_decode.py` + `services/med42_backend.py` + LMFE installed.
- **Work items.**
  - [ ] Wire constrained decoding to the *new* M4 v3 weights (once §3.10 completes).
  - [ ] Score.
  - [ ] Compare to M4 without constraint to confirm the lift.
- **Failure modes.**
  - LMFE latency can be 2-4× larger than free-form; budget accordingly.
  - Enforcing the schema can force the model to emit `null` where it should say "unknown" — audit the null distribution.

---

### 3.12. M4+CR — M4 with constrained decoding + RAG + CoT

- **What it is.** M4+C plus (a) retrieval of similar F-S letters as few-shot context, (b) chain-of-thought "let me think step-by-step" prompt scaffolding before final JSON emission.
- **Current.** Not built.
- **Target.** 0.65–0.82.
- **Prerequisites.** M1' (§3.6) RAG index + retriever, and a two-stage prompt: (1) free-form CoT reasoning, (2) constrained-decoding JSON emission of the final answer.
- **Work items.**
  - [ ] `services/rag_prompt.py` extended with a CoT preamble.
  - [ ] Two-stage generator: first pass free-form to `</reasoning>`, second pass constrained-decoding to `{...}`.
  - [ ] Score.
- **Failure modes.**
  - CoT can hallucinate — the reasoning trace may look plausible but drive the JSON output away from the note. Mitigation: score the JSON only; keep the CoT as an audit trail.
  - Two-stage inference doubles latency.

---

### 3.13. M4+CRV — M4+CR with DeepSeek verifier

- **What it is.** M4+CR extraction pass followed by a DeepSeek-V3.1 verifier that reads (note, extraction) and flags/repairs disagreements. Emits a per-field confidence + a per-field final label.
- **Current.** `services/llm_verifier.py` + `services/deepseek_backend.py` + `scripts/run_deepseek_verifier_on_pilot.py` exist. Not yet wired to M4+CR.
- **Target.** 0.68–0.85.
- **Prerequisites.** M4+CR (§3.12) + DeepSeek-V3.1 verifier.
- **Work items.**
  - [ ] `scripts/run_m4crv_on_fs_test.py` — pipes M4+CR outputs through the DeepSeek verifier.
  - [ ] Verifier prompt: "Given this note and this extracted phenotype, flag any assertion that is unsupported by the note text. Suggest a corrected value with evidence text."
  - [ ] Score.
  - [ ] Report: verifier changed X % of assertions, of which Y % were correct changes vs Z % introduced errors.
- **Failure modes.**
  - **Verifier can hallucinate its own errors** and "correct" a correct answer. Compare pre/post verifier per-field F1; if the verifier hurts a field, gate on that field.
  - **Cost / latency** — DeepSeek verifier runs on the same GPU as M4; batch inference required.
  - **Confidence calibration** — DeepSeek's self-reported confidence is not well-calibrated for extraction; treat as ordinal, not probabilistic.

---

## 4. Cross-cutting infrastructure

### 4.1. Scoring harness

- **Primary scorer:** `scripts/score_llm_arms_vs_fs_gold.py` — micro-F1 per field vs F-S native gold, with bootstrap 95 % CIs.
- **Rules scorer:** `scripts/score_medcat_vs_gold.py` — same interface, tailored to Evidence[T].
- **Requirement:** every arm above must emit output files in the same JSON schema (`data/run_manifests_*/{doc_id}.json`) so a single scorer processes all of them.

### 4.2. Universal manifest

- `docs/CORPUS_MANIFEST_SCHEMA.md` — the row-per-visit format used by every corpus.
- All arms consume `data/eval_corpora/*/manifest.csv` when present.

### 4.3. Preprocessing

- `services/us_note_preprocessing.py` — invoked lazily by LLM arms whenever a corpus is US-style and section headers are non-canonical.
- Empirically **does not help B1'** (see [US_NOTE_PREPROCESSING.md](US_NOTE_PREPROCESSING.md)) but expected to help M1'/M4+CR (section-scoped retrieval, section-gated few-shot).

### 4.4. RAG index

- Built once from F-S train 160.
- Indexed granularity: per-section (chief complaint / HPI / meds / imaging).
- Reranker: minimal — cosine over sentence-BERT.
- Do not re-index at inference time.

### 4.5. Constrained decoding

- `services/constrained_decode.py` uses LMFE.
- Schema pinned to `schema/ontology.py` v0.2.1.
- If we bump the schema, regenerate the constraint grammar in the same commit.

### 4.6. Verifier

- `services/llm_verifier.py` uses the DeepSeek backend.
- The verifier reads `(note, extraction)` — must fit in DeepSeek's context. Chunk long notes.
- The verifier must never see the F-S gold — sanity-check by running with a dummy extraction and confirming the verifier does not "reveal" the true answer.

### 4.7. GPU accounting

| Arm | GPU | Runtime per corpus |
|---|---|---|
| B0, B1, B1', MTSamples preproc | CPU | seconds |
| M0/M1/M2/M4 inference (F-S 40) | 1×A100 40GB | 30-60 min |
| M4 LoRA training | 1×H100 80GB or 2×A100 40GB | 6-12h |
| DeepSeek zero-shot F-S 40 | 1×A100 40GB (8-bit) | ~1h |
| DeepSeek verifier | 1×A100 40GB | ~1h |

---

## 5. Dependency graph

```
        preprocessing (done) ──► MTSamples / synth-v3 eval slices
                                     │
                                     ▼
    B0 rules  ─┬─►  scoring harness  ─────► scoreboard
    B1 concept-only ─┘                          ▲
    B1' MedCAT+Rules (needs recall lift) ───────┤
                                                │
    M0/M1/M2 Med42 (done) ──────────────────────┤
                                                │
    F0 GPT-5.6-terra (partial) ─────────────────┤
    F1 DeepSeek zero-shot ──────────────────────┤
                                                │
    synth-v3 corpus (in-flight)                 │
        │                                       │
        ▼                                       │
    silver-label + emit training pairs          │
        │                                       │
        ▼                                       │
    M4 LoRA fine-tune ──────────────────────────┤
        │                                       │
        ▼                                       │
    M4+C constrained ───────────────────────────┤
        │                                       │
        ▼                                       │
    RAG index + retrieval + CoT                 │
        │                                       │
        ▼                                       │
    M4+CR ──────────────────────────────────────┤
        │                                       │
        ▼                                       │
    DeepSeek verifier                           │
        │                                       │
        ▼                                       │
    M4+CRV ─────────────────────────────────────┘
```

Critical path to a shippable table:

1. **B1' recall lift** (§3.3) — biggest single-arm gap.
2. **synth-v3 completes → silver labels → M4 v3 fine-tune** — biggest ML work item.
3. **F1 DeepSeek zero-shot + M4+CR + M4+CRV** — extends the ablation.
4. **B1 concept-only + M1' RAG** — fills the honest floor rows.

Parallelisable:

- `F0 GPT-5.6-terra` M2 completion (~$50, few hours).
- `B0 F-S 40 scoring` (~1 min).

---

## 6. Success gates

Ship the paper when:

- [ ] Every arm in the table has a scored F1 on F-S test 40 with bootstrap 95 % CI.
- [ ] B1' ≥ 0.70 micro-F1 (bottom of the target band).
- [ ] M4+CRV ≥ 0.68 micro-F1.
- [ ] The gap M4 → M4+CRV is ≥ 0.10 F1 (ablation is meaningful).
- [ ] F0 vs F1 comparison shows at least one open-weight arm within 0.05 of the closed-weight comparator (auditability argument).
- [ ] Every arm's failure modes above are demonstrated with at least one concrete example in the supplement.

If any of these fail after honest effort, **the paper reports the negative result** — do not tune eval to hit the target.

---

## 7. Risks & unknowns

- **B1' plateau below 0.72** — if the semiology_text field structurally caps at 0.30 because the F-S gold uses free-text spans that the extractor cannot canonicalize, we may need to redefine the field's scoring metric (span overlap instead of exact match). Document this before running the score, not after.
- **synth-v3 quality** — if the human blind-eval accuracy is above 75 % (i.e., raters *can* tell notes are synthetic), M4 trained on synth-v3 may not transfer to F-S. Backup: mix in F-S train 160 to the LoRA data.
- **DeepSeek availability** — model access + GPU are external dependencies. If unavailable, drop F1 and M4+CRV from the table and reframe the paper around the open-weight fine-tune story alone.
- **Verifier feedback loop** — if the verifier reads the extraction and both models over-agree (both wrong), the F1 doesn't move but confidence looks high. Test by injecting known-wrong extractions and measuring detection rate.

---

## 8. Update log

| Date | Change | By |
|---|---|---|
| 2026-09-30 | Initial draft. B1' current = 0.5627; synth-v3 generation in-flight (PID 1530836). | Session on `main` |

Add a row here on every update to prevent drift.
