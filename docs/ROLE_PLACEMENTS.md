# Role placements: RAG, O codes, ConText ablation (not extract machinery)

Status: 2026-10-07. EVAL D21 / §10.36. Default LEO (D17, flag off) is unchanged.

These pieces are useful. They are **not** extra machinery inside the phenotype filler.
Each one solves a different job than “read this note, fill `seizure_type`.”

Short map: **RAG → guideline questions.** **Ontologies → O codes after extraction.**
**70B / chain-of-thought / self-consistency → not shipped** (optional stress tests or DRE
reasoning, not the default extract path). **Second ConText → E ablation, not a third arm.**
The extract table still improves most from quote entailment, med-status, sectioning, and
per-field routing.

## 1. RAG over ILAE/ACNS passages (`--ask-rag`)

**What it is.** At *question* time, retrieve short operational paraphrases of Fisher 2017,
Scheffer 2017, Kwan 2010, and ACNS Hirsch, then stuff them into the ask prompt.

**When it helps.** Guideline judgment, not span copy. Shipped templates:

| Template | Job |
|---|---|
| `dre_kwan` | Does this ASM history meet ILAE 2010 DRE (two adequate, tolerated trials)? |
| `first_feature` | Is this onset the first feature or later evolution? |
| `ltm_sense` | Is this “LTM” a study or a drug in this sentence? |

**When it does not.** Filling `seizure_type` from “focal impaired awareness seizures.”
The answer is in the note. Retrieving ILAE text can make the model echo the guideline
instead of the quote (the same failure mode as schema-echo).

**Guardrails**

- Off unless `--ask-rag` or `MEDAI_LEO_ASK_RAG=1`.
- Never imported by L1C / X1C / P1C / F1C (`services/flat_extract.py` and siblings).
- Injected only when the question is a guideline-judgment ask (`services/guideline_rag.py`).
  A seizure-type question retrieves nothing even if the flag is on.
- Corpus: `data/guidelines/ilae_ask.json` (our paraphrases + citations, not PDF dumps).
- Quote check still requires the quote in the **note**. A guideline echo is `rejected`
  `offsets_unresolved`.
- Answers stay `needs_review` (`llm_only`); RAG does not auto-accept.

Corpus file is not the leftover `utils/rag_system.py` (mixed neurology guidelines, unused).

## 2. SCORE / EpSO / ICD-10-CM / Orphanet in O (`--export-codes`)

**What they are.** Controlled vocabularies and coding systems, not readers of English.

| Resource | Useful as | Not useful as |
|---|---|---|
| SCORE | Map EEG findings you already extracted to a standard report code | A gazetteer that invents LPDs |
| EpSO | Semantic layer / interoperability (EPIO already retrieves in O) | Extra trigger strings in `rules/fields/` |
| ICD-10-CM | Billing/cohort export, G40.x category | ILAE phenotype (ICD “intractable” ≠ ILAE DRE) |
| Orphanet | Rare-syndrome codes when etiology names a disease | Filling seizure type |

**How they help.** After E or L emits “Dravet” or “left temporal IEDs,” O attaches a stable
id (`services/o_code_maps.py` → `Claim.export_codes`). That lets a downstream registry or
NINDS CDE export join to other sites. Dumping them into E only adds collisions.

**Guardrails**

- Off unless `--export-codes` or `MEDAI_LEO_EXPORT_CODES=1`.
- Does not change ACCEPT / REVIEW, `concept`, detectors, or D17.
- Not added to the ontology *retriever* (SCOPE D3–D5 retrieval still deferred).
- `drug_resistance_status` never maps to ICD intractable.
- “No LPDs” does not become a SCORE LPD code.
- Orphanet fires only when the *extracted* value/evidence already names the disease.

EPIO remains the live retrieval source (`docs/ONTOLOGY_SOURCES.md`). NINDS CDEs stay a
documentation table (`docs/NINDS_CDE_MAPPING.md`) except discontinuation phrases used by
the `fail-reason` sidecar.

## 3. Second ConText as an ablation inside E (`--context-engine`)

**What ConText is.** A component: negation / experiencer / historical / hypothetical on a
mention. E already has a medspaCy ConText pass (`docs/METACAT_EVAL.md`).

**Useful:** Ablation inside E — swap medspaCy ConText vs sentence-level skips vs NegEx
cues; score the same fields (IED present, current vs prior ASM). That tells you whether
LPD/surgery false positives are a context-engine problem.

**Not useful:** Publishing “ConText F1 vs EpExtra F1.” ConText does not emit ILAE epilepsy
type. Scoring it as a phenotype system confuses a preprocessor with a table filler.

| Flag | Engine |
|---|---|
| `medspacy` (default) | Current E |
| `sentence` | `rules.sentence_context` |
| `negex` | Chapman 2001 pre-negation (`services.ext_detectors.span`) |

`MEDAI_LEO_CONTEXT_ENGINE` overrides. Default ≡ previous E.

## 4. Not shipped: 70B, chain-of-thought, self-consistency

Per the same placement rule. They are not default extract machinery and were **not**
wired in this pass.

| Idea | Useful as | Why not the default reader |
|---|---|---|
| Med42-70B | Spot-check on ~20 hard disagreements (seizure type, hedged MRI) to see if 8B is the bottleneck | ~10× memory, no L40S 24GB path; status errors (negation, planned, LTM-as-drug) still need prompt/rules |
| Chain-of-thought | Multi-step judgment (“count failed, tolerated ASMs → Kwan DRE”) on the *ask* path | Harmful for extraction: longer, less stable JSON, invented reasoning; we score the label, not the scratchpad |
| Self-consistency | Only if sampling is on | We run greedy (`seed 0`, `do_sample=False`). Voting would fight the eval contract and would not fix a wrong gazetteer hit on “no LPDs” |

Use `dre_kwan` + `--ask-rag` when the job is Kwan judgment. Use 8B L1C for the extract table.

## 5. Flags (all off by default)

```bash
bin/leo batch notes.xlsx --ask-rag --ask-template dre_kwan
bin/leo batch notes.xlsx --export-codes
bin/leo batch notes.xlsx --context-engine sentence   # or negex
```

Tests: `tests/test_role_placements.py`. Protocol: EVAL D21 / 10.36.
