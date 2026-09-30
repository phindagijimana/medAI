# MetaCAT training plan for MedAI-EPI

**Status:** proposal (see task #164). This document specifies what MetaCAT is, why we want one, how synth-v3 can serve as training data, and — importantly — the limitations of a synth-v3-trained MetaCAT compared to one trained on real clinical letters.

## 1. What MetaCAT is

MetaCAT ("Meta-annotation for MedCAT") is a per-mention contextual classifier that sits on top of a MedCAT concept span. For every concept span the CDB detects, MetaCAT predicts a small set of **contextual labels**:

| Label | Values | Example |
|---|---|---|
| **Presence / Negation** | affirmed, negated, unknown | "no seizures" → negated |
| **Experiencer** | patient, family, other | "her mother had epilepsy" → family |
| **Temporality** | current, past, hypothetical | "history of seizures in 2015" → past |
| **Certainty** | definite, possible, hedged | "possibly focal onset" → possible |

Architecturally MetaCAT is a small transformer/CNN that consumes the token window around the concept span plus surrounding section context, and emits a softmax over the label set for each meta-annotation task. Model weights are per-CDB and per-task.

MedCAT + MetaCAT is the pattern used by ExECT-V2: their model produces both the concept CUI *and* whether the mention is negated / historical / family / hedged. Our current pipeline uses `medspaCy ConText` rules for the same purpose — cheaper to build but less flexible.

## 2. Why we want a MetaCAT for MedAI-EPI

Two reasons.

**a) Better negation & experiencer handling in US notes.** The ConText rules were tuned on UK letters. US progress notes carry longer HPIs with mixed temporality ("she was on lamotrigine but Dr. X switched her to Keppra last month, now off both"). A learned classifier that has seen many US patterns will out-perform hand-crafted rules on ambiguous cases.

**b) Method parity with ExECT.** Reviewers of the MedAI-EPI manuscript will ask whether we replicated ExECT's architecture. Having a MetaCAT lets us answer yes; running only ConText rules leaves us a step short.

## 3. Where the training data comes from

Historically MetaCAT is trained on clinician-annotated spans: humans label each medication mention as `current` vs `past`, each seizure mention as `patient` vs `family`, etc. That is expensive.

Two synthetic-derived alternatives are available to us.

### 3a. Weakly-supervised silver labels from ExECT rule outputs on F-S

Run `services/phenotype_assembler.py` on the 200 F-S letters. For every MedCAT mention that fell into an Evidence[T] output, we already know its `certainty` and `temporal_status` (they are fields on the Evidence wrapper). Serialize `(text, span, label)` triples for each meta-annotation task.

- **Coverage:** ~200 letters × ~40 populated fields/letter × ~1-3 evidence spans/field ≈ 24 k labels total.
- **Splits:** F-S train (160) → MetaCAT train; F-S test (40) → held-out for both rules and MetaCAT.
- **Distribution:** UK letters, so still not US-native, but on-distribution with the rule vocabulary.

### 3b. Semantic-plan-derived silver labels from synth-v3

Every synth-v3 note is authored to encode a specific semantic plan, and the plan explicitly states each assertion's field, value, and (for many fields) its temporal_status and experiencer. After we generate ~493 US-style notes, we can:

1. Run MedCAT on each note to get concept spans.
2. Align each span to a semantic-plan assertion (fuzzy string / CUI match).
3. Emit the plan's labels (`patient`, `current`, `definite`) as silver ground truth for that span.

- **Coverage:** ~493 visits × ~20 grounded spans each ≈ 10 k labels.
- **Distribution:** US templates (12 note types), phenotype-diverse.
- **Complements 3a** — combine the two datasets for training breadth.

## 4. Proposed pipeline

```
      F-S rule outputs   ─┐
                          ├─►  silver span+label triples  ─►  MetaCAT training  ─►  weights (per task)
     synth-v3 rule align ─┘                                              │
                                                                         ▼
                                              F-S test 40 (held-out)  evaluation
                                              synth-v3 held-out       evaluation
```

Concrete steps (each one a task-tracker entry):

