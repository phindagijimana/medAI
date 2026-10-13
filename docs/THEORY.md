# Theory and Science

Why LEO is three parts — **L** (language model), **E** (rules specialist), **O** (ontology) — and why they are not voted into one answer.

Tested on **synthetic notes only**. Not a device. Numbers: [Interpreting results](INTERPRETING_RESULTS.md). Bibliography: [Literature](LITERATURE.md).

## The problem

A clinic letter does not support one complete phenotype. The same sentence can be current or prior, a plan or a fact, the patient’s drug or a family history. A single extractor that always emits a value will be wrong on a large share of cells, and the error is silent.

LEO’s claim is not “more accurate than Med42 on F1.” It is: **keep the cells where two different readers agree** (the research extract), report that table’s concordant PPV against gold, and put clashes in a review queue. On the 40-letter gold that extract is 71/82 = 0.866. Accepted cells are still not “safe” (about one in six or seven misses gold).

That shape is selective prediction plus two-reader concordance [Khan 2025; Alwakeel 2025; Swaminathan 2023]. The epilepsy-specific move is that one reader is deterministic rules, disagreements stay visible, and the default shown value is the rules (D17).

```
note → Prepare → E + L + O → fuse → verify → phenotype row
```

## Why L — the language model

**What it is.** Med42-8B [Christophe et al. 2024], flat prompt, two fixed examples, schema-constrained greedy decoding (`seed=0`). It fills ILAE enums, drugs, and free-text spans the rules cannot list.

**Why this model.** It is an open clinical LLM we can run on approved compute. 70B, chain-of-thought, and self-consistency voting are not the extract path: they are a different job (exam-QA), and they do not fix status or quote-support holes.

**Why constrained.** Prompts that pasted the JSON schema (M0–M2) echoed the schema instead of filling fields. Constrained decoding stops that. Fine-tuning (H2) raised the model alone and **lowered** fused LEO, so the shipped reader stays L1C.

**What L cannot do.** It does not know ILAE operational rules unless they are in the prompt. It invents codes if you let it pick from a long index. A quote it returns can sit in the note and still not support the cell [Windisch 2026; Chung / VeriFact 2026]. Presence is required (C4); semantic support (`--quote-entail`) stays off.

## Why E — EpExtra (rules)

**What it is.** MedCAT [Kraljevic et al. 2021] plus ExECT-style field rules [Fonferko-Shadrach et al. 2019] plus medspaCy ConText [Harkema 2009; Eyre 2021]. It reads drugs, types, EEG/MRI cues, and status/time (“was stopped”, later-stop-wins, PLAN ≠ current).

**Why rules as the second reader.** Agreement is only an accept signal if the two readers fail differently. Two LLMs that share a training corpus often share errors [Khan 2025]. E is deterministic, lineage to published epilepsy letter NLP, and precise on named ASMs and ILAE strings that are actually written. Extra ILAE synonyms did not move headline F1; the remaining holes are status, time, and quote support — not missing aliases.

**Why ILAE and Kwan live in E.** Seizure/epilepsy enums follow Fisher / Scheffer 2017 (historical names from Berg 2010 still appear in notes). Drug resistance, if inferred, follows Kwan 2010 as a two-drug approximation; as-stated DRE is a separate opt-in detector. Rescue vs maintenance follows NINDS CDE / ILAE ASM wording [Loring 2011; Perucca 2024] — a labelling convention, not a second ontology.

**What E cannot do.** It misses paraphrase and implied type. Seizure type is weak when D17 shows the rules on a clash. It cannot judge whether two failed trials were adequate. It must not swallow ICD “intractable,” SCORE labels, or Orphanet ids as extra trigger strings (those are O export, after extract).

## Why O — ontology

**What it is.** A retriever over HPO [Köhler 2021], MONDO, EPIO [Sargsyan 2023], SNOMED, and RxNorm. Exact match may stamp a code. The LLM picker of a ranked list is **off** (it lost to first-hit). Optional `--export-codes` attaches ICD-10-CM G40.x, Orphanet, SCORE [Beniczky 2017], or EpSO [Sahoo 2014] **after** fusion.

**Why a third piece at all.** L and E extract *values*. Cohort work and interoperability need *codes* the model is not allowed to invent. O is hygiene: pin an id when the label already matches. It is **not** shown to raise auto-accept precision or concordant PPV. Do not put O in the results sentence.

**What O must not do.** It must not dump SCORE/ICD/Orphanet into E as gazetteers. It must not treat ICD intractable as ILAE drug-resistant epilepsy. It must not be a majority voter that can un-accept a good E cell.

## Why fuse this way (not a third model)

| Situation | What LEO does | Why |
|---|---|---|
| L and E same value | ACCEPT (`llm+specialist`) | Concordant PPV is the quantity we evaluate [Alwakeel 2025] |
| L and E clash | REVIEW; **show E**; keep L as `alternative` (D17) | Wang et al. 2026 resolve clash by ensemble; we leave it visible so a person can choose |
| One reader only | REVIEW (`no_second_reader` on CPU) | One reader is not an accept band |
| Quote not in the note | never ACCEPT | C4; Gero 2023 wanted a span — we require presence, not a self-verify loop |
| Judge / critique LLM | not used | Mahbub 2026 adds a judge; Courvoisier 2026 uses k-of-n LLMs. We stay two readers |

Sidecars (`--ext-detector`) are extra literature jobs (frequency, stated type, HS, and so on). They never auto-accept and cannot un-accept E.

## What this is not

- An F1 win over Med42 (reviewed−model CI includes 0).
- A trust or time-and-motion study.
- Evidence on real notes.
- A claim that accepted cells are safe.
- ILAE 2025 as the shipped enums (still 2017; 2025 is scoped, not flipped).

Design walk-through: [Design](IMPLEMENTATION.md). How to quote a number: [Interpreting results](INTERPRETING_RESULTS.md).