1. `scripts/emit_metacat_silver.py` — walks manifests + rule outputs, emits per-task JSONL files with `(text_window, span, label)` rows.
2. `scripts/train_metacat.py` — thin wrapper around MedCAT's `MetaCAT.train()` for each of the four tasks.
3. `services/metacat_backend.py` — loads trained MetaCATs, exposes an inference API that plugs into `services/phenotype_assembler.py` alongside the existing ConText rules.
4. `scripts/score_metacat_vs_context.py` — compares MetaCAT to the current ConText rules on F-S test 40 and on a synth-v3 held-out slice.

## 5. Limitations (honest self-critique)

These are the reasons a synth-v3-trained MetaCAT will not be equivalent to a MetaCAT trained on real US EHRs — and why the manuscript should say so.

### 5a. Distribution gap: synth-v3 is not real
- Synth-v3 notes are GPT-generated from templates + semantic plans. Real US notes contain typos, dictation drift, copy-forward errors, and idiosyncratic clinician voice that no template captures. A MetaCAT that has never seen those artifacts may over-fit to GPT stylistic tics.
- Mitigation: report accuracy on F-S test 40 as the primary metric (real letters, real clinician voice), and treat synth-v3 held-out as a secondary sanity check.

### 5b. Incomplete negation coverage in semantic plans
- The v2 sampler emits mostly *affirmed* assertions. Negation (`patient denies seizures`, `no aura`, `no focal deficit`) appears in real notes but is barely represented in the plan. A MetaCAT trained mainly on affirmed cases will have poor recall for negation.
- Mitigation: extend the sampler to include `denied_findings` and `negated_symptoms` fields with realistic frequency (~15-20 % of clinical assertions), and re-generate a subset of synth-v3 accordingly.

### 5c. Experiencer coverage is sparse
- Plans focus on the patient. "Family history of epilepsy" or "her sister has migraines" is rarely in the plan, so silver labels for `experiencer=family` are scarce. A model trained on this data will default to `patient` and miss family-history mentions.
- Mitigation: add a `family_history` structured field to the plan (already partly present in FHx sampling) and audit alignment during silver-label emission.

### 5d. Temporality is coarse
- Semantic plans say "current AED", "past AED", "current seizures". Real notes have finer-grained temporality ("in remission since 2020", "one seizure last Tuesday", "chronic since childhood"). MetaCAT trained on binary current/past labels will collapse the fine grain.
- Mitigation: acceptable for the paper's scope; call it out in Limitations.

### 5e. Single-labeler bias
- Silver labels from rule outputs inherit any systematic bias in those rules. If ConText mis-labels 8 % of mentions as negated when they are affirmed, the MetaCAT trained on that data will inherit the same mistake.
- Mitigation: sample 100-200 labels for manual audit; report noise rate; consider training with label smoothing or a small clinician-labeled seed set.

### 5f. Generator model attribution
- Semantic-plan derived labels came from `gpt-5.6-sol` / `luna`. Never evaluate MetaCAT against a research-role GPT extractor without using `gpt-5.6-terra` (held-out tier) to avoid self-scoring circularity — see `feedback_gpt_research_holdout` memory.

### 5g. No adversarial cases
- Rule outputs and semantic plans do not generate the difficult "cross-negation" patterns ("she is no longer having her breakthrough seizures, though she used to have generalized ones") that clinicians write frequently. A MetaCAT that has never trained on them will fail on them silently.
- Mitigation: hand-curate a 100-item adversarial test set from F-S and score MetaCAT separately on it.

## 6. Success criteria

A synth-v3 + F-S trained MetaCAT should meet:

- **F1 ≥ 0.85 on F-S test 40** for the `presence` (affirmed / negated) task — matching or beating current ConText rules.
- **F1 ≥ 0.75 on F-S test 40** for `experiencer` and `temporality` — where ConText typically struggles.
- **≥ 0.05 F1 lift vs ConText on at least one task** — to justify the additional model complexity.
- **Documented failure modes** — the six limitations above scored against manual samples so the paper can report them.

If none of these are met, we do not deploy the MetaCAT and continue with ConText, and the paper reports the negative result honestly.

## 7. Cross-references

- [US Note Preprocessing](US_NOTE_PREPROCESSING.md) — canonical headers help MetaCAT feature extraction.
- [Corpus Manifest Schema](CORPUS_MANIFEST_SCHEMA.md) — required for silver-label alignment.
- [References](REFERENCES.md) — MedCAT / MetaCAT / ConText citations.
- Task #164 — `Batch B — MetaCAT training on F-S 160 train (after Batch A lands)`.
